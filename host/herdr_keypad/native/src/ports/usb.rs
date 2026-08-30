//! Exact paired USB CDC transport.
//!
//! This module deliberately owns application/session authority rather than
//! treating an operating-system descriptor as authorization.  Platform
//! adapters only enumerate and open candidate serial functions; every stream
//! still has to pass the frozen binding and a fresh v1 application hello
//! before v2 frames are admitted.

use serde_json::{json, Map, Value};
use serde::de::{DeserializeSeed, Error as DeError, MapAccess, SeqAccess, Visitor};
use std::fmt;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::io::{AsyncBufRead, AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader};

pub const EXPECTED_VID: u16 = 0x303a;
pub const EXPECTED_PID: u16 = 0x1001;
pub const EXPECTED_SERIAL: &str = "8C:BF:EA:0D:CB:FC";
pub const EXPECTED_CDC_INTERFACE: &str = "01";
pub const APPLICATION_PROTOCOL: u64 = 1;
pub const DEVICE_PROTOCOL: u64 = 2;
pub const DEVICE_LINE_LIMIT: usize = 4_096;

/// A normalized descriptor snapshot.  `device` is a platform endpoint only;
/// it is never used as the pairing authority.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceCandidate {
    pub device: String,
    pub vid: Option<u16>,
    pub pid: Option<u16>,
    pub serial_number: Option<String>,
    pub location: Option<String>,
    pub manufacturer: Option<String>,
    pub product: Option<String>,
    pub interface: Option<String>,
    /// Platform adapters set this only for a stable, non-transient endpoint.
    pub stable: bool,
}

impl DeviceCandidate {
    pub fn exact(
        device: impl Into<String>,
        serial_number: impl Into<String>,
        interface: impl Into<String>,
    ) -> Self {
        let device = device.into();
        Self {
            stable: endpoint_is_stable(&device),
            device,
            vid: Some(EXPECTED_VID),
            pid: Some(EXPECTED_PID),
            serial_number: canonical_serial(&serial_number.into()),
            location: None,
            manufacturer: None,
            product: None,
            interface: canonical_interface(&interface.into(), None),
        }
    }

    pub fn exact_descriptor(&self) -> bool {
        self.vid == Some(EXPECTED_VID)
            && self.pid == Some(EXPECTED_PID)
            && self.serial_number.as_deref() == Some(EXPECTED_SERIAL)
            && self.interface.as_deref() == Some(EXPECTED_CDC_INTERFACE)
    }

    pub fn admissible(&self) -> bool {
        self.exact_descriptor() && self.stable
    }

    pub fn descriptor_tuple(&self) -> (&str, &str, &str) {
        (
            self.serial_number.as_deref().unwrap_or(""),
            self.interface.as_deref().unwrap_or(""),
            self.device.as_str(),
        )
    }
}

