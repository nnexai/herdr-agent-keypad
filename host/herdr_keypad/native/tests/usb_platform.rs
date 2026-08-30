use serde::Deserialize;
use serialport::{SerialPortInfo, SerialPortType, UsbPortInfo};
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
    FocusUntilResultThenAck,
    CloseAfterHello,
    MalformedAfterHello,
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
    if matches!(mode, HelloMode::CloseAfterHello) {
        return;
    }
    if matches!(mode, HelloMode::MalformedAfterHello) {
        let _ = write_half.write_all(b"not-json\n").await;
        return;
    }
    if !matches!(mode, HelloMode::Matching | HelloMode::FocusBeforeAck | HelloMode::FocusUntilResultThenAck) {
        return;
    }
    let Ok(Some(snapshot_line)) = lines.next_line().await else { return };
    let Ok(snapshot): Result<Value, _> = serde_json::from_str(&snapshot_line) else { return };
    let snapshot_payload = snapshot.get("payload").cloned().unwrap_or_default();
    if matches!(mode, HelloMode::FocusBeforeAck | HelloMode::FocusUntilResultThenAck) {
        let intent = frame(
            2,
            "focus_intent",
            boot_id,
            session,
            2,
            None,
            json!({"action_id":"queued"}),
        );
        let _ = write_json(&mut write_half, intent).await;
    }
    if matches!(mode, HelloMode::FocusUntilResultThenAck) {
        let Ok(Some(result_line)) = lines.next_line().await else {
            return;
        };
        let Ok(result): Result<Value, _> = serde_json::from_str(&result_line) else {
            return;
        };
        assert_eq!(result.get("type").and_then(Value::as_str), Some("focus_result"));
    }
    let sequence = if matches!(mode, HelloMode::FocusBeforeAck | HelloMode::FocusUntilResultThenAck) {
        3
    } else {
        2
    };
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

