use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, DuplexStream};

#[path = "../src/ports/usb.rs"]
pub mod usb;
pub mod ports {
    pub use crate::usb;
}
#[path = "../src/platform/linux.rs"]
pub mod linux;
#[path = "../src/platform/macos.rs"]
pub mod macos;

use linux::LinuxPortMetadata;
use macos::{normalize_registry_snapshot, MacRegistryRecord};
use usb::{DeviceCandidate, PlatformSerial, SerialConnection, UsbError, UsbEvent, UsbPort, EXPECTED_CDC_INTERFACE, EXPECTED_PID, EXPECTED_SERIAL, EXPECTED_VID};

#[derive(Clone)]
struct FakePlatform {
    candidates: Vec<DeviceCandidate>,
    streams: Arc<Mutex<VecDeque<DuplexStream>>>,
}

impl PlatformSerial for FakePlatform {
    fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError> {
        Ok(self.candidates.clone())
    }

    fn open(&self, candidate: &DeviceCandidate) -> Result<SerialConnection, UsbError> {
        if !candidate.admissible() {
            return Err(UsbError::CandidateMissing);
        }
        self.streams
            .lock()
            .expect("fake stream queue")
            .pop_front()
            .map(|stream| Box::new(stream) as SerialConnection)
            .ok_or(UsbError::OpenFailed)
    }
}

#[derive(Clone, Copy)]
enum HelloMode {
    Matching,
    WrongDevice,
    WrongSession,
    StaleSequence,
    FocusBeforeAck,
}

fn exact_candidate(endpoint: &str) -> DeviceCandidate {
    DeviceCandidate {
        device: endpoint.to_string(),
        vid: Some(EXPECTED_VID),
        pid: Some(EXPECTED_PID),
        serial_number: Some(EXPECTED_SERIAL.to_string()),
        location: Some("1-1:1.1".to_string()),
        manufacturer: Some("Espressif".to_string()),
        product: Some("USB composite CDC + keyboard".to_string()),
        interface: Some(EXPECTED_CDC_INTERFACE.to_string()),
        stable: true,
    }
}

fn make_platform(mode: HelloMode, endpoint: &str) -> (FakePlatform, tokio::task::JoinHandle<()>) {
    let (host, device) = tokio::io::duplex(16 * 1024);
    let platform = FakePlatform {
        candidates: vec![exact_candidate(endpoint)],
        streams: Arc::new(Mutex::new(VecDeque::from([host]))),
    };
    let server = tokio::spawn(async move { fake_device(device, mode).await });
    (platform, server)
}

async fn fake_device(stream: DuplexStream, mode: HelloMode) {
    let (read_half, mut write_half) = tokio::io::split(stream);
    let mut lines = BufReader::new(read_half).lines();
    let Ok(Some(hello_line)) = lines.next_line().await else { return };
    let Ok(hello): Result<Value, _> = serde_json::from_str(&hello_line) else { return };
    let session = hello.get("session_id").and_then(Value::as_str).unwrap_or("session");
    let hello_session = if matches!(mode, HelloMode::WrongSession) { "stale-session" } else { session };
    let device_id = if matches!(mode, HelloMode::WrongDevice) { "lookalike-device" } else { "paired-device" };
    let hello_seq = if matches!(mode, HelloMode::StaleSequence) { 0 } else { 1 };
    let boot_id = "device-boot-1";
    let hello_ack = frame(
        1,
        "hello_ack",
        boot_id,
        hello_session,
        hello_seq,
        Some(1),
        json!({"accepted":true,"device_id":device_id,"firmware":"phase1-bringup","protocol":1}),
    );
    let _ = write_json(&mut write_half, hello_ack).await;
    if !matches!(mode, HelloMode::Matching | HelloMode::FocusBeforeAck) {
        return;
    }
    let Ok(Some(snapshot_line)) = lines.next_line().await else { return };
    let Ok(snapshot): Result<Value, _> = serde_json::from_str(&snapshot_line) else { return };
    let snapshot_payload = snapshot.get("payload").cloned().unwrap_or_default();
    if matches!(mode, HelloMode::FocusBeforeAck) {
        let intent = frame(2, "focus_intent", boot_id, session, 2, None, json!({"action_id":"queued"}));
        let _ = write_json(&mut write_half, intent).await;
    }
    let sequence = if matches!(mode, HelloMode::FocusBeforeAck) { 3 } else { 2 };
    let ack = frame(
        2,
        "snapshot_ack",
        boot_id,
        session,
        sequence,
        snapshot.get("seq").and_then(Value::as_u64),
        json!({
            "accepted":true,
            "host_epoch":snapshot_payload.get("host_epoch").and_then(Value::as_str).unwrap_or("epoch"),
            "snapshot_revision":snapshot_payload.get("snapshot_revision").and_then(Value::as_u64).unwrap_or(1),
            "source_status":snapshot_payload.get("source_status").and_then(Value::as_str).unwrap_or("empty"),
            "reason":"committed"
        }),
    );
    let _ = write_json(&mut write_half, ack).await;
}