/// Normalize serial-number spellings emitted by pyserial/IOKit.
pub fn canonical_serial(value: &str) -> Option<String> {
    let compact: String = value
        .chars()
        .filter(|character| *character != ':' && *character != '-')
        .collect::<String>()
        .to_ascii_uppercase();
    if compact.len() == 12 && compact.chars().all(|character| character.is_ascii_hexdigit()) {
        Some(
            compact
                .as_bytes()
                .chunks(2)
                .map(|pair| String::from_utf8_lossy(pair).to_string())
                .collect::<Vec<_>>()
                .join(":"),
        )
    } else if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

/// Normalize `if01`, a numeric interface, or Linux's `bus:config.interface`
/// location.  A disagreement between explicit interface and location fails
/// closed rather than selecting the first spelling.
pub fn canonical_interface(interface: &str, location: Option<&str>) -> Option<String> {
    let explicit = interface_number(interface);
    let from_location = location.and_then(interface_number);
    match (explicit, from_location) {
        (Some(left), Some(right)) if left != right => None,
        (Some(value), _) | (_, Some(value)) => Some(value),
        _ => None,
    }
}

fn interface_number(value: &str) -> Option<String> {
    let mut text = value.trim();
    if let Some(rest) = text.strip_prefix("if") {
        text = rest;
    } else if let Some((_, rest)) = text.rsplit_once(':') {
        text = rest.rsplit_once('.').map_or(rest, |(_, number)| number);
    }
    if text.is_empty() || !text.chars().all(|character| character.is_ascii_digit()) {
        return None;
    }
    text.parse::<u8>().ok().map(|number| format!("{number:02}"))
}

/// Stable Linux by-id paths and macOS `/dev/cu.*` names are accepted.  A
/// transient ttyACM/ttyUSB path is intentionally never admitted.
pub fn endpoint_is_stable(device: &str) -> bool {
    let linux_by_id = device.starts_with("/dev/serial/by-id/") && device.len() > "/dev/serial/by-id/".len();
    let mac_cu = device.starts_with("/dev/cu.") && device.len() > "/dev/cu.".len();
    (linux_by_id || mac_cu)
        && !device.contains("..")
        && !device.chars().any(|character| character.is_ascii_whitespace())
}

/// Safe, bounded error vocabulary shared by platform and USB callers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UsbError {
    BindingMissing,
    BindingInvalid,
    BindingIncompatible,
    CandidateMissing,
    CandidateAmbiguous,
    CandidateUnstable,
    PermissionDenied,
    OpenFailed,
    Closed,
    Timeout,
    Io,
    Protocol,
    HelloMismatch,
    FirmwareMismatch,
    SessionMismatch,
    OutOfOrder,
    Suspended,
}

impl UsbError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::BindingMissing => "binding_missing",
            Self::BindingInvalid => "binding_invalid",
            Self::BindingIncompatible => "binding_incompatible",
            Self::CandidateMissing => "candidate_missing",
            Self::CandidateAmbiguous => "candidate_ambiguous",
            Self::CandidateUnstable => "candidate_unstable",
            Self::PermissionDenied => "permission_denied",
            Self::OpenFailed => "open_failed",
            Self::Closed => "closed",
            Self::Timeout => "timeout",
            Self::Io => "io",
            Self::Protocol => "protocol",
            Self::HelloMismatch => "hello_mismatch",
            Self::FirmwareMismatch => "firmware_mismatch",
            Self::SessionMismatch => "session_mismatch",
            Self::OutOfOrder => "out_of_order",
            Self::Suspended => "suspended",
        }
    }
}

impl fmt::Display for UsbError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for UsbError {}

/// Frozen `~/.config/herdr/keypad-binding.json` schema.  There is intentionally
/// no save/migrate method in the native bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PairingBinding {
    pub device_id: String,
    pub protocol: u64,
    pub firmware: String,
}

impl PairingBinding {
    pub fn from_value(value: &Value) -> Result<Self, UsbError> {
        let object = value.as_object().ok_or(UsbError::BindingInvalid)?;
        const FIELDS: [&str; 4] = ["schema_version", "device_id", "protocol", "firmware"];
        if object.len() != FIELDS.len() || FIELDS.iter().any(|field| !object.contains_key(*field)) {
            return Err(UsbError::BindingInvalid);
        }
        if object.get("schema_version").and_then(Value::as_u64) != Some(1) {
            return Err(UsbError::BindingInvalid);
        }
        let device_id = object
            .get("device_id")
            .and_then(Value::as_str)
            .ok_or(UsbError::BindingInvalid)?;
        let firmware = object
            .get("firmware")
            .and_then(Value::as_str)
            .ok_or(UsbError::BindingIncompatible)?;
        let protocol = object.get("protocol").and_then(Value::as_u64).unwrap_or(0);
        if protocol != APPLICATION_PROTOCOL {
            return Err(UsbError::BindingIncompatible);
        }
        if !opaque_identifier(device_id) || device_id == "host" {
            return Err(UsbError::BindingInvalid);
        }
        if firmware.is_empty() || firmware.len() > 64 || !firmware.is_ascii() {
            return Err(UsbError::BindingIncompatible);
        }
        Ok(Self { device_id: device_id.to_string(), protocol, firmware: firmware.to_string() })
    }
}

