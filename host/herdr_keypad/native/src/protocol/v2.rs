//! Closed, bounded v2 device protocol.
//!
//! The wire format is deliberately independent from the rest of the bridge.  A
//! line is admitted in the same order as the Python/firmware contract: transport
//! bounds, UTF-8, duplicate/nesting checks, closed envelope/payload validation,
//! canonical FNV-1a digest, and finally session fencing.

use serde::de::{DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{BTreeSet, VecDeque};
use std::fmt;

pub const PROTOCOL_VERSION: u8 = 2;
pub const MAX_LINE_BYTES: usize = 4096;
pub const MAX_JSON_NESTING: usize = 8;
pub const MAX_IDENTIFIER_BYTES: usize = 64;
pub const SESSION_CAPACITY: usize = 16;
pub const SLOT_COUNT: usize = 3;

const ENVELOPE_FIELDS: &[&str] = &[
    "v", "type", "boot_id", "session_id", "seq", "reply_to", "digest", "payload",
];
const SNAPSHOT_REQUIRED_FIELDS: &[&str] = &[
    "host_epoch", "snapshot_revision", "source_status", "agents", "codex", "diagnostics",
];
const SNAPSHOT_FIELDS: &[&str] = &[
    "host_epoch", "snapshot_revision", "source_status", "agents", "codex", "copilot", "diagnostics",
];
const AGENT_FIELDS: &[&str] = &[
    "slot", "entry_id", "title", "discriminator", "since", "age", "state", "pane_id",
    "terminal_id", "agent_session", "source_revision",
];
const CODEX_FIELDS: &[&str] = &[
    "source_state", "primary", "secondary", "reset_text", "observation_age", "reached_limit",
    "error_code",
];
const COPILOT_FIELDS: &[&str] = &[
    "source_state", "used_credits", "included_credits", "used_percent", "reset_text",
    "observation_age", "unlimited", "reached_limit", "usage_allowed", "overage_allowed",
    "failure_reason",
];
const DIAGNOSTICS_FIELDS: &[&str] = &[
    "link_status", "herdr_status", "codex_status", "sync_age", "codex_age", "firmware_version",
    "protocol_version", "bridge_version", "device_suffix", "session_suffix", "revision_suffix",
    "error_code",
];
const ACK_FIELDS: &[&str] = &["accepted", "host_epoch", "snapshot_revision", "source_status", "reason"];
const FOCUS_INTENT_FIELDS: &[&str] = &[
    "action_id", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id", "terminal_id",
    "agent_session", "source_revision",
];
const FOCUS_RESULT_FIELDS: &[&str] = &[
    "action_id", "outcome", "host_epoch", "snapshot_revision", "slot", "entry_id", "pane_id",
    "terminal_id", "agent_session", "source_revision", "focused",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProtocolError {
    pub code: &'static str,
    pub detail: String,
}

impl ProtocolError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self { code, detail: detail.into() }
    }
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for ProtocolError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FrameType {
    AgentSnapshot,
    SnapshotAck,
    FocusIntent,
    FocusResult,
}

impl FrameType {
    fn as_str(self) -> &'static str {
        match self {
            Self::AgentSnapshot => "agent_snapshot",
            Self::SnapshotAck => "snapshot_ack",
            Self::FocusIntent => "focus_intent",
            Self::FocusResult => "focus_result",
        }
    }

    fn parse(value: &Value) -> Result<Self, ProtocolError> {
        match value.as_str() {
            Some("agent_snapshot") => Ok(Self::AgentSnapshot),
            Some("snapshot_ack") => Ok(Self::SnapshotAck),
            Some("focus_intent") => Ok(Self::FocusIntent),
            Some("focus_result") => Ok(Self::FocusResult),
            _ => Err(ProtocolError::new("unknown_type", "frame type is not in the closed v2 set")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceStatus {
    Current,
    Empty,
    Stale,
    Unavailable,
    Offline,
}

impl SourceStatus {
    fn parse(value: &Value) -> Result<Self, ProtocolError> {
        match value.as_str() {
            Some("current") => Ok(Self::Current),
            Some("empty") => Ok(Self::Empty),
            Some("stale") => Ok(Self::Stale),
            Some("unavailable") => Ok(Self::Unavailable),
            Some("offline") => Ok(Self::Offline),
            _ => Err(ProtocolError::new("invalid_shape", "source_status is invalid")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentState {
    Empty,
    Working,
    Idle,
    Blocked,
    Finished,
    Settled,
    Unknown,
}

impl AgentState {
    fn parse(value: &Value) -> Result<Self, ProtocolError> {
        serde_json::from_value(value.clone())
            .map_err(|_| ProtocolError::new("invalid_shape", "agent state is invalid"))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WireIdentity {
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Agent {
    pub slot: u8,
    pub entry_id: String,
    pub title: String,
    pub discriminator: String,
    pub since: String,
    pub age: String,
    pub state: AgentState,
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u32,
}

impl Agent {
    fn validate(&self) -> Result<(), ProtocolError> {
        if self.slot as usize >= SLOT_COUNT {
            return Err(ProtocolError::new("invalid_shape", "agent slots must be unique in 0..2"));
        }
        let empty = matches!(self.state, AgentState::Empty);
        check_opaque(&self.entry_id, "entry_id", empty)?;
        check_text(&self.title, "title", 64, false)?;
        check_text(&self.discriminator, "discriminator", 32, false)?;
        check_text(&self.since, "since", 16, true)?;
        check_text(&self.age, "age", 16, true)?;
        check_opaque(&self.pane_id, "pane_id", empty)?;
        check_opaque(&self.terminal_id, "terminal_id", empty)?;
        if let Some(session) = &self.agent_session {
            check_opaque(session, "agent_session", false)?;
        }
        if empty {
            if self.source_revision != 0 {
                return Err(ProtocolError::new("invalid_identity", "empty identity must have source revision zero"));
            }
        } else if self.source_revision == 0 || self.pane_id.is_empty() || self.terminal_id.is_empty() {
            return Err(ProtocolError::new("invalid_identity", "occupied identity is incomplete"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Codex {
    pub source_state: String,
    pub primary: Option<u8>,
    pub secondary: Option<u8>,
    pub reset_text: String,
    pub observation_age: String,
    pub reached_limit: Option<bool>,
    pub error_code: String,
}

impl Codex {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_status(
            &self.source_state,
            "codex source_state",
            &["current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"],
        )?;
        check_percent(self.primary, "codex primary")?;
        check_percent(self.secondary, "codex secondary")?;
        check_text(&self.reset_text, "codex reset_text", 32, false)?;
        check_text(&self.observation_age, "codex observation_age", 16, false)?;
        check_error_code(&self.error_code, "codex error_code")?;
        if self.error_code == "E-2401"
            && (self.source_state != "unavailable"
                || self.primary.is_some()
                || self.secondary.is_some()
                || self.reset_text != "RESET N/A"
                || self.reached_limit.is_some())
        {
            return Err(ProtocolError::new(
                "invalid_shape",
                "bucket-unavailable Codex state cannot claim capacity",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Diagnostics {
    pub link_status: String,
    pub herdr_status: String,
    pub codex_status: String,
    pub sync_age: String,
    pub codex_age: String,
    pub firmware_version: String,
    pub protocol_version: u8,
    pub bridge_version: String,
    pub device_suffix: String,
    pub session_suffix: String,
    pub revision_suffix: String,
    pub error_code: String,
}

impl Diagnostics {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_status(&self.link_status, "diagnostics link_status", &["current", "offline"])?;
        check_status(
            &self.herdr_status,
            "diagnostics herdr_status",
            &["current", "empty", "stale", "unavailable", "offline"],
        )?;
        check_status(
            &self.codex_status,
            "diagnostics codex_status",
            &["current", "stale", "unavailable", "auth_required", "codex_offline", "host_offline"],
        )?;
        check_text(&self.sync_age, "diagnostics sync_age", 16, false)?;
        check_text(&self.codex_age, "diagnostics codex_age", 16, false)?;
        check_text(&self.firmware_version, "diagnostics firmware_version", 16, false)?;
        if self.protocol_version != PROTOCOL_VERSION {
            return Err(ProtocolError::new(
                "invalid_shape",
                "diagnostics protocol_version must be v2",
            ));
        }
        check_text(&self.bridge_version, "diagnostics bridge_version", 16, false)?;
        for (name, value) in [
            ("diagnostics device_suffix", &self.device_suffix),
            ("diagnostics session_suffix", &self.session_suffix),
            ("diagnostics revision_suffix", &self.revision_suffix),
        ] {
            check_text(value, name, 6, false)?;
            if value.chars().any(|character| !character.is_ascii_uppercase() && !character.is_ascii_digit()) {
                return Err(ProtocolError::new("invalid_shape", format!("{name} must be an uppercase bounded suffix")));
            }
        }
        check_error_code(&self.error_code, "diagnostics error_code")
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CopilotUsage {
    pub source_state: String,
    pub used_credits: Option<u64>,
    pub included_credits: Option<u64>,
    pub used_percent: Option<u8>,
    pub reset_text: String,
    pub observation_age: String,
    pub unlimited: bool,
    pub reached_limit: Option<bool>,
    pub usage_allowed: Option<bool>,
    pub overage_allowed: Option<bool>,
    pub failure_reason: String,
}

impl CopilotUsage {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_status(
            &self.source_state,
            "copilot source_state",
            &["current", "stale", "auth_required", "unavailable"],
        )?;
        check_count(self.used_credits, "copilot used_credits")?;
        check_count(self.included_credits, "copilot included_credits")?;
        check_percent(self.used_percent, "copilot used_percent")?;
        check_text(&self.reset_text, "copilot reset_text", 32, false)?;
        check_text(&self.observation_age, "copilot observation_age", 16, false)?;
        check_text(&self.failure_reason, "copilot failure_reason", 32, true)?;
        if self.failure_reason != ""
            && ![
                "auth_required", "cli_missing", "cli_version_mismatch", "protocol_mismatch",
                "unsupported_host", "quota_unavailable", "billing_mode_unsupported",
                "malformed_quota", "timeout", "transport_unavailable",
            ]
            .contains(&self.failure_reason.as_str())
        {
            return Err(ProtocolError::new("invalid_shape", "copilot failure_reason is not allowlisted"));
        }
        if matches!(self.source_state.as_str(), "auth_required" | "unavailable")
            && (self.used_credits.is_some()
                || self.included_credits.is_some()
                || self.used_percent.is_some()
                || self.unlimited
                || self.reached_limit.is_some())
        {
            return Err(ProtocolError::new(
                "invalid_shape",
                "unavailable Copilot state cannot claim capacity",
            ));
        }
        if self.unlimited && self.included_credits.is_some() {
            return Err(ProtocolError::new(
                "invalid_shape",
                "unlimited Copilot state cannot claim an included denominator",
            ));
        }
        if self.source_state == "current" && self.failure_reason != "" {
            return Err(ProtocolError::new(
                "invalid_shape",
                "current Copilot state cannot carry a failure reason",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentSnapshot {
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub source_status: SourceStatus,
    pub agents: [Agent; SLOT_COUNT],
    pub codex: Codex,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub copilot: Option<CopilotUsage>,
    pub diagnostics: Diagnostics,
}

impl AgentSnapshot {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_identifier(&self.host_epoch, "host_epoch")?;
        if self.snapshot_revision == 0 {
            return Err(ProtocolError::new("invalid_shape", "snapshot_revision must be positive"));
        }
        let mut slots = BTreeSet::new();
        for agent in &self.agents {
            agent.validate()?;
            if !slots.insert(agent.slot) {
                return Err(ProtocolError::new("invalid_shape", "agent slots must be unique in 0..2"));
            }
        }
        if slots != BTreeSet::from([0, 1, 2]) {
            return Err(ProtocolError::new("invalid_shape", "agent slots must be 0, 1, and 2"));
        }
        self.codex.validate()?;
        if let Some(copilot) = &self.copilot {
            copilot.validate()?;
        }
        self.diagnostics.validate()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotAck {
    pub accepted: bool,
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub source_status: SourceStatus,
    pub reason: String,
}

impl SnapshotAck {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_identifier(&self.host_epoch, "host_epoch")?;
        if self.snapshot_revision == 0 {
            return Err(ProtocolError::new("invalid_shape", "snapshot_revision must be positive"));
        }
        check_text(&self.reason, "reason", 64, false)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FocusIntentPayload {
    pub action_id: String,
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub slot: u8,
    pub entry_id: String,
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u32,
}

impl FocusIntentPayload {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_identifier(&self.action_id, "action_id")?;
        check_identifier(&self.host_epoch, "host_epoch")?;
        check_generation(self.snapshot_revision, self.slot)?;
        check_identifier(&self.entry_id, "entry_id")?;
        check_opaque(&self.pane_id, "pane_id", false)?;
        check_opaque(&self.terminal_id, "terminal_id", false)?;
        if let Some(session) = &self.agent_session {
            check_opaque(session, "agent_session", false)?;
        }
        if self.source_revision == 0 {
            return Err(ProtocolError::new("invalid_identity", "occupied identity is incomplete"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FocusOutcome {
    Accepted,
    Rejected,
    StaleTarget,
    NotFound,
    HerdrOffline,
    Timeout,
    Uncertain,
    Vanished,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FocusResultPayload {
    pub action_id: String,
    pub outcome: FocusOutcome,
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub slot: u8,
    pub entry_id: String,
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u32,
    pub focused: bool,
}

impl FocusResultPayload {
    fn validate(&self) -> Result<(), ProtocolError> {
        check_identifier(&self.action_id, "action_id")?;
        check_identifier(&self.host_epoch, "host_epoch")?;
        check_generation(self.snapshot_revision, self.slot)?;
        check_identifier(&self.entry_id, "entry_id")?;
        check_opaque(&self.pane_id, "pane_id", false)?;
        check_opaque(&self.terminal_id, "terminal_id", false)?;
        if let Some(session) = &self.agent_session {
            check_opaque(session, "agent_session", false)?;
        }
        if self.source_revision == 0 {
            return Err(ProtocolError::new("invalid_identity", "occupied identity is incomplete"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Payload {
    AgentSnapshot(AgentSnapshot),
    SnapshotAck(SnapshotAck),
    FocusIntent(FocusIntentPayload),
    FocusResult(FocusResultPayload),
}

impl Payload {
    fn frame_type(&self) -> FrameType {
        match self {
            Self::AgentSnapshot(_) => FrameType::AgentSnapshot,
            Self::SnapshotAck(_) => FrameType::SnapshotAck,
            Self::FocusIntent(_) => FrameType::FocusIntent,
            Self::FocusResult(_) => FrameType::FocusResult,
        }
    }

    fn validate(&self) -> Result<(), ProtocolError> {
        match self {
            Self::AgentSnapshot(value) => value.validate(),
            Self::SnapshotAck(value) => value.validate(),
            Self::FocusIntent(value) => value.validate(),
            Self::FocusResult(value) => value.validate(),
        }
    }

    fn to_value(&self) -> Result<Value, ProtocolError> {
        match self {
            Self::AgentSnapshot(value) => serde_json::to_value(value),
            Self::SnapshotAck(value) => serde_json::to_value(value),
            Self::FocusIntent(value) => serde_json::to_value(value),
            Self::FocusResult(value) => serde_json::to_value(value),
        }
        .map_err(|error| ProtocolError::new("invalid_payload", error.to_string()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProtocolFrame {
    pub version: u8,
    pub frame_type: FrameType,
    pub boot_id: String,
    pub session_id: String,
    pub seq: u32,
    pub reply_to: Option<u32>,
    pub digest: String,
    pub payload: Payload,
}

impl ProtocolFrame {
    pub fn new(
        frame_type: FrameType,
        boot_id: impl Into<String>,
        session_id: impl Into<String>,
        seq: u32,
        reply_to: Option<u32>,
        payload: Payload,
    ) -> Result<Self, ProtocolError> {
        let mut frame = Self {
            version: PROTOCOL_VERSION,
            frame_type,
            boot_id: boot_id.into(),
            session_id: session_id.into(),
            seq,
            reply_to,
            digest: String::new(),
            payload,
        };
        frame.validate_without_digest()?;
        frame.digest = payload_digest(&frame.payload)?;
        Ok(frame)
    }

    pub fn decode_line(line: &[u8]) -> Result<Self, ProtocolError> {
        let result = classify_line(line);
        if result.accepted {
            result
                .frame
                .ok_or_else(|| ProtocolError::new("invalid_envelope", "accepted line has no frame"))
        } else {
            Err(ProtocolError::new(result.reason, result.reason))
        }
    }

    pub fn encode_line(&self) -> Result<Vec<u8>, ProtocolError> {
        self.validate()?;
        let mut envelope = Map::new();
        envelope.insert("v".into(), Value::from(self.version));
        envelope.insert("type".into(), Value::from(self.frame_type.as_str()));
        envelope.insert("boot_id".into(), Value::from(self.boot_id.clone()));
        envelope.insert("session_id".into(), Value::from(self.session_id.clone()));
        envelope.insert("seq".into(), Value::from(self.seq));
        envelope.insert("reply_to".into(), self.reply_to.map_or(Value::Null, Value::from));
        envelope.insert("digest".into(), Value::from(self.digest.clone()));
        envelope.insert("payload".into(), self.payload.to_value()?);
        let mut encoded = canonical_json(&Value::Object(envelope)).into_bytes();
        encoded.push(b'\n');
        if encoded.len() > MAX_LINE_BYTES {
            return Err(ProtocolError::new("line_too_long", "encoded frame exceeds 4096 bytes including LF"));
        }
        Ok(encoded)
    }

    pub fn as_agent_snapshot(&self) -> Result<&AgentSnapshot, ProtocolError> {
        match &self.payload {
            Payload::AgentSnapshot(snapshot) => Ok(snapshot),
            _ => Err(ProtocolError::new("invalid_payload", "frame payload is not agent_snapshot")),
        }
    }

    pub fn as_snapshot_ack(&self) -> Result<&SnapshotAck, ProtocolError> {
        match &self.payload {
            Payload::SnapshotAck(value) => Ok(value),
            _ => Err(ProtocolError::new("invalid_payload", "frame payload is not snapshot_ack")),
        }
    }

    fn validate_without_digest(&self) -> Result<(), ProtocolError> {
        if self.version != PROTOCOL_VERSION {
            return Err(ProtocolError::new("invalid_version", "only protocol v2 is accepted"));
        }
        check_identifier(&self.boot_id, "boot_id")?;
        check_identifier(&self.session_id, "session_id")?;
        if self.seq == 0 {
            return Err(ProtocolError::new("invalid_sequence", "seq must be a positive uint32"));
        }
        if self.reply_to == Some(0) {
            return Err(ProtocolError::new("invalid_reply_to", "reply_to must be null or a positive uint32"));
        }
        if self.frame_type != self.payload.frame_type() {
            return Err(ProtocolError::new("invalid_payload", "frame type and payload differ"));
        }
        self.payload.validate()
    }

    fn validate(&self) -> Result<(), ProtocolError> {
        self.validate_without_digest()?;
        if self.digest.len() != 16 || !self.digest.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
            return Err(ProtocolError::new("invalid_digest", "digest must be a lowercase 64-bit hex value"));
        }
        let expected = payload_digest(&self.payload)?;
        if self.digest != expected {
            return Err(ProtocolError::new("digest_mismatch", "payload digest does not match canonical payload"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProtocolResult {
    pub accepted: bool,
    pub reason: &'static str,
    pub frame: Option<ProtocolFrame>,
    pub dispatched: bool,
}

impl ProtocolResult {
    fn reject(reason: &'static str) -> Self {
        Self { accepted: false, reason, frame: None, dispatched: false }
    }

    fn accepted(frame: ProtocolFrame, dispatched: bool) -> Self {
        Self { accepted: true, reason: "ok", frame: Some(frame), dispatched }
    }
}

pub fn classify_line(line: &[u8]) -> ProtocolResult {
    if line.is_empty() {
        return ProtocolResult::reject("empty_line");
    }
    if line.len() > MAX_LINE_BYTES {
        return ProtocolResult::reject("line_too_long");
    }
    if !line.ends_with(b"\n") {
        return ProtocolResult::reject("missing_lf");
    }
    let text = match std::str::from_utf8(&line[..line.len() - 1]) {
        Ok(text) => text,
        Err(_) => return ProtocolResult::reject("invalid_utf8"),
    };
    if let Err(reason) = preflight(text.as_bytes()) {
        return ProtocolResult::reject(reason);
    }
    let value: Value = match serde_json::from_slice(text.as_bytes()) {
        Ok(value) => value,
        Err(_) => return ProtocolResult::reject("invalid_json"),
    };
    match decode_value(value) {
        Ok(frame) => ProtocolResult::accepted(frame, false),
        Err(error) => ProtocolResult::reject(error.code),
    }
}

pub fn payload_digest(payload: &Payload) -> Result<String, ProtocolError> {
    let value = payload.to_value()?;
    Ok(fnv1a64(canonical_json(&value).as_bytes()))
}

pub fn fnv1a64(bytes: &[u8]) -> String {
    let mut digest: u64 = 0xcbf29ce484222325;
    for byte in bytes {
        digest ^= u64::from(*byte);
        digest = digest.wrapping_mul(0x100000001b3);
    }
    format!("{digest:016x}")
}

fn decode_value(value: Value) -> Result<ProtocolFrame, ProtocolError> {
    let object = value
        .as_object()
        .ok_or_else(|| ProtocolError::new("invalid_envelope", "frame must be an object"))?;
    check_fields(object, ENVELOPE_FIELDS, false)?;
    let version = object.get("v").and_then(Value::as_u64).filter(|value| *value <= u64::from(u8::MAX));
    if version != Some(u64::from(PROTOCOL_VERSION)) {
        return Err(ProtocolError::new("invalid_version", "only protocol v2 is accepted"));
    }
    let frame_type = FrameType::parse(object.get("type").unwrap())?;
    let boot_id = object.get("boot_id").unwrap();
    let session_id = object.get("session_id").unwrap();
    let boot_id = as_identifier(boot_id, "boot_id")?;
    let session_id = as_identifier(session_id, "session_id")?;
    let seq = as_positive_u32(object.get("seq").unwrap(), "seq", "invalid_sequence")?;
    let reply_to = match object.get("reply_to").unwrap() {
        Value::Null => None,
        value => Some(as_positive_u32(value, "reply_to", "invalid_reply_to")?),
    };
    let digest = object.get("digest").unwrap().as_str().ok_or_else(|| ProtocolError::new("invalid_digest", "digest must be a lowercase 64-bit hex value"))?;
    if digest.len() != 16 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return Err(ProtocolError::new("invalid_digest", "digest must be a lowercase 64-bit hex value"));
    }
    let payload_value = object
        .get("payload")
        .ok_or_else(|| ProtocolError::new("invalid_payload", "v2 payload must be an object"))?;
    let payload = decode_payload(frame_type, payload_value)?;
    let frame = ProtocolFrame {
        version: PROTOCOL_VERSION,
        frame_type,
        boot_id,
        session_id,
        seq,
        reply_to,
        digest: digest.to_owned(),
        payload,
    };
    let expected = payload_digest(&frame.payload)?;
    if frame.digest != expected {
        return Err(ProtocolError::new("digest_mismatch", "payload digest does not match canonical payload"));
    }
    Ok(frame)
}

fn decode_payload(frame_type: FrameType, value: &Value) -> Result<Payload, ProtocolError> {
    let object = value
        .as_object()
        .ok_or_else(|| ProtocolError::new("invalid_payload", "v2 payload must be an object"))?;
    let payload = match frame_type {
        FrameType::AgentSnapshot => {
            check_fields_optional(object, SNAPSHOT_REQUIRED_FIELDS, SNAPSHOT_FIELDS)?;
            validate_snapshot_nested(value)?;
            let snapshot: AgentSnapshot = deserialize(object, value)?;
            Payload::AgentSnapshot(snapshot)
        }
        FrameType::SnapshotAck => {
            check_fields(object, ACK_FIELDS, false)?;
            let ack: SnapshotAck = deserialize(object, value)?;
            Payload::SnapshotAck(ack)
        }
        FrameType::FocusIntent => {
            check_fields(object, FOCUS_INTENT_FIELDS, false)?;
            let intent: FocusIntentPayload = deserialize(object, value)?;
            Payload::FocusIntent(intent)
        }
        FrameType::FocusResult => {
            check_fields(object, FOCUS_RESULT_FIELDS, false)?;
            let result: FocusResultPayload = deserialize(object, value)?;
            Payload::FocusResult(result)
        }
    };
    payload.validate()?;

    Ok(payload)
}

fn validate_snapshot_nested(value: &Value) -> Result<(), ProtocolError> {
    let object = value
        .as_object()
        .ok_or_else(|| ProtocolError::new("invalid_payload", "v2 payload must be an object"))?;
    let agents = object
        .get("agents")
        .and_then(Value::as_array)
        .ok_or_else(|| ProtocolError::new("invalid_shape", "agent_snapshot requires exactly three slots"))?;
    if agents.len() != SLOT_COUNT {
        return Err(ProtocolError::new("invalid_shape", "agent_snapshot requires exactly three slots"));
    }
    for agent in agents {
        let agent_object = agent
            .as_object()
            .ok_or_else(|| ProtocolError::new("unknown_field", "agent slot is closed"))?;
        check_fields(agent_object, AGENT_FIELDS, true)?;
    }
    let codex = object
        .get("codex")
        .and_then(Value::as_object)
        .ok_or_else(|| ProtocolError::new("unknown_field", "codex view is closed"))?;
    check_fields(codex, CODEX_FIELDS, true)?;
    if let Some(copilot) = object.get("copilot") {
        let copilot = copilot
            .as_object()
            .ok_or_else(|| ProtocolError::new("unknown_field", "copilot view is closed"))?;
        check_fields(copilot, COPILOT_FIELDS, true)?;
    }
    let diagnostics = object
        .get("diagnostics")
        .and_then(Value::as_object)
        .ok_or_else(|| ProtocolError::new("unknown_field", "diagnostics view is closed"))?;
    check_fields(diagnostics, DIAGNOSTICS_FIELDS, true)
}

fn deserialize<T: for<'de> Deserialize<'de>>(object: &Map<String, Value>, value: &Value) -> Result<T, ProtocolError> {
    let _ = object;
    serde_json::from_value(value.clone()).map_err(|_| ProtocolError::new("invalid_shape", "v2 payload has an invalid shape"))
}

fn check_fields_optional(
    object: &Map<String, Value>,
    required: &[&str],
    allowed: &[&str],
) -> Result<(), ProtocolError> {
    let actual: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    let allowed: BTreeSet<&str> = allowed.iter().copied().collect();
    if actual.difference(&allowed).next().is_some() {
        return Err(ProtocolError::new("unknown_field", "object is closed"));
    }
    let required: BTreeSet<&str> = required.iter().copied().collect();
    if required.difference(&actual).next().is_some() {
        return Err(ProtocolError::new("invalid_shape", "object is missing required fields"));
    }
    Ok(())
}
fn check_fields(object: &Map<String, Value>, expected: &[&str], nested_always_unknown: bool) -> Result<(), ProtocolError> {
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    let actual: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    if actual == expected {
        return Ok(());
    }
    if actual.difference(&expected).next().is_some() || nested_always_unknown {
        Err(ProtocolError::new("unknown_field", "object is closed"))
    } else {
        Err(ProtocolError::new("invalid_shape", "object is missing required fields"))
    }
}

fn as_identifier(value: &Value, name: &'static str) -> Result<String, ProtocolError> {
    let text = value.as_str().ok_or_else(|| ProtocolError::new("invalid_identifier", format!("{name} must be a bounded opaque identifier")))?;
    check_identifier(text, name)?;
    Ok(text.to_owned())
}

fn check_identifier(value: &str, name: &str) -> Result<(), ProtocolError> {
    if value.is_empty() || value.len() > MAX_IDENTIFIER_BYTES || !value.bytes().all(|byte| (0x21..=0x7e).contains(&byte)) {
        return Err(ProtocolError::new("invalid_identifier", format!("{name} must be a bounded opaque identifier")));
    }
    Ok(())
}

fn check_opaque(value: &str, name: &str, allow_empty: bool) -> Result<(), ProtocolError> {
    check_text(value, name, MAX_IDENTIFIER_BYTES, allow_empty)?;
    if value.bytes().any(|byte| byte == b'\r' || byte == b'\n' || byte == b'\t' || byte < 0x21) {
        return Err(ProtocolError::new("invalid_identifier", format!("{name} contains disallowed opaque bytes")));
    }
    Ok(())
}

fn check_text(value: &str, name: &str, maximum: usize, allow_empty: bool) -> Result<(), ProtocolError> {
    if value.len() > maximum || (!allow_empty && value.is_empty()) || !value.is_ascii() {
        return Err(ProtocolError::new("invalid_shape", format!("{name} must be bounded ASCII text")));
    }
    Ok(())
}

fn check_generation(revision: u32, slot: u8) -> Result<(), ProtocolError> {
    if revision == 0 {
        return Err(ProtocolError::new("invalid_shape", "snapshot_revision must be positive"));
    }
    if usize::from(slot) >= SLOT_COUNT {
        return Err(ProtocolError::new("invalid_shape", "focus slot must be 0..2"));
    }
    Ok(())
}

fn as_positive_u32(value: &Value, name: &str, code: &'static str) -> Result<u32, ProtocolError> {
    let value = value.as_u64().filter(|value| (1..=u64::from(u32::MAX)).contains(value));
    value.map(|value| value as u32).ok_or_else(|| ProtocolError::new(code, format!("{name} must be a positive uint32")))
}

fn check_percent(value: Option<u8>, name: &str) -> Result<(), ProtocolError> {
    if value.is_some_and(|value| value > 100) {
        Err(ProtocolError::new("invalid_shape", format!("{name} must be null or an integer percentage")))
    } else {
        Ok(())
    }
}

fn check_count(value: Option<u64>, name: &str) -> Result<(), ProtocolError> {
    if value.is_some_and(|value| value > 1_000_000_000) {
        Err(ProtocolError::new("invalid_shape", format!("{name} must be null or an integer count")))
    } else {
        Ok(())
    }
}
fn check_status(value: &str, name: &str, allowed: &[&str]) -> Result<(), ProtocolError> {
    if allowed.contains(&value) {
        Ok(())
    } else {
        Err(ProtocolError::new("invalid_shape", format!("{name} is invalid")))
    }
}

fn check_error_code(value: &str, name: &str) -> Result<(), ProtocolError> {
    if value.is_empty() || (value.len() == 6 && value.starts_with("E-24") && value[4..].parse::<u16>().is_ok_and(|code| code <= 10)) {
        Ok(())
    } else {
        Err(ProtocolError::new("invalid_shape", format!("{name} is not an allowlisted diagnostic code")))
    }
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Null => "null".to_owned(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => serde_json::to_string(value).expect("JSON string serialization cannot fail"),
        Value::Array(values) => format!("[{}]", values.iter().map(canonical_json).collect::<Vec<_>>().join(",")),
        Value::Object(values) => {
            let mut keys: Vec<&str> = values.keys().map(String::as_str).collect();
            keys.sort_unstable();
            let fields = keys
                .into_iter()
                .map(|key| format!("{}:{}", serde_json::to_string(key).unwrap(), canonical_json(&values[key])))
                .collect::<Vec<_>>();
            format!("{{{}}}", fields.join(","))
        }
    }
}

fn preflight(bytes: &[u8]) -> Result<(), &'static str> {
    let mut deserializer = serde_json::Deserializer::from_slice(bytes);
    AuditSeed { depth: 0 }
        .deserialize(&mut deserializer)
        .map_err(|error| if error.to_string().contains("duplicate_key") || error.to_string().contains("nesting_limit") { if error.to_string().contains("duplicate_key") { "duplicate_key" } else { "invalid_json" } } else { "invalid_json" })?;
    deserializer.end().map_err(|_| "invalid_json")
}

struct AuditSeed {
    depth: usize,
}

impl<'de> DeserializeSeed<'de> for AuditSeed {
    type Value = ();

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        if self.depth > MAX_JSON_NESTING {
            return Err(serde::de::Error::custom("nesting_limit"));
        }
        deserializer.deserialize_any(AuditVisitor { depth: self.depth })
    }
}

struct AuditVisitor {
    depth: usize,
}

impl<'de> Visitor<'de> for AuditVisitor {
    type Value = ();

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("any bounded JSON value")
    }

    fn visit_bool<E>(self, _: bool) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_i64<E>(self, _: i64) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_u64<E>(self, _: u64) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_f64<E>(self, _: f64) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_str<E>(self, _: &str) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_borrowed_str<E>(self, _: &'de str) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_string<E>(self, _: String) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_none<E>(self) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }
    fn visit_unit<E>(self) -> Result<Self::Value, E> where E: serde::de::Error { Ok(()) }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        while sequence.next_element_seed(AuditSeed { depth: self.depth + 1 })?.is_some() {}
        Ok(())
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut keys = BTreeSet::new();
        while let Some(key) = map.next_key::<String>()? {
            if !keys.insert(key) {
                return Err(serde::de::Error::custom("duplicate_key"));
            }
            map.next_value_seed(AuditSeed { depth: self.depth + 1 })?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProtocolSession {
    boot_id: String,
    session_id: String,
    queue_limit: usize,
    last_received_seq: u32,
    seen: VecDeque<u32>,
    pending: VecDeque<ProtocolFrame>,
}

impl ProtocolSession {
    pub fn new(boot_id: impl Into<String>, session_id: impl Into<String>, queue_limit: usize) -> Result<Self, ProtocolError> {
        let boot_id = boot_id.into();
        let session_id = session_id.into();
        check_identifier(&boot_id, "boot_id")?;
        check_identifier(&session_id, "session_id")?;
        if queue_limit == 0 || queue_limit > SESSION_CAPACITY {
            return Err(ProtocolError::new("queue_full", "session queue capacity must be 1..16"));
        }
        Ok(Self { boot_id, session_id, queue_limit, last_received_seq: 0, seen: VecDeque::new(), pending: VecDeque::new() })
    }

    pub fn reset(&mut self, boot_id: impl Into<String>, session_id: impl Into<String>) -> Result<(), ProtocolError> {
        let boot_id = boot_id.into();
        let session_id = session_id.into();
        check_identifier(&boot_id, "boot_id")?;
        check_identifier(&session_id, "session_id")?;
        self.boot_id = boot_id;
        self.session_id = session_id;
        self.last_received_seq = 0;
        self.seen.clear();
        self.pending.clear();
        Ok(())
    }

    pub fn accept(&mut self, line: &[u8]) -> ProtocolResult {
        self.accept_with_dispatch(line, true)
    }

    pub fn accept_with_dispatch(&mut self, line: &[u8], dispatch: bool) -> ProtocolResult {
        let result = classify_line(line);
        if !result.accepted {
            return result;
        }
        let frame = result.frame.expect("accepted result carries a frame");
        if frame.boot_id != self.boot_id {
            return ProtocolResult { accepted: false, reason: "boot_mismatch", frame: Some(frame), dispatched: false };
        }
        if frame.session_id != self.session_id {
            return ProtocolResult { accepted: false, reason: "session_mismatch", frame: Some(frame), dispatched: false };
        }
        if self.seen.contains(&frame.seq) {
            return ProtocolResult { accepted: false, reason: "duplicate", frame: Some(frame), dispatched: false };
        }
        if frame.seq <= self.last_received_seq {
            return ProtocolResult { accepted: false, reason: "out_of_order", frame: Some(frame), dispatched: false };
        }
        if dispatch && self.pending.len() >= self.queue_limit {
            return ProtocolResult { accepted: false, reason: "queue_full", frame: Some(frame), dispatched: false };
        }
        self.last_received_seq = frame.seq;
        self.seen.push_back(frame.seq);
        while self.seen.len() > self.queue_limit {
            self.seen.pop_front();
        }
        if dispatch {
            self.pending.push_back(frame.clone());
        }
        ProtocolResult::accepted(frame, dispatch)
    }

    pub fn complete(&mut self) -> bool { self.pending.pop_front().is_some() }
    pub fn pending_count(&self) -> usize { self.pending.len() }
    pub fn discard_pending(&mut self) -> usize { let count = self.pending.len(); self.pending.clear(); count }
    pub fn boot_id(&self) -> &str { &self.boot_id }
    pub fn session_id(&self) -> &str { &self.session_id }
}