async fn write_json(writer: &mut (impl tokio::io::AsyncWrite + Unpin), value: Value) -> std::io::Result<()> {
    let mut line = serde_json::to_vec(&value).expect("fake frame JSON");
    line.push(b'\n');
    writer.write_all(&line).await
}

fn frame(version: u64, frame_type: &str, boot_id: &str, session_id: &str, seq: u64, reply_to: Option<u64>, payload: Value) -> Value {
    json!({
        "v":version,"type":frame_type,"boot_id":boot_id,"session_id":session_id,"seq":seq,
        "reply_to":reply_to,"digest":digest(&payload),"payload":payload
    })
}

fn digest(value: &Value) -> String {
    let mut bytes = Vec::new();
    canonical(value, &mut bytes);
    let mut result = 0xcbf29ce484222325u64;
    for byte in bytes {
        result ^= u64::from(byte);
        result = result.wrapping_mul(0x100000001b3);
    }
    format!("{result:016x}")
}

fn canonical(value: &Value, output: &mut Vec<u8>) {
    match value {
        Value::Null => output.extend_from_slice(b"null"),
        Value::Bool(value) => output.extend_from_slice(if *value { b"true" } else { b"false" }),
        Value::Number(value) => output.extend_from_slice(value.to_string().as_bytes()),
        Value::String(value) => output.extend_from_slice(serde_json::to_string(value).unwrap().as_bytes()),
        Value::Array(values) => {
            output.push(b'[');
            for (index, child) in values.iter().enumerate() {
                if index != 0 { output.push(b','); }
                canonical(child, output);
            }
            output.push(b']');
        }
        Value::Object(values) => {
            output.push(b'{');
            let mut keys: Vec<&String> = values.keys().collect();
            keys.sort();
            for (index, key) in keys.into_iter().enumerate() {
                if index != 0 { output.push(b','); }
                output.extend_from_slice(serde_json::to_string(key).unwrap().as_bytes());
                output.push(b':');
                canonical(&values[key], output);
            }
            output.push(b'}');
        }
    }
}

struct TestDir(std::path::PathBuf);

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn binding_path(name: &str) -> (TestDir, std::path::PathBuf) {
    let suffix = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let directory = std::env::temp_dir().join(format!("herdr-keypad-usb-{}-{suffix}", std::process::id()));
    std::fs::create_dir(&directory).expect("temporary binding directory");
    let path = directory.join(name);
    std::fs::write(&path, br#"{"schema_version":1,"device_id":"paired-device","protocol":1,"firmware":"phase1-bringup"}
"#).expect("binding fixture");
    (TestDir(directory), path)
}

#[test]
fn linux_exact_descriptor_filter_rejects_lookalikes_wrong_interface_and_transient_paths() {
    let records = [
        LinuxPortMetadata { device:"/dev/serial/by-id/usb-herdr".into(), vid:Some(EXPECTED_VID), pid:Some(EXPECTED_PID), serial_number:Some("8CBFEA0DCBFC".into()), location:Some("1-1:1.1".into()), manufacturer:None, product:None, interface:Some("if01".into()) },
        LinuxPortMetadata { device:"/dev/serial/by-id/usb-lookalike".into(), vid:Some(EXPECTED_VID), pid:Some(EXPECTED_PID), serial_number:Some("lookalike".into()), location:Some("1-1:1.1".into()), manufacturer:None, product:None, interface:Some("if01".into()) },
        LinuxPortMetadata { device:"/dev/serial/by-id/usb-wrong-interface".into(), vid:Some(EXPECTED_VID), pid:Some(EXPECTED_PID), serial_number:Some(EXPECTED_SERIAL.into()), location:Some("1-1:1.0".into()), manufacturer:None, product:None, interface:Some("if00".into()) },
        LinuxPortMetadata { device:"/dev/ttyACM0".into(), vid:Some(EXPECTED_VID), pid:Some(EXPECTED_PID), serial_number:Some(EXPECTED_SERIAL.into()), location:Some("1-1:1.1".into()), manufacturer:None, product:None, interface:Some("if01".into()) },
    ];
    let candidates = linux::LinuxPlatform::new().enumerate_metadata(records);
    assert_eq!(candidates.len(), 1);
    assert_eq!(candidates[0].device, "/dev/serial/by-id/usb-herdr");
}

#[tokio::test]
async fn exact_hello_then_snapshot_ack_gates_readiness_and_close_clears_focus() {
    let (_directory, binding) = binding_path("binding.json");
    let (platform, server) = make_platform(HelloMode::FocusBeforeAck, "/dev/serial/by-id/usb-herdr");
    let mut port = UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(250));
    assert!(matches!(port.connect().await.unwrap(), UsbEvent::Connected { .. }));
    assert!(!port.ready());
    let ack = port.publish_snapshot(json!({"host_epoch":"epoch","snapshot_revision":1,"source_status":"empty"})).await.unwrap();
    assert!(ack.accepted);
    assert!(port.ready());
    assert_eq!(port.pending_focus_count(), 1);
    port.close();
    assert!(!port.connected());
    assert!(!port.ready());
    assert_eq!(port.pending_focus_count(), 0);
    server.await.unwrap();
}