pub fn load_binding(path: impl AsRef<Path>) -> Result<PairingBinding, UsbError> {
    let bytes = std::fs::read(path).map_err(|error| {
        if error.kind() == io::ErrorKind::NotFound {
            UsbError::BindingMissing
        } else {
            UsbError::BindingInvalid
        }
    })?;
    let mut deserializer = serde_json::Deserializer::from_slice(&bytes);
    let value = StrictJson.deserialize(&mut deserializer).map_err(|_| UsbError::BindingInvalid)?;
    deserializer.end().map_err(|_| UsbError::BindingInvalid)?;
    PairingBinding::from_value(&value)
}

#[derive(Clone, Copy)]
struct StrictJson;

impl<'de> DeserializeSeed<'de> for StrictJson {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictJsonVisitor)
    }
}

struct StrictJsonVisitor;

impl<'de> Visitor<'de> for StrictJsonVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Value, E> { Ok(Value::Bool(value)) }
    fn visit_i64<E>(self, value: i64) -> Result<Value, E> where E: DeError { Ok(Value::Number(value.into())) }
    fn visit_u64<E>(self, value: u64) -> Result<Value, E> where E: DeError { Ok(Value::Number(value.into())) }
    fn visit_f64<E>(self, value: f64) -> Result<Value, E> where E: DeError {
        serde_json::Number::from_f64(value).map(Value::Number).ok_or_else(|| E::custom("non-finite JSON number"))
    }
    fn visit_str<E>(self, value: &str) -> Result<Value, E> where E: DeError { Ok(Value::String(value.to_string())) }
    fn visit_string<E>(self, value: String) -> Result<Value, E> where E: DeError { Ok(Value::String(value)) }
    fn visit_none<E>(self) -> Result<Value, E> where E: DeError { Ok(Value::Null) }
    fn visit_unit<E>(self) -> Result<Value, E> where E: DeError { Ok(Value::Null) }
    fn visit_some<D>(self, deserializer: D) -> Result<Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        StrictJson.deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element_seed(StrictJson)? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut object = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if object.contains_key(&key) {
                return Err(A::Error::custom("duplicate JSON object key"));
            }
            let value = map.next_value_seed(StrictJson)?;
            object.insert(key, value);
        }
        Ok(Value::Object(object))
    }
}

fn opaque_identifier(value: &str) -> bool {
    !value.is_empty() && value.len() <= 64 && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
}

/// Platform adapters provide only normalized descriptors and an opened async
/// byte stream.  They do not authorize the application identity.
pub trait SerialStream: AsyncRead + AsyncWrite + Unpin + Send {}
impl<T: AsyncRead + AsyncWrite + Unpin + Send> SerialStream for T {}
pub type SerialConnection = Box<dyn SerialStream>;

