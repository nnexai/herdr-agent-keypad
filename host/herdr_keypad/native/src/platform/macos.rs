//! macOS-only enumeration/opening and process-local suspend signalling.
//!
//! The portable part of this module normalizes synthetic IOKit/registry facts
//! so Linux tests can exercise the mapping contract. Actual `/dev/cu.*`
//! enumeration and opening are compiled only for macOS. Neither fixture data
//! nor this adapter treats OS metadata as application authorization: UsbPort
//! still requires the binding and a fresh hello.

use crate::ports::usb::{canonical_interface, canonical_serial, endpoint_is_stable, DeviceCandidate, PlatformSerial, SerialConnection, UsbError, EXPECTED_CDC_INTERFACE, EXPECTED_PID, EXPECTED_SERIAL, EXPECTED_VID};
use serde::{Deserialize, Serialize};
use std::io;
use std::sync::Arc;
use tokio::sync::broadcast;
#[cfg(target_os = "macos")]
use std::time::Duration;
#[cfg(target_os = "macos")]
use tokio_serial::SerialPortBuilderExt;

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct MacRegistryRecord {
    pub vendor_id: Option<u16>,
    pub product_id: Option<u16>,
    pub serial_number: Option<String>,
    pub interface: Option<String>,
    pub location: Option<String>,
    /// Present for native enumeration only. Portable fixtures intentionally
    /// omit this host path.
    #[serde(default, skip_serializing)]
    pub device: Option<String>,
    #[serde(default)]
    pub permission: Option<String>,
    #[serde(default)]
    pub state: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MacRegistryOutcome {
    pub candidate: DeviceCandidate,
    pub safe_code: &'static str,
}

pub fn normalize_registry(record: &MacRegistryRecord) -> MacRegistryOutcome {
    let device = record.device.clone().unwrap_or_default();
    let interface = canonical_interface(record.interface.as_deref().unwrap_or(""), record.location.as_deref());
    let candidate = DeviceCandidate {
        stable: endpoint_is_stable(&device),
        device,
        vid: record.vendor_id,
        pid: record.product_id,
        serial_number: record.serial_number.as_deref().and_then(canonical_serial),
        location: record.location.clone(),
        manufacturer: None,
        product: None,
        interface,
    };
    let safe_code = if record.permission.as_deref() == Some("denied") {
        "permission_denied"
    } else if record.state.as_deref() == Some("disconnected") {
        "disconnected"
    } else if !candidate.exact_descriptor() {
        if candidate.serial_number.as_deref() != Some(EXPECTED_SERIAL) {
            "lookalike"
        } else {
            "wrong_interface"
        }
    } else {
        "exact"
    };
    MacRegistryOutcome { candidate, safe_code }
}

/// Normalize a synthetic registry snapshot. Ambiguity is returned explicitly
/// instead of collapsing to the first matching service.
pub fn normalize_registry_snapshot(records: &[MacRegistryRecord]) -> Vec<MacRegistryOutcome> {
    let mut outcomes: Vec<MacRegistryOutcome> = records.iter().map(normalize_registry).collect();
    let exact_count = outcomes.iter().filter(|outcome| outcome.safe_code == "exact").count();
    if exact_count > 1 {
        for outcome in outcomes.iter_mut().filter(|outcome| outcome.safe_code == "exact") {
            outcome.safe_code = "ambiguous";
        }
    }
    outcomes
}

#[derive(Clone)]
pub struct MacOsPlatform {
    suspend: Arc<broadcast::Sender<()>>,
}

impl Default for MacOsPlatform {
    fn default() -> Self { Self::new() }
}

impl MacOsPlatform {
    pub fn new() -> Self {
        let (sender, _) = broadcast::channel(4);
        Self { suspend: Arc::new(sender) }
    }

    /// Called by the process-local suspend hook. There is no cross-process or
    /// HID side effect; subscribers simply invalidate the active USB session.
    pub fn notify_suspend(&self) {
        let _ = self.suspend.send(());
    }

    pub fn subscribe_suspend(&self) -> broadcast::Receiver<()> {
        self.suspend.subscribe()
    }

    pub fn normalize_registry_snapshot(records: &[MacRegistryRecord]) -> Vec<MacRegistryOutcome> {
        normalize_registry_snapshot(records)
    }
}

impl PlatformSerial for MacOsPlatform {
    fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError> {
        #[cfg(target_os = "macos")]
        {
            let ports = serialport::available_ports().map_err(|_| UsbError::Io)?;
            let mut records = Vec::new();
            for port in ports {
                if !port.port_name.starts_with("/dev/cu.") {
                    continue;
                }
                if let serialport::SerialPortType::UsbPort(usb) = port.port_type {
                    records.push(MacRegistryRecord {
                        vendor_id: Some(usb.vid),
                        product_id: Some(usb.pid),
                        serial_number: usb.serial_number,
                        interface: usb.interface.map(|interface| interface.to_string()),
                        location: None,
                        device: Some(port.port_name),
                        permission: None,
                        state: None,
                    });
                }
            }
            Ok(normalize_registry_snapshot(&records)
                .into_iter()
                .filter(|outcome| outcome.candidate.exact_descriptor())
                .map(|outcome| outcome.candidate)
                .collect())
        }
        #[cfg(not(target_os = "macos"))]
        {
            Ok(Vec::new())
        }
    }

    fn open(&self, candidate: &DeviceCandidate) -> Result<SerialConnection, UsbError> {
        if !candidate.device.starts_with("/dev/cu.") || !candidate.stable {
            return Err(UsbError::CandidateUnstable);
        }
        if !candidate.exact_descriptor() {
            return Err(UsbError::CandidateMissing);
        }
        #[cfg(target_os = "macos")]
        {
            tokio_serial::new(candidate.device.clone(), 115_200)
                .timeout(Duration::from_millis(200))
                .open_native_async()
                .map(|stream| Box::new(stream) as SerialConnection)
                .map_err(|error| map_serial_error(&error))
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = candidate;
            Err(UsbError::OpenFailed)
        }
    }
}

pub fn map_io_error(error: &io::Error) -> UsbError {
    match error.kind() {
        io::ErrorKind::PermissionDenied => UsbError::PermissionDenied,
        io::ErrorKind::NotFound => UsbError::OpenFailed,
        io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut => UsbError::Timeout,
        _ => UsbError::Io,
    }
}

#[cfg(target_os = "macos")]
fn map_serial_error(error: &serialport::Error) -> UsbError {
    match error.kind {
        serialport::ErrorKind::NoDevice => UsbError::OpenFailed,
        serialport::ErrorKind::Io(io_kind) if io_kind == io::ErrorKind::PermissionDenied => UsbError::PermissionDenied,
        serialport::ErrorKind::Io(io_kind) if io_kind == io::ErrorKind::TimedOut => UsbError::Timeout,
        _ => UsbError::OpenFailed,
    }
}

pub fn measured_tuple(candidate: &DeviceCandidate) -> bool {
    candidate.vid == Some(EXPECTED_VID)
        && candidate.pid == Some(EXPECTED_PID)
        && candidate.serial_number.as_deref() == Some(EXPECTED_SERIAL)
        && candidate.interface.as_deref() == Some(EXPECTED_CDC_INTERFACE)
        && candidate.stable
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_mapping_is_safe_and_platform_neutral() {
        let exact = MacRegistryRecord {
            vendor_id: Some(EXPECTED_VID), product_id: Some(EXPECTED_PID),
            serial_number: Some("8CBFEA0DCBFC".to_string()), interface: Some("if01".to_string()),
            location: Some("IOUSBInterface-01".to_string()), ..Default::default()
        };
        assert_eq!(normalize_registry(&exact).safe_code, "exact");
        let wrong = MacRegistryRecord { interface: Some("if00".to_string()), ..exact.clone() };
        assert_eq!(normalize_registry(&wrong).safe_code, "wrong_interface");
        let lookalike = MacRegistryRecord { serial_number: Some("lookalike".to_string()), ..exact.clone() };
        assert_eq!(normalize_registry(&lookalike).safe_code, "lookalike");
        let denied = MacRegistryRecord { permission: Some("denied".to_string()), ..exact };
        assert_eq!(normalize_registry(&denied).safe_code, "permission_denied");
    }

    #[test]
    fn duplicate_exact_registry_services_are_ambiguous() {
        let record = MacRegistryRecord {
            vendor_id: Some(EXPECTED_VID), product_id: Some(EXPECTED_PID),
            serial_number: Some(EXPECTED_SERIAL.to_string()), interface: Some("if01".to_string()), ..Default::default()
        };
        let result = normalize_registry_snapshot(&[record.clone(), record]);
        assert!(result.iter().all(|outcome| outcome.safe_code == "ambiguous"));
    }

    #[tokio::test]
    async fn suspend_notification_is_process_local() {
        let platform = MacOsPlatform::new();
        let mut receiver = platform.subscribe_suspend();
        platform.notify_suspend();
        assert!(receiver.recv().await.is_ok());
    }
}
