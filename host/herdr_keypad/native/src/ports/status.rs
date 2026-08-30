//! Read-only, bounded operational status.
//!
//! Status intentionally consists only of normalized states and an allowlisted
//! code vocabulary.  It cannot carry a request, path, identity, provider
//! payload, or mutation.  The same `SafeCode` values are consumed by logging.
use serde::de::{self, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Serialize};
use std::collections::{HashSet, VecDeque};
use std::fmt;

pub const STATUS_PAYLOAD_LIMIT: usize = 16 * 1024;
pub const STATUS_HISTORY_LIMIT: usize = 32;
pub const STATUS_IDENTITY_LIMIT: usize = 25;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BridgeStatus {
    Stopped,
    Running,
    Ready,
    Unavailable,
    DeviceUnavailable,
    HerdrUnavailable,
    CodexUnavailable,
    Stale,
}

impl BridgeStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Stopped => "stopped",
            Self::Running => "running",
            Self::Ready => "ready",
            Self::Unavailable => "unavailable",
            Self::DeviceUnavailable => "device_unavailable",
            Self::HerdrUnavailable => "herdr_unavailable",
            Self::CodexUnavailable => "codex_unavailable",
            Self::Stale => "stale",
        }
    }
}

/// Safe operational codes.  No variant accepts arbitrary text.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SafeCode {
    BridgeStarted,
    BridgeStopped,
    BridgeRestarted,
    DeviceConnected,
    DeviceDisconnected,
    DeviceUnavailable,
    HerdrConnected,
    HerdrUnavailable,
    CodexConnected,
    CodexUnavailable,
    ReconnectAttempt,
    ReconnectBackoff,
    Reconnected,
    SnapshotPublished,
    SnapshotAcknowledged,
    FocusAccepted,
    FocusRejected,
    ConfigInvalid,
    BindingInvalid,
    ControlRejected,
    UnauthorizedPeer,
    RestartRequired,
    Suspend,
    Resume,
    AuthorityEnded,
    SourceStale,
    PayloadRejected,
    CapacityReached,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Transition {
    pub code: SafeCode,
    pub at_ms: u64,
}

impl Transition {
    pub const fn new(code: SafeCode, at_ms: u64) -> Self {
        Self { code, at_ms }
    }
}

/// Fixed-capacity transition history.  It stores no raw upstream text.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct TransitionRing {
    entries: VecDeque<Transition>,
}