pub trait PlatformSerial: Send + Sync {
    fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError>;
    fn open(&self, candidate: &DeviceCandidate) -> Result<SerialConnection, UsbError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SnapshotAck {
    pub reply_to: u64,
    pub accepted: bool,
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub source_status: String,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FocusIntent {
    pub payload: Value,
    pub sequence: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UsbEvent {
    Connected { candidate: DeviceCandidate, boot_id: String, session_id: String },
    SnapshotAck(SnapshotAck),
    FocusIntent(FocusIntent),
    Disconnected,
    Failed { code: &'static str },
}

struct Session {
    candidate: DeviceCandidate,
    device_boot_id: String,
    session_id: String,
    next_sequence: u64,
    last_received_sequence: u64,
}

/// One exact paired CDC stream. A dropped or closed stream clears all partial
/// ingress bytes and session authority; no keyboard/HID operation exists.
pub struct UsbPort {
    platform: Box<dyn PlatformSerial>,
    binding_path: PathBuf,
    timeout: Duration,
    reader: Option<BufReader<SerialConnection>>,
    read_buffer: Vec<u8>,
    binding: Option<PairingBinding>,
    session: Option<Session>,
}

impl UsbPort {
    pub fn new(platform: Box<dyn PlatformSerial>, binding_path: impl Into<PathBuf>) -> Self {
        Self {
            platform,
            binding_path: binding_path.into(),
            timeout: Duration::from_secs(3),
            reader: None,
            read_buffer: Vec::with_capacity(DEVICE_LINE_LIMIT),
            binding: None,
            session: None,
        }
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }
    pub fn connected(&self) -> bool { self.session.is_some() && self.reader.is_some() }
    pub fn candidate(&self) -> Option<&DeviceCandidate> { self.session.as_ref().map(|session| &session.candidate) }
    pub fn session_identity(&self) -> Option<(&str, &str)> {
        self.session.as_ref().map(|session| (session.device_boot_id.as_str(), session.session_id.as_str()))
    }

    /// Enumerate every descriptor candidate, then perform hello on each exact
    /// stable function.  A first match is never enough: exactly one matching
    /// opaque application identity must remain after all opens are checked.
    pub async fn connect(&mut self) -> Result<UsbEvent, UsbError> {
        self.reset_link();
        let binding = load_binding(&self.binding_path)?;
        let candidates = self.platform.enumerate()?;
        let exact: Vec<DeviceCandidate> = candidates.into_iter().filter(DeviceCandidate::admissible).collect();
        if exact.is_empty() {
            return Err(UsbError::CandidateMissing);
        }
        if exact.iter().any(|candidate| !candidate.stable) {
            return Err(UsbError::CandidateUnstable);
        }

        let mut matches: Vec<(DeviceCandidate, BufReader<SerialConnection>, Session)> = Vec::new();
        let mut last_open_error = None;
        for candidate in exact {
            let stream = match self.platform.open(&candidate) {
                Ok(stream) => stream,
                Err(error) => {
                    last_open_error = Some(error);
                    continue;
                }
            };
            let mut reader = BufReader::new(stream);
            match self.perform_hello(&mut reader, &binding).await {
                Ok(mut session) => {
                    session.candidate = candidate.clone();
                    matches.push((candidate, reader, session));
                }
                Err(error) => {
                    if matches!(error, UsbError::PermissionDenied | UsbError::OpenFailed) {
                        last_open_error = Some(error);
                    }
                }
            }
        }
        if matches.len() > 1 {
            return Err(UsbError::CandidateAmbiguous);
        }
        let (candidate, reader, session) = matches.into_iter().next().ok_or(last_open_error.unwrap_or(UsbError::HelloMismatch))?;
        self.binding = Some(binding);
        let boot_id = session.device_boot_id.clone();
        let session_id = session.session_id.clone();
        self.reader = Some(reader);
        self.session = Some(session);
        Ok(UsbEvent::Connected { candidate, boot_id, session_id })
    }

    async fn perform_hello(&mut self, reader: &mut BufReader<SerialConnection>, binding: &PairingBinding) -> Result<Session, UsbError> {
        let host_boot = fresh_id("host");
        let host_session = fresh_id("session");
        let hello_payload = json!({"device_id":"host","firmware":"phase1-host","protocol":APPLICATION_PROTOCOL});
        let hello = wire_frame(APPLICATION_PROTOCOL, "hello", &host_boot, &host_session, 1, None, hello_payload)?;
        write_frame(reader, &hello).await?;
        let mut read_buffer = Vec::with_capacity(DEVICE_LINE_LIMIT);
        loop {
            let line = read_line_with_timeout(reader, &mut read_buffer, self.timeout).await?;
            let frame = parse_wire(&line, APPLICATION_PROTOCOL)?;
            if frame.boot_id.is_empty() || frame.session_id != host_session || frame.sequence == 0 {
                return Err(UsbError::SessionMismatch);
            }
            if frame.frame_type != "hello_ack" || frame.reply_to != Some(1) {
                continue;
            }
            let payload = frame.payload.as_object().ok_or(UsbError::HelloMismatch)?;
            if payload.get("accepted").and_then(Value::as_bool) != Some(true)
                || payload.get("protocol").and_then(Value::as_u64) != Some(APPLICATION_PROTOCOL)
            {
                return Err(UsbError::HelloMismatch);
            }
            let device_id = payload.get("device_id").and_then(Value::as_str).ok_or(UsbError::HelloMismatch)?;
            if device_id != binding.device_id {
                return Err(UsbError::HelloMismatch);
            }
            let firmware = payload.get("firmware").and_then(Value::as_str).ok_or(UsbError::FirmwareMismatch)?;
            if firmware != binding.firmware {
                return Err(UsbError::FirmwareMismatch);
            }
            return Ok(Session {
                candidate: DeviceCandidate::exact("", EXPECTED_SERIAL, EXPECTED_CDC_INTERFACE),
                device_boot_id: frame.boot_id,
                session_id: host_session,
                next_sequence: 1,
                last_received_sequence: frame.sequence,
            });
        }
    }

    pub async fn send_snapshot(&mut self, payload: Value) -> Result<u64, UsbError> {
        self.send_v2("agent_snapshot", payload).await
    }

    pub async fn send_focus_result(&mut self, payload: Value) -> Result<(), UsbError> {
        self.send_v2("focus_result", payload).await.map(|_| ())
    }

    pub async fn poll(&mut self) -> Result<Option<UsbEvent>, UsbError> {
        let frame = self.receive_v2().await?;
        if frame.frame_type == "focus_intent" {
            return Ok(Some(UsbEvent::FocusIntent(FocusIntent {
                payload: frame.payload,
                sequence: frame.sequence,
            })));
        }
        if frame.frame_type == "snapshot_ack" {
            let reply_to = frame.reply_to.ok_or(UsbError::Protocol)?;
            return Ok(Some(UsbEvent::SnapshotAck(snapshot_ack(
                &frame.payload,
                reply_to,
            )?)));
        }
        Ok(None)
    }

    pub fn close(&mut self) { self.reset_link(); }

    fn reset_link(&mut self) {
        self.session = None;
        self.reader = None;
        self.read_buffer.clear();
        self.binding = None;
    }

    async fn send_v2(&mut self, frame_type: &str, payload: Value) -> Result<u64, UsbError> {
        let (device_boot_id, session_id, sequence) = {
            let session = self.session.as_ref().ok_or(UsbError::Closed)?;
            (
                session.device_boot_id.clone(),
                session.session_id.clone(),
                session.next_sequence.checked_add(1).ok_or(UsbError::Protocol)?,
            )
        };
        let frame = wire_frame(DEVICE_PROTOCOL, frame_type, &device_boot_id, &session_id, sequence, None, payload)?;
        let reader = self.reader.as_mut().ok_or(UsbError::Closed)?;
        if let Err(error) = write_frame(reader, &frame).await {
            self.reset_link();
            return Err(error);
        }
        if let Some(session) = self.session.as_mut() {
            session.next_sequence = sequence;
        }
        Ok(sequence)
    }

    async fn receive_v2(&mut self) -> Result<WireFrame, UsbError> {
        let line = match self.read_line_owned().await {
            Ok(line) => line,
            Err(error) => {
                self.reset_link();
                return Err(error);
            }
        };
        let frame = match parse_wire(&line, DEVICE_PROTOCOL) {
            Ok(frame) => frame,
            Err(error) => {
                self.reset_link();
                return Err(error);
            }
        };
        let (boot_matches, sequence_is_fresh) = {
            let session = self.session.as_ref().ok_or(UsbError::Closed)?;
            (
                frame.boot_id == session.device_boot_id && frame.session_id == session.session_id,
                frame.sequence > session.last_received_sequence,
            )
        };
        if !boot_matches {
            self.reset_link();
            return Err(UsbError::SessionMismatch);
        }
        if !sequence_is_fresh {
            self.reset_link();
            return Err(UsbError::OutOfOrder);
        }
        if let Some(session) = self.session.as_mut() {
            session.last_received_sequence = frame.sequence;
        }
        Ok(frame)
    }


    async fn read_line_owned(&mut self) -> Result<Vec<u8>, UsbError> {
        let reader = self.reader.as_mut().ok_or(UsbError::Closed)?;
        read_line_with_timeout(reader, &mut self.read_buffer, self.timeout).await
    }


}

#[derive(Debug)]
struct WireFrame {
    frame_type: String,
    boot_id: String,
    session_id: String,
    sequence: u64,
    reply_to: Option<u64>,
    payload: Value,
}

fn wire_frame(version: u64, frame_type: &str, boot_id: &str, session_id: &str, sequence: u64, reply_to: Option<u64>, payload: Value) -> Result<Value, UsbError> {
    if sequence == 0 || boot_id.is_empty() || session_id.is_empty() || !opaque_identifier(boot_id) || !opaque_identifier(session_id) {
        return Err(UsbError::Protocol);
    }
    Ok(json!({
        "v": version,
        "type": frame_type,
        "boot_id": boot_id,
        "session_id": session_id,
        "seq": sequence,
        "reply_to": reply_to,
        "digest": payload_digest(&payload),
        "payload": payload,
    }))
}

fn parse_wire(line: &[u8], expected_version: u64) -> Result<WireFrame, UsbError> {
    if line.is_empty() || line.len() > DEVICE_LINE_LIMIT || !line.ends_with(&[b'\n']) {
        return Err(UsbError::Protocol);
    }
    let value: Value = serde_json::from_slice(&line[..line.len() - 1]).map_err(|_| UsbError::Protocol)?;
    let object = value.as_object().ok_or(UsbError::Protocol)?;
    const FIELDS: [&str; 8] = ["v", "type", "boot_id", "session_id", "seq", "reply_to", "digest", "payload"];
    if object.len() != FIELDS.len() || FIELDS.iter().any(|field| !object.contains_key(*field)) {
        return Err(UsbError::Protocol);
    }
    if object.get("v").and_then(Value::as_u64) != Some(expected_version) {
        return Err(UsbError::Protocol);
    }
    let frame_type = object.get("type").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let allowed_type = if expected_version == APPLICATION_PROTOCOL {
        frame_type == "hello_ack"
    } else {
        matches!(frame_type, "snapshot_ack" | "focus_intent")
    };
    if !allowed_type {
        return Err(UsbError::Protocol);
    }
    let boot_id = object.get("boot_id").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let session_id = object.get("session_id").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let sequence = object.get("seq").and_then(Value::as_u64).ok_or(UsbError::Protocol)?;
    let reply_to = match object.get("reply_to") {
        Some(Value::Null) => None,
        Some(value) => Some(value.as_u64().ok_or(UsbError::Protocol)?),
        None => return Err(UsbError::Protocol),
    };
    let digest = object.get("digest").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let payload = object.get("payload").cloned().ok_or(UsbError::Protocol)?;
    if !opaque_identifier(boot_id) || !opaque_identifier(session_id) || sequence == 0 || payload_digest(&payload) != digest {
        return Err(UsbError::Protocol);
    }
    Ok(WireFrame { frame_type: frame_type.to_string(), boot_id: boot_id.to_string(), session_id: session_id.to_string(), sequence, reply_to, payload })
}

fn payload_digest(payload: &Value) -> String {
    let mut canonical = Vec::new();
    canonical_json(payload, &mut canonical);
    let mut digest = 0xcbf29ce484222325u64;
    for byte in canonical {
        digest ^= u64::from(byte);
        digest = digest.wrapping_mul(0x100000001b3);
    }
    format!("{digest:016x}")
}

fn canonical_json(value: &Value, output: &mut Vec<u8>) {
    match value {
        Value::Null => output.extend_from_slice(b"null"),
        Value::Bool(value) => output.extend_from_slice(if *value { b"true" } else { b"false" }),
        Value::Number(value) => output.extend_from_slice(value.to_string().as_bytes()),
        Value::String(value) => output.extend_from_slice(serde_json::to_string(value).expect("JSON string encoding").as_bytes()),
        Value::Array(values) => {
            output.push(b'[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 { output.push(b','); }
                canonical_json(value, output);
            }
            output.push(b']');
        }
        Value::Object(values) => {
            output.push(b'{');
            let mut keys: Vec<&String> = values.keys().collect();
            keys.sort();
            for (index, key) in keys.into_iter().enumerate() {
                if index > 0 { output.push(b','); }
                output.extend_from_slice(serde_json::to_string(key).expect("JSON key encoding").as_bytes());
                output.push(b':');
                canonical_json(&values[key], output);
            }
            output.push(b'}');
        }
    }
}
fn snapshot_ack(value: &Value, reply_to: u64) -> Result<SnapshotAck, UsbError> {
    let object = value.as_object().ok_or(UsbError::Protocol)?;
    let accepted = object.get("accepted").and_then(Value::as_bool).ok_or(UsbError::Protocol)?;
    let host_epoch = object.get("host_epoch").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let snapshot_revision = object.get("snapshot_revision").and_then(Value::as_u64).ok_or(UsbError::Protocol)?;
    let source_status = object.get("source_status").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    let reason = object.get("reason").and_then(Value::as_str).ok_or(UsbError::Protocol)?;
    if reply_to == 0 || host_epoch.is_empty() || snapshot_revision == 0 || source_status.is_empty() || reason.is_empty() {
        return Err(UsbError::Protocol);
    }
    Ok(SnapshotAck { reply_to, accepted, host_epoch: host_epoch.to_string(), snapshot_revision, source_status: source_status.to_string(), reason: reason.to_string() })
}

async fn write_frame(reader: &mut BufReader<SerialConnection>, value: &Value) -> Result<(), UsbError> {
    let mut bytes = serde_json::to_vec(value).map_err(|_| UsbError::Protocol)?;
    bytes.push(b'\n');
    if bytes.len() > DEVICE_LINE_LIMIT {
        return Err(UsbError::Protocol);
    }
    tokio::time::timeout(Duration::from_secs(3), reader.get_mut().write_all(&bytes))
        .await
        .map_err(|_| UsbError::Timeout)?
        .map_err(|_| UsbError::Io)
}

async fn read_line_with_timeout<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    buffer: &mut Vec<u8>,
    timeout: Duration,
) -> Result<Vec<u8>, UsbError> {
    tokio::time::timeout(timeout, read_bounded_line(reader, buffer))
        .await
        .map_err(|_| UsbError::Timeout)?
        .map_err(|error| {
            if error.kind() == io::ErrorKind::UnexpectedEof { UsbError::Io } else { UsbError::Protocol }
        })
}

async fn read_bounded_line<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    line: &mut Vec<u8>,
) -> io::Result<Vec<u8>> {
    loop {
        let mut byte = [0u8; 1];
        let count = reader.read(&mut byte).await?;
        if count == 0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "serial stream closed"));
        }
        if line.len() >= DEVICE_LINE_LIMIT {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "serial line exceeds limit"));
        }
        line.push(byte[0]);
        if byte[0] == b'\n' {
            return Ok(std::mem::replace(
                line,
                Vec::with_capacity(DEVICE_LINE_LIMIT),
            ));
        }
    }
}