fn make_split_focus_platform(
    endpoint: &str,
    split_delay: Duration,
) -> (FakePlatform, tokio::task::JoinHandle<()>) {
    let (host, device) = tokio::io::duplex(16 * 1024);
    let platform = FakePlatform {
        candidates: vec![exact_candidate(endpoint)],
        streams: Arc::new(Mutex::new(VecDeque::from([host]))),
    };
    let server = tokio::spawn(async move {
        let (read_half, mut write_half) = tokio::io::split(device);
        let mut lines = BufReader::new(read_half).lines();
        let hello_line = lines
            .next_line()
            .await
            .expect("hello read")
            .expect("hello line");
        let hello: Value = serde_json::from_str(&hello_line).expect("hello JSON");
        let session = hello["session_id"].as_str().expect("session").to_owned();
        write_json(
            &mut write_half,
            frame(
                1,
                "hello_ack",
                "device-boot-1",
                &session,
                1,
                Some(1),
                json!({
                    "accepted":true,
                    "device_id":"paired-device",
                    "firmware":"phase1-bringup",
                    "protocol":1
                }),
            ),
        )
        .await
        .expect("hello ACK");

        let focus = frame(
            2,
            "focus_intent",
            "device-boot-1",
            &session,
            2,
            None,
            json!({"action_id":"split"}),
        );
        let mut encoded = serde_json::to_vec(&focus).expect("focus JSON");
        encoded.push(b'\n');
        let split = encoded.len() / 2;
        write_half
            .write_all(&encoded[..split])
            .await
            .expect("focus prefix");
        tokio::time::sleep(split_delay).await;
        write_half
            .write_all(&encoded[split..])
            .await
            .expect("focus suffix");
    });
    (platform, server)
}
async fn fake_device_reconnect(stream: DuplexStream, old_session: String) {
    let (read_half, mut write_half) = tokio::io::split(stream);
    let mut lines = BufReader::new(read_half).lines();
    let Ok(Some(hello_line)) = lines.next_line().await else { return };
    let Ok(hello): Result<Value, _> = serde_json::from_str(&hello_line) else { return };
    let session = hello.get("session_id").and_then(Value::as_str).unwrap_or("session");
    assert_ne!(session, old_session);
    let boot_id = "device-boot-1";
    let hello_ack = frame(
        1,
        "hello_ack",
        boot_id,
        session,
        1,
        Some(1),
        json!({"accepted":true,"device_id":"paired-device","firmware":"phase1-bringup","protocol":1}),
    );
    let _ = write_json(&mut write_half, hello_ack).await;
    let Ok(Some(snapshot_line)) = lines.next_line().await else { return };
    let Ok(snapshot): Result<Value, _> = serde_json::from_str(&snapshot_line) else { return };
    let snapshot_payload = snapshot.get("payload").cloned().unwrap_or_default();
    let ack = frame(
        2,
        "snapshot_ack",
        boot_id,
        session,
        2,
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
    let stale = frame(2, "focus_intent", boot_id, &old_session, 3, None, json!({"action_id":"stale"}));
    let _ = write_json(&mut write_half, stale).await;
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

#[cfg(unix)]
#[test]
fn linux_transient_enumeration_resolves_one_exact_stable_by_id_alias() {
    use std::os::unix::fs::symlink;

    let suffix = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let root = std::env::temp_dir().join(format!("herdr-keypad-by-id-{}-{suffix}", std::process::id()));
    let _directory = TestDir(root.clone());
    let by_id = root.join("by-id");
    std::fs::create_dir_all(&by_id).expect("by-id fixture");
    let transient = root.join("ttyACM0");
    std::fs::write(&transient, []).expect("transient tty fixture");
    let stable = by_id.join("usb-Espressif_exact-if01");
    symlink("../ttyACM0", &stable).expect("stable alias fixture");
    let port = SerialPortInfo {
        port_name: transient.to_string_lossy().into_owned(),
        port_type: SerialPortType::UsbPort(UsbPortInfo {
            vid: EXPECTED_VID,
            pid: EXPECTED_PID,
            serial_number: Some(EXPECTED_SERIAL.to_owned()),
            manufacturer: Some("Espressif".to_owned()),
            product: Some("TinyUSB CDC".to_owned()),
        }),
    };

    let candidates = linux::normalize_serial_ports_in(&[port.clone()], &by_id);
    assert_eq!(candidates.len(), 1);
    assert_eq!(candidates[0].device, stable.to_string_lossy());
    assert!(candidates[0].admissible());

    symlink("../ttyACM0", by_id.join("usb-Espressif_duplicate-if01")).expect("duplicate alias fixture");
    assert!(linux::normalize_serial_ports_in(&[port], &by_id).is_empty());
}

#[tokio::test]
async fn exact_hello_then_snapshot_ack_preserves_focus_and_reply_fences() {
    let (_directory, binding) = binding_path("binding.json");
    let (platform, server) =
        make_platform(HelloMode::FocusBeforeAck, "/dev/serial/by-id/usb-herdr");
    let mut port =
        UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(250));
    assert!(matches!(
        port.connect().await.unwrap(),
        UsbEvent::Connected { .. }
    ));
    let request = port
        .send_snapshot(json!({"host_epoch":"epoch","snapshot_revision":1,"source_status":"empty"}))
        .await
        .unwrap();
    assert!(matches!(
        port.poll().await.unwrap(),
        Some(UsbEvent::FocusIntent(_))
    ));
    let Some(UsbEvent::SnapshotAck(ack)) = port.poll().await.unwrap() else {
        panic!("snapshot ACK missing");
    };
    assert!(ack.accepted);
    assert_eq!(ack.reply_to, request);
    port.close();
    assert!(!port.connected());
    server.await.unwrap();
}

#[tokio::test]
async fn snapshot_publication_does_not_starve_focus_while_ack_is_pending() {
    let (_directory, binding) = binding_path("binding.json");
    let (platform, server) =
        make_platform(HelloMode::FocusUntilResultThenAck, "/dev/serial/by-id/usb-herdr");
    let mut port =
        UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(250));
    assert!(matches!(
        port.connect().await.unwrap(),
        UsbEvent::Connected { .. }
    ));

    tokio::time::timeout(
        Duration::from_millis(50),
        port.send_snapshot(json!({
            "host_epoch":"epoch",
            "snapshot_revision":1,
            "source_status":"current"
        })),
    )
    .await
    .expect("snapshot send waited for its ACK and monopolized event-loop ingress")
    .expect("snapshot send");

    let focus = port.poll().await.expect("focus poll").expect("focus event");
    assert!(matches!(focus, UsbEvent::FocusIntent(_)));
    port.send_focus_result(json!({"action_id":"queued","outcome":"accepted"}))
        .await
        .expect("focus result send");
    let ack = port.poll().await.expect("ACK poll").expect("ACK event");
    assert!(matches!(ack, UsbEvent::SnapshotAck(_)));
    server.await.expect("fake device");
}

#[tokio::test]
async fn cancelled_poll_preserves_a_split_focus_frame_for_resume() {
    let (_directory, binding) = binding_path("binding.json");
    let (platform, server) = make_split_focus_platform(
        "/dev/serial/by-id/usb-herdr",
        Duration::from_millis(75),
    );
    let mut port =
        UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(250));
    assert!(matches!(
        port.connect().await.unwrap(),
        UsbEvent::Connected { .. }
    ));

    assert!(
        tokio::time::timeout(Duration::from_millis(25), port.poll())
            .await
            .is_err(),
        "the first poll should be interrupted after consuming only the frame prefix"
    );
    let resumed = port
        .poll()
        .await
        .expect("resumed poll must retain the prefix")
        .expect("split focus event");
    assert!(matches!(resumed, UsbEvent::FocusIntent(_)));
    assert!(port.connected(), "cancellation must not reset the authorized session");
    server.await.expect("split fake device");
}

