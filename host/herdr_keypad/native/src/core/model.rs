//! Portable normalized domain values shared by projection and focus policy.
//!
//! These values intentionally contain only the identity and presentation data
//! needed by the keypad.  They have no keycode, command, HID, or provider
//! authority.

use serde_json::Value;
use std::fmt;

pub const MAX_SLOTS: usize = 3;
pub const MAX_TEXT: usize = 64;
pub const MAX_DISCRIMINATOR: usize = 32;
pub const MAX_IDENTIFIER: usize = 64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SourceStatus {
    Current,
    Empty,
    Stale,
    Unavailable,
    Offline,
}

impl SourceStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Empty => "empty",
            Self::Stale => "stale",
            Self::Unavailable => "unavailable",
            Self::Offline => "offline",
        }
    }

    pub fn is_current(self) -> bool { matches!(self, Self::Current) }

    pub fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "current" => Self::Current,
            "empty" => Self::Empty,
            "stale" => Self::Stale,
            "unavailable" => Self::Unavailable,
            "offline" => Self::Offline,
            _ => return None,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectionError {
    pub reason: &'static str,
}

impl ProjectionError {
    pub fn unavailable() -> Self { Self { reason: "unavailable" } }
}

impl fmt::Display for ProjectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.reason)
    }
}

impl std::error::Error for ProjectionError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Identity {
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u32,
    pub workspace_id: String,
    pub tab_id: String,
}

impl Identity {
    pub fn displayed_echo_exact(&self, echoed: &Self) -> bool {
        self.pane_id == echoed.pane_id
            && self.terminal_id == echoed.terminal_id
            && self.agent_session == echoed.agent_session
            && self.source_revision == echoed.source_revision
            && (echoed.workspace_id.is_empty() || self.workspace_id == echoed.workspace_id)
            && (echoed.tab_id.is_empty() || self.tab_id == echoed.tab_id)
    }