fn fresh_id(prefix: &str) -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(1);
    let value = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{prefix}-{}-{value}", std::process::id())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serial_and_interface_normalization_is_exact() {
        assert_eq!(canonical_serial("8CBFEA0DCBFC").as_deref(), Some(EXPECTED_SERIAL));
        assert_eq!(canonical_interface("if01", Some("1-1:1.1")).as_deref(), Some("01"));
        assert!(canonical_interface("if00", Some("1-1:1.1")).is_none());
        assert!(!endpoint_is_stable("/dev/ttyACM0"));
        assert!(endpoint_is_stable("/dev/serial/by-id/usb-herdr"));
    }

    #[test]
    fn binding_parser_is_closed_and_read_only() {
        let valid = json!({"schema_version":1,"device_id":"opaque-device","protocol":1,"firmware":"phase1"});
        assert_eq!(PairingBinding::from_value(&valid).unwrap().device_id, "opaque-device");
        assert_eq!(PairingBinding::from_value(&json!({"schema_version":1,"device_id":"host","protocol":1,"firmware":"phase1"})), Err(UsbError::BindingInvalid));
        assert_eq!(PairingBinding::from_value(&json!({"schema_version":1,"device_id":"opaque-device","protocol":2,"firmware":"phase1"})), Err(UsbError::BindingIncompatible));
        assert_eq!(PairingBinding::from_value(&json!({"schema_version":1,"device_id":"opaque-device","protocol":1,"firmware":"phase1","extra":true})), Err(UsbError::BindingInvalid));
    }

    #[test]
    fn payload_digest_sorts_object_keys() {
        assert_eq!(payload_digest(&json!({"b":2,"a":1})), payload_digest(&json!({"a":1,"b":2})));
    }
}