impl TransitionRing {
    pub fn push(&mut self, code: SafeCode, at_ms: u64) {
        if self.entries.len() == STATUS_HISTORY_LIMIT {
            self.entries.pop_front();
        }
        self.entries.push_back(Transition::new(code, at_ms));
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn as_slice(&self) -> Vec<Transition> {
        self.entries.iter().copied().collect()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StatusSnapshot {
    pub schema_version: u8,
    pub bridge_version: String,
    pub state: BridgeStatus,
    pub device_state: BridgeStatus,
    pub herdr_state: BridgeStatus,
    pub codex_state: BridgeStatus,
    pub config_identity: String,
    pub reconnect_attempt: u32,
    pub backoff_ms: u64,
    pub last_error: Option<SafeCode>,
    pub transitions: Vec<Transition>,
}

impl StatusSnapshot {
    pub fn stopped(config_identity: impl Into<String>) -> Self {
        let mut snapshot = Self {
            schema_version: 1,
            bridge_version: env!("CARGO_PKG_VERSION").to_owned(),
            state: BridgeStatus::Stopped,
            device_state: BridgeStatus::DeviceUnavailable,
            herdr_state: BridgeStatus::Unavailable,
            codex_state: BridgeStatus::Unavailable,
            config_identity: config_identity.into(),
            reconnect_attempt: 0,
            backoff_ms: 0,
            last_error: None,
            transitions: Vec::new(),
        };
        snapshot.sanitize().expect("constructor uses safe values");
        snapshot
    }

    pub fn with_transitions(mut self, ring: TransitionRing) -> Self {
        self.transitions = ring.as_slice();
        self
    }

    pub fn validate(&self) -> Result<(), StatusError> {
        if self.schema_version != 1
            || self.transitions.len() > STATUS_HISTORY_LIMIT
            || self.bridge_version.len() > 32
            || !self.bridge_version.is_ascii()
            || self.config_identity.is_empty()
            || self.config_identity.len() > STATUS_IDENTITY_LIMIT
            || !self
                .config_identity
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return Err(StatusError::Invalid);
        }
        if self.backoff_ms > 8_000 {
            return Err(StatusError::Invalid);
        }
        Ok(())
    }

    pub fn encode(&self) -> Result<Vec<u8>, StatusError> {
        self.validate()?;
        let bytes = serde_json::to_vec(self).map_err(|_| StatusError::Invalid)?;
        if bytes.len() > STATUS_PAYLOAD_LIMIT {
            return Err(StatusError::Oversized);
        }
        Ok(bytes)
    }

    pub fn decode(bytes: &[u8]) -> Result<Self, StatusError> {
        // This check must happen before serde allocates any response object.
        if bytes.len() > STATUS_PAYLOAD_LIMIT {
            return Err(StatusError::Oversized);
        }
        if reject_duplicate_keys(bytes) {
            return Err(StatusError::Invalid);
        }
        let snapshot: Self = serde_json::from_slice(bytes).map_err(|_| StatusError::Invalid)?;
        snapshot.validate()?;
        Ok(snapshot)
    }

    /// Status has no command-bearing fields by construction; this helper makes
    /// the observation/mutation separation explicit at call sites and tests.
    pub const fn has_mutating_fields(&self) -> bool {
        false
    }

    pub(crate) fn sanitize(&mut self) -> Result<(), StatusError> {
        if self.transitions.len() > STATUS_HISTORY_LIMIT {
            self.transitions.truncate(STATUS_HISTORY_LIMIT);
        }
        self.validate()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatusError {
    Invalid,
    Oversized,
}

/// Event representation shared by status history and the optional logger.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SafeEvent {
    pub schema_version: u8,
    pub code: SafeCode,
    pub at_ms: u64,
}

impl SafeEvent {
    pub const fn new(code: SafeCode, at_ms: u64) -> Self {
        Self { schema_version: 1, code, at_ms }
    }

    pub fn encode(&self) -> Result<Vec<u8>, StatusError> {
        let bytes = serde_json::to_vec(self).map_err(|_| StatusError::Invalid)?;
        if bytes.len() > STATUS_PAYLOAD_LIMIT {
            Err(StatusError::Oversized)
        } else {
            Ok(bytes)
        }
    }
}
/// Return true when any JSON object repeats a member name. Serde's ordinary
/// derive keeps the last duplicate, which would weaken closed-protocol
/// admission; this seed walks every nested object before typed allocation.
pub(crate) fn reject_duplicate_keys(bytes: &[u8]) -> bool {
    let mut deserializer = serde_json::Deserializer::from_slice(bytes);
    let result = deserializer.deserialize_any(DuplicateVisitor);
    result.is_err() || deserializer.end().is_err()
}

struct DuplicateSeed;

impl<'de> DeserializeSeed<'de> for DuplicateSeed {
    type Value = ();

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(DuplicateVisitor)
    }
}

struct DuplicateVisitor;

impl<'de> Visitor<'de> for DuplicateVisitor {
    type Value = ();

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, _: bool) -> Result<(), E> {
        Ok(())
    }

    fn visit_i64<E>(self, _: i64) -> Result<(), E> {
        Ok(())
    }

    fn visit_u64<E>(self, _: u64) -> Result<(), E> {
        Ok(())
    }

    fn visit_f64<E>(self, _: f64) -> Result<(), E> {
        Ok(())
    }

    fn visit_str<E>(self, _: &str) -> Result<(), E> {
        Ok(())
    }

    fn visit_borrowed_str<E>(self, _: &'de str) -> Result<(), E> {
        Ok(())
    }

    fn visit_string<E>(self, _: String) -> Result<(), E> {
        Ok(())
    }

    fn visit_none<E>(self) -> Result<(), E> {
        Ok(())
    }

    fn visit_unit<E>(self) -> Result<(), E> {
        Ok(())
    }

    fn visit_some<D>(self, deserializer: D) -> Result<(), D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(DuplicateVisitor)
    }

    fn visit_newtype_struct<D>(self, deserializer: D) -> Result<(), D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(DuplicateVisitor)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<(), A::Error>
    where
        A: SeqAccess<'de>,
    {
        while sequence.next_element_seed(DuplicateSeed)?.is_some() {}
        Ok(())
    }

    fn visit_map<A>(self, mut map: A) -> Result<(), A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut keys = HashSet::new();
        while let Some(key) = map.next_key::<String>()? {
            if !keys.insert(key) {
                return Err(de::Error::custom("duplicate JSON object key"));
            }
            map.next_value_seed(DuplicateSeed)?;
        }
        Ok(())
    }
}