    pub fn live_exact(&self, other: &Self) -> bool {
        self.pane_id == other.pane_id
            && self.terminal_id == other.terminal_id
            && self.agent_session == other.agent_session
            && (self.workspace_id.is_empty() || self.workspace_id == other.workspace_id)
            && (self.tab_id.is_empty() || self.tab_id == other.tab_id)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentEntry {
    pub slot: usize,
    pub entry_id: String,
    pub title: String,
    pub discriminator: String,
    pub since: String,
    pub age: String,
    pub state: String,
    pub rank: Option<u8>,
    pub state_change_seq: u32,
    pub identity: Option<Identity>,
    pub stale: bool,
}

impl AgentEntry {
    pub fn empty(slot: usize, state: impl Into<String>) -> Self {
        Self {
            slot,
            entry_id: String::new(),
            title: "NO AGENT".to_owned(),
            discriminator: "NO WORKSPACE".to_owned(),
            since: String::new(),
            age: String::new(),
            state: state.into(),
            rank: None,
            state_change_seq: 0,
            identity: None,
            stale: false,
        }
    }

    pub fn occupied(&self) -> bool {
        self.identity.is_some() && !self.entry_id.is_empty() && self.state != "empty" && !self.stale
    }

    pub fn logical_eq(&self, other: &Self) -> bool {
        self.slot == other.slot
            && self.entry_id == other.entry_id
            && self.title == other.title
            && self.discriminator == other.discriminator
            && self.since == other.since
            && self.age == other.age
            && self.state == other.state
            && self.rank == other.rank
            && self.state_change_seq == other.state_change_seq
            && self.stale == other.stale
            && match (&self.identity, &other.identity) {
                (Some(left), Some(right)) => left.pane_id == right.pane_id
                    && left.terminal_id == right.terminal_id
                    && left.agent_session == right.agent_session
                    && left.workspace_id == right.workspace_id
                    && left.tab_id == right.tab_id,
                (None, None) => true,
                _ => false,
            }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectionSnapshot {
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub source_status: SourceStatus,
    pub entries: [AgentEntry; MAX_SLOTS],
}

impl ProjectionSnapshot {
    pub fn actionable(&self) -> bool {
        self.source_status.is_current() && self.entries.iter().any(AgentEntry::occupied)
    }

    pub fn binding(&self, slot: usize) -> Option<Binding> {
        if !self.actionable() || slot >= MAX_SLOTS {
            return None;
        }
        let entry = &self.entries[slot];
        if !entry.occupied() {
            return None;
        }
        Some(Binding {
            host_epoch: self.host_epoch.clone(),
            snapshot_revision: self.snapshot_revision,
            slot,
            entry_id: entry.entry_id.clone(),
            identity: entry.identity.clone()?,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Binding {
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub slot: usize,
    pub entry_id: String,
    pub identity: Identity,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FocusIntent {
    pub action_id: String,
    pub binding: Binding,
    pub device_session: Option<String>,
}

impl FocusIntent {
    pub fn new(action_id: impl Into<String>, binding: Binding) -> Self {
        Self { action_id: action_id.into(), binding, device_session: None }
    }

    pub fn with_device_session(mut self, session: impl Into<String>) -> Self {
        self.device_session = Some(session.into());
        self
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FocusStatus {
    Accepted,
    Empty,
    Stale,
    Offline,
    Incompatible,
    WrongEpoch,
    WrongRevision,
    WrongSlot,
    PaneReused,
    SessionChanged,
    SourceRevisionChanged,
    Vanished,
    Rejected,
    Uncertain,
    Failed,
}

impl FocusStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Accepted => "accepted",
            Self::Empty => "empty",
            Self::Stale => "stale",
            Self::Offline => "offline",
            Self::Incompatible => "incompatible",
            Self::WrongEpoch => "wrong_epoch",
            Self::WrongRevision => "wrong_revision",
            Self::WrongSlot => "wrong_slot",
            Self::PaneReused => "pane_reused",
            Self::SessionChanged => "session_changed",
            Self::SourceRevisionChanged => "source_revision_changed",
            Self::Vanished => "vanished",
            Self::Rejected => "rejected",
            Self::Uncertain => "uncertain",
            Self::Failed => "failed",
        }
    }

    pub fn success(self) -> bool { matches!(self, Self::Accepted) }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FocusOutcome {
    pub status: FocusStatus,
    pub action_id: String,
    pub reason: String,
}

impl FocusOutcome {
    pub fn success(&self) -> bool { self.status.success() }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FocusResult {
    pub intent: FocusIntent,
    pub outcome: FocusStatus,
    pub focused: bool,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InboxRow {
    pub pane_id: String,
    pub terminal_id: String,
    pub workspace_id: String,
    pub tab_id: String,
    pub agent_status: String,
    pub focused: bool,
    pub revision: u32,
    pub state_change_seq: u32,
    pub cwd: Option<String>,
    pub title: Option<String>,
    pub tokens: Value,
    pub agent: Option<String>,
    pub agent_session: Value,
}

impl InboxRow {
    pub fn from_value(value: &Value) -> Result<Self, ProjectionError> {
        let object = value.as_object().ok_or_else(ProjectionError::unavailable)?;
        Ok(Self {
            pane_id: required_string(object, "pane_id")?,
            terminal_id: required_string(object, "terminal_id")?,
            workspace_id: required_string(object, "workspace_id")?,
            tab_id: required_string(object, "tab_id")?,
            agent_status: required_string(object, "agent_status")?,
            focused: object.get("focused").and_then(Value::as_bool).ok_or_else(ProjectionError::unavailable)?,
            revision: bounded_uint(object.get("revision").ok_or_else(ProjectionError::unavailable)?)?,
            state_change_seq: bounded_uint_zero(object.get("state_change_seq").ok_or_else(ProjectionError::unavailable)?)?,
            cwd: object.get("cwd").and_then(Value::as_str).map(str::to_owned),
            title: object.get("title").and_then(Value::as_str).map(str::to_owned),
            tokens: object.get("tokens").cloned().ok_or_else(ProjectionError::unavailable)?,
            agent: object.get("agent").and_then(Value::as_str).map(str::to_owned),
            agent_session: object.get("agent_session").cloned().unwrap_or(Value::Null),
        })
    }
}

pub fn required_string(object: &serde_json::Map<String, Value>, key: &str) -> Result<String, ProjectionError> {
    let value = object.get(key).and_then(Value::as_str).ok_or_else(ProjectionError::unavailable)?;
    opaque(value, key, false).map(str::to_owned)
}

pub fn bounded_uint(value: &Value) -> Result<u32, ProjectionError> {
    value.as_u64().filter(|value| *value >= 1 && *value <= u64::from(u32::MAX)).map(|v| v as u32).ok_or_else(ProjectionError::unavailable)
}

pub fn bounded_uint_zero(value: &Value) -> Result<u32, ProjectionError> {
    value.as_u64().filter(|value| *value <= u64::from(u32::MAX)).map(|v| v as u32).ok_or_else(ProjectionError::unavailable)
}

pub fn opaque<'a>(value: &'a str, _name: &str, allow_empty: bool) -> Result<&'a str, ProjectionError> {
    if (!allow_empty && value.is_empty()) || value.len() > MAX_IDENTIFIER || !value.is_ascii() || value.bytes().any(|byte| byte < 0x21 || byte > 0x7e) {
        return Err(ProjectionError::unavailable());
    }
    Ok(value)
}

pub fn text<'a>(value: &'a str, _name: &str, maximum: usize, allow_empty: bool) -> Result<&'a str, ProjectionError> {
    if (!allow_empty && value.is_empty()) || value.len() > maximum || !value.is_ascii() || value.bytes().any(|byte| byte < 0x20) {
        return Err(ProjectionError::unavailable());
    }
    Ok(value)
}

pub fn session_token(value: &Value) -> Result<Option<String>, ProjectionError> {
    match value {
        Value::Null => Ok(None),
        Value::String(value) => Ok(Some(opaque(value, "agent_session", false)?.to_owned())),
        Value::Object(object) => {
            let pieces = ["source", "agent", "kind"].map(|key| object.get(key).and_then(Value::as_str));
            if pieces.iter().all(Option::is_some) {
                let token = pieces.into_iter().map(Option::unwrap).collect::<Vec<_>>().join(":");
                Ok(Some(opaque(&token, "agent_session", false)?.to_owned()))
            } else {
                Err(ProjectionError::unavailable())
            }
        }
        _ => Err(ProjectionError::unavailable()),
    }
}
