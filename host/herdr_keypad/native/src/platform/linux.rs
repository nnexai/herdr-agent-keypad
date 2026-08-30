//! Linux-only USB metadata normalization and serial opening.
//!
//! Descriptor facts narrow candidates but never authorize the application.  The
//! stable `/dev/serial/by-id/` endpoint and measured CDC interface are retained
//! so [`crate::ports::usb::UsbPort`] can perform the fresh hello gate.

use crate::ports::usb::{canonical_interface, canonical_serial, endpoint_is_stable, DeviceCandidate, PlatformSerial, SerialConnection, UsbError, EXPECTED_CDC_INTERFACE, EXPECTED_PID, EXPECTED_SERIAL, EXPECTED_VID};
use serialport::{SerialPortInfo, SerialPortType};
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio_serial::SerialPortBuilderExt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LinuxPortMetadata {
    pub device: String,
    pub vid: Option<u16>,
    pub pid: Option<u16>,
    pub serial_number: Option<String>,
    pub location: Option<String>,
    pub manufacturer: Option<String>,
    pub product: Option<String>,
    pub interface: Option<String>,
}

pub fn normalize_metadata(metadata: LinuxPortMetadata) -> DeviceCandidate {
    let interface = canonical_interface(metadata.interface.as_deref().unwrap_or(""), metadata.location.as_deref());
    DeviceCandidate {
        stable: endpoint_is_stable(&metadata.device),
        device: metadata.device,
        vid: metadata.vid,
        pid: metadata.pid,
        serial_number: metadata.serial_number.as_deref().and_then(canonical_serial),
        location: metadata.location,
        manufacturer: metadata.manufacturer,
        product: metadata.product,
        interface,
    }
}

/// Return all normalized USB descriptors.  Non-USB serial functions are
/// omitted; exact descriptor and application identity checks remain in UsbPort.
pub fn normalize_serial_ports(ports: &[SerialPortInfo]) -> Vec<DeviceCandidate> {
    normalize_serial_ports_in(ports, Path::new("/dev/serial/by-id"))
}

pub(crate) fn normalize_serial_ports_in(ports: &[SerialPortInfo], by_id: &Path) -> Vec<DeviceCandidate> {
    ports
        .iter()
        .filter_map(|port| match &port.port_type {
            SerialPortType::UsbPort(usb) => {
                let stable = resolve_stable_endpoint_in(Path::new(&port.port_name), by_id);
                let device = stable.as_ref().and_then(|path| path.to_str()).unwrap_or(&port.port_name);
                let interface = discover_interface_number(&port.port_name)
                    .or_else(|| stable.as_deref().and_then(interface_from_by_id));
                let mut candidate = normalize_metadata(LinuxPortMetadata {
                    device: device.to_owned(),
                    vid: Some(usb.vid),
                    pid: Some(usb.pid),
                    serial_number: usb.serial_number.clone(),
                    location: None,
                    manufacturer: usb.manufacturer.clone(),
                    product: usb.product.clone(),
                    interface,
                });
                candidate.stable |= stable.is_some();
                Some(candidate)
            }
            _ => None,
        })
        .filter(DeviceCandidate::admissible)
        .collect()
}

pub(crate) fn resolve_stable_endpoint_in(device: &Path, by_id: &Path) -> Option<PathBuf> {
    let target = std::fs::canonicalize(device).ok()?;
    let entries = std::fs::read_dir(by_id).ok()?;
    let mut matched = None;
    for entry in entries {
        let Ok(entry) = entry else { continue };
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if !name.ends_with("-if01") || !entry.file_type().is_ok_and(|kind| kind.is_symlink()) {
            continue;
        }
        if std::fs::canonicalize(&path).ok().as_ref() != Some(&target) {
            continue;
        }
        if matched.is_some() {
            return None;
        }
        matched = Some(path);
    }
    matched
}

fn interface_from_by_id(path: &Path) -> Option<String> {
    let name = path.file_name()?.to_str()?;
    name.strip_suffix("-if01").map(|_| EXPECTED_CDC_INTERFACE.to_owned())
}