#[tokio::test]
async fn idle_poll_timeout_preserves_connected_session_and_partial_frame() {
    let (_directory, binding) = binding_path("binding.json");
    let (platform, server) = make_split_focus_platform(
        "/dev/serial/by-id/usb-herdr",
        Duration::from_millis(40),
    );
    let mut port =
        UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(25));
    assert!(matches!(
        port.connect().await.unwrap(),
        UsbEvent::Connected { .. }
    ));
    let session_before = port.session_identity().map(|(boot, session)| {
        (boot.to_owned(), session.to_owned())
    });

    assert_eq!(
        port.poll().await,
        Ok(None),
        "an internal idle read deadline is not a link failure or an event"
    );
    assert!(port.connected(), "idle timeout must retain link authority");
    assert_eq!(
        port.session_identity().map(|(boot, session)| {
            (boot.to_owned(), session.to_owned())
        }),
        session_before,
        "idle timeout must retain the authorized session"
    );

    let resumed = port
        .poll()
        .await
        .expect("resumed poll must retain the prefix")
        .expect("split focus event");
    assert!(matches!(resumed, UsbEvent::FocusIntent(_)));
    assert!(port.connected());
    server.await.expect("split fake device");
}

#[tokio::test]
async fn real_eof_and_protocol_failures_reset_the_connected_session() {
    for (name, mode, expected) in [
        ("eof-binding.json", HelloMode::CloseAfterHello, UsbError::Io),
        (
            "protocol-binding.json",
            HelloMode::MalformedAfterHello,
            UsbError::Protocol,
        ),
    ] {
        let (_directory, binding) = binding_path(name);
        let (platform, server) =
            make_platform(mode, "/dev/serial/by-id/usb-herdr");
        let mut port = UsbPort::new(Box::new(platform), binding)
            .with_timeout(Duration::from_millis(250));
        assert!(matches!(
            port.connect().await.unwrap(),
            UsbEvent::Connected { .. }
        ));

        assert_eq!(port.poll().await, Err(expected));
        assert!(
            !port.connected(),
            "real read and protocol failures must discard session authority"
        );
        assert_eq!(port.session_identity(), None);
        server.await.expect("failure fake device");
    }
}
#[tokio::test]
async fn same_boot_id_reconnects_with_fresh_host_session_and_rejects_old_frames() {
    let (_directory, binding) = binding_path("binding.json");
    let (first_host, first_device) = tokio::io::duplex(16 * 1024);
    let (second_host, second_device) = tokio::io::duplex(16 * 1024);
    let platform = FakePlatform {
        candidates: vec![exact_candidate("/dev/serial/by-id/usb-herdr")],
        streams: Arc::new(Mutex::new(VecDeque::from([first_host, second_host]))),
    };
    let first_server = tokio::spawn(async move { fake_device(first_device, HelloMode::Matching).await });
    let mut port = UsbPort::new(Box::new(platform), binding).with_timeout(Duration::from_millis(250));

    let (first_boot, old_session) = match port.connect().await.unwrap() {
        UsbEvent::Connected { boot_id, session_id, .. } => (boot_id, session_id),
        event => panic!("unexpected first event: {event:?}"),
    };
    port.close();
    first_server.await.unwrap();

    let second_server = tokio::spawn(fake_device_reconnect(second_device, old_session.clone()));
    let (second_boot, new_session) = match port.connect().await.unwrap() {
        UsbEvent::Connected { boot_id, session_id, .. } => (boot_id, session_id),
        event => panic!("unexpected reconnect event: {event:?}"),
    };
    assert_eq!(second_boot, first_boot);
    assert_ne!(new_session, old_session);

    let request = port
        .send_snapshot(json!({"host_epoch":"reconnect-epoch","snapshot_revision":2,"source_status":"empty"}))
        .await
        .unwrap();
    let Some(UsbEvent::SnapshotAck(ack)) = port.poll().await.unwrap() else {
        panic!("reconnect snapshot ACK missing");
    };
    assert!(ack.accepted);
    assert_eq!(ack.reply_to, request);
    assert_eq!(port.poll().await.unwrap_err(), UsbError::SessionMismatch);
    assert!(!port.connected());
    second_server.await.unwrap();
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