#[tokio::test]
async fn malformed_binding_is_unchanged_and_prevents_any_candidate_open() {
    let (_directory, path) = binding_path("binding.json");
    let original = br#"{"schema_version":1,"device_id":"paired-device","protocol":2,"firmware":"phase1-bringup"}
"#;
    std::fs::write(&path, original).unwrap();
    let (platform, server) = make_platform(HelloMode::Matching, "/dev/serial/by-id/usb-herdr");
    let mut port = UsbPort::new(Box::new(platform.clone()), path.clone());
    assert_eq!(port.connect().await.unwrap_err(), UsbError::BindingIncompatible);
    assert_eq!(std::fs::read(&path).unwrap(), original);
    drop(port);
    server.abort();
    let _ = server.await;
}

#[tokio::test]
async fn stale_hello_session_and_identity_fail_closed() {
    for mode in [HelloMode::WrongDevice, HelloMode::WrongSession, HelloMode::StaleSequence] {
        let (_directory, binding) = binding_path("binding.json");
        let (platform, server) = make_platform(mode, "/dev/serial/by-id/usb-herdr");
        let mut port = UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(100));
        assert!(port.connect().await.is_err());
        assert!(!port.connected());
        server.await.unwrap();
    }
}

#[test]
fn linux_udev_shape_is_not_broadened_by_adapter() {
    let candidate = linux::normalize_metadata(LinuxPortMetadata {
        device: "/dev/serial/by-id/usb-herdr".into(), vid:Some(EXPECTED_VID), pid:Some(EXPECTED_PID),
        serial_number:Some(EXPECTED_SERIAL.into()), location:Some("1-1:1.1".into()),
        manufacturer:None, product:None, interface:Some("if01".into()),
    });
    assert!(candidate.exact_descriptor());
    assert!(candidate.stable);
    assert!(!DeviceCandidate::exact("/dev/ttyACM0", EXPECTED_SERIAL, EXPECTED_CDC_INTERFACE).admissible());
}

#[derive(Debug, Deserialize)]
struct Fixture {
    schema_version: u64,
    cases: Vec<FixtureCase>,
}

#[derive(Debug, Deserialize)]
struct FixtureCase {
    name: String,
    records: Vec<MacRegistryRecord>,
    expected_codes: Vec<String>,
}

fn fixture() -> Fixture {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/macos-serial.json");
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

#[test]
fn macos_fixture_registry_cases_map_to_safe_codes() {
    let fixture = fixture();
    assert_eq!(fixture.schema_version, 1);
    for case in fixture.cases {
        let outcomes = normalize_registry_snapshot(&case.records);
        let actual: Vec<&str> = outcomes.iter().map(|outcome| outcome.safe_code).collect();
        let expected: Vec<&str> = case.expected_codes.iter().map(String::as_str).collect();
        assert_eq!(actual, expected, "fixture case {}", case.name);
    }
}

#[test]
fn macos_fixture_exact_descriptor_requires_hello_after_candidate_gate() {
    let record = MacRegistryRecord {
        vendor_id: Some(EXPECTED_VID),
        product_id: Some(EXPECTED_PID),
        serial_number: Some(EXPECTED_SERIAL.into()),
        interface: Some("if01".into()),
        location: Some("IOUSBInterface-01".into()),
        ..Default::default()
    };
    let outcome = macos::normalize_registry(&record);
    assert_eq!(outcome.safe_code, "exact");
    assert!(!outcome.candidate.admissible(), "fixture metadata cannot authorize or open a host path");
}

#[test]
fn macos_fixture_contains_no_host_paths_or_application_identity() {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/macos-serial.json");
    let text = std::fs::read_to_string(path).unwrap();
    assert!(!text.contains("/dev/"));
    assert!(!text.contains("device_id"));
    assert!(!text.contains("firmware"));
}