/// `serialport` exposes USB VID/PID/serial fields but not the composite
/// interface number. Read the kernel's class attribute rather than guessing
/// from tty enumeration order.
fn discover_interface_number(device: &str) -> Option<String> {
    let path = std::path::Path::new(device);
    let names = [
        path.file_name().and_then(|name| name.to_str()).map(str::to_string),
        std::fs::canonicalize(path).ok().and_then(|resolved| resolved.file_name().and_then(|name| name.to_str()).map(str::to_string)),
    ];
    names.into_iter().flatten().find_map(|name| {
        let paths = [
            format!("/sys/class/tty/{name}/device/bInterfaceNumber"),
            format!("/sys/class/tty/{name}/device/../bInterfaceNumber"),
        ];
        paths.iter().find_map(|path| {
            let value = std::fs::read_to_string(path).ok()?;
            let value = value.trim();
            if value.is_empty() { None } else { Some(value.to_string()) }
        })
    })
}

pub fn exact_candidates(candidates: impl IntoIterator<Item = DeviceCandidate>) -> Vec<DeviceCandidate> {
    candidates.into_iter().filter(DeviceCandidate::admissible).collect()
}

#[derive(Debug, Default, Clone, Copy)]
pub struct LinuxPlatform;

impl LinuxPlatform {
    pub fn new() -> Self { Self }

    pub fn enumerate_metadata(&self, metadata: impl IntoIterator<Item = LinuxPortMetadata>) -> Vec<DeviceCandidate> {
        exact_candidates(metadata.into_iter().map(normalize_metadata))
    }
}

impl PlatformSerial for LinuxPlatform {
    fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError> {
        let ports = serialport::available_ports().map_err(|_| UsbError::Io)?;
        Ok(normalize_serial_ports(&ports))
    }

    fn open(&self, candidate: &DeviceCandidate) -> Result<SerialConnection, UsbError> {
        if !candidate.stable {
            return Err(UsbError::CandidateUnstable);
        }
        if !candidate.exact_descriptor() {
            return Err(UsbError::CandidateMissing);
        }
        tokio_serial::new(candidate.device.clone(), 115_200)
            .timeout(Duration::from_millis(200))
            .open_native_async()
            .map(|stream| Box::new(stream) as SerialConnection)
            .map_err(|error| match error.kind {
                serialport::ErrorKind::NoDevice => UsbError::OpenFailed,
                serialport::ErrorKind::Io(io_kind) if io_kind == std::io::ErrorKind::PermissionDenied => UsbError::PermissionDenied,
                _ => UsbError::OpenFailed,
            })
    }
}

pub fn measured_tuple(candidate: &DeviceCandidate) -> bool {
    candidate.vid == Some(EXPECTED_VID)
        && candidate.pid == Some(EXPECTED_PID)
        && candidate.serial_number.as_deref() == Some(EXPECTED_SERIAL)
        && candidate.interface.as_deref() == Some(EXPECTED_CDC_INTERFACE)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn metadata(device: &str, serial: &str, interface: &str, location: Option<&str>) -> LinuxPortMetadata {
        LinuxPortMetadata {
            device: device.to_string(), vid: Some(EXPECTED_VID), pid: Some(EXPECTED_PID),
            serial_number: Some(serial.to_string()), location: location.map(str::to_string),
            manufacturer: Some("Espressif".to_string()), product: Some("USB composite CDC + keyboard".to_string()),
            interface: Some(interface.to_string()),
        }
    }

    #[test]
    fn normalization_requires_measured_composite_function_and_stable_path() {
        let exact = normalize_metadata(metadata("/dev/serial/by-id/usb-herdr", "8CBFEA0DCBFC", "if01", Some("1-1:1.1")));
        assert!(exact.admissible());
        assert!(measured_tuple(&exact));
        let transient = normalize_metadata(metadata("/dev/ttyACM0", EXPECTED_SERIAL, "if01", Some("1-1:1.1")));
        assert!(!transient.admissible());
        let wrong_interface = normalize_metadata(metadata("/dev/serial/by-id/usb-herdr", EXPECTED_SERIAL, "if00", Some("1-1:1.0")));
        assert!(!wrong_interface.admissible());
        let disagreement = normalize_metadata(metadata("/dev/serial/by-id/usb-herdr", EXPECTED_SERIAL, "if00", Some("1-1:1.1")));
        assert!(!disagreement.admissible());
    }

    #[test]
    fn ambiguous_exact_descriptors_are_not_collapsed_by_first_match() {
        let records = [
            metadata("/dev/serial/by-id/usb-herdr-a", EXPECTED_SERIAL, "if01", None),
            metadata("/dev/serial/by-id/usb-herdr-b", EXPECTED_SERIAL, "if01", None),
        ];
        assert_eq!(exact_candidates(records.into_iter().map(normalize_metadata)).len(), 2);
    }
}
