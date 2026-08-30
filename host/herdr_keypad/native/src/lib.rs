//! Native Herdr keypad bridge domain and port contracts.
//!
//! This crate keeps the process boundary small and typed. Herdr owns process
//! lifetime; the runtime reads authoritative state and exposes only exact
//! `agent.focus`. There is no host HID operation or generic action dispatch in
//! this API.
//!
//! Ownership for downstream plans:
//! * Plan 03 owns protocol, projection, and focus additions under `protocol/` and
//!   `core/`; it consumes the event and port contracts here.
//! * Plan 04 owns Herdr and Codex ports under `ports/`; Herdr keeps the sole typed
//!   `agent.focus` write and never forwards a generic method.
//! * Plan 05 owns USB and platform adapters; device/session authority remains
//!   fenced by the protocol contracts.
//! * Plan 06 owns lifecycle, configuration, control, status, and logging ports.
//! * Plan 07 alone may revisit shared manifests, root exports, entrypoint,
//!   runtime wiring, and the plugin manifest.
//!
//! All ingress capacities and line limits are explicit. The runtime is woken
//! only by a boundary event, device frame, or cancellation; it has no fixed-rate
//! polling loop.

pub mod core;
pub mod platform;
pub mod ports;
pub mod protocol;
extern crate self as herdr_keypad_native;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fmt;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::Notify;

/// Errors crossing the native boundary. Messages are bounded before construction
/// so an upstream payload cannot become an unbounded diagnostic allocation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BridgeError {
    kind: BridgeErrorKind,
    message: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BridgeErrorKind {
    Io,
    Protocol,
    Channel,
    InvalidInput,
}

impl BridgeError {
    pub fn io(error: std::io::Error) -> Self {
        Self::bounded(BridgeErrorKind::Io, error.to_string())
    }

    pub fn protocol(message: impl Into<String>) -> Self {
        Self::bounded(BridgeErrorKind::Protocol, message.into())
    }

    pub fn channel(message: impl Into<String>) -> Self {
        Self::bounded(BridgeErrorKind::Channel, message.into())
    }

    pub fn invalid_input(message: impl Into<String>) -> Self {
        Self::bounded(BridgeErrorKind::InvalidInput, message.into())
    }

    fn bounded(kind: BridgeErrorKind, mut message: String) -> Self {
        if message.len() > 256 {
            message.truncate(256);
        }
        Self { kind, message }
    }

    pub fn code(&self) -> &'static str {
        match self.kind {
            BridgeErrorKind::Io => "io",
            BridgeErrorKind::Protocol => "protocol",
            BridgeErrorKind::Channel => "channel",
            BridgeErrorKind::InvalidInput => "invalid_input",
        }
    }
}

impl fmt::Display for BridgeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code(), self.message)
    }
}

impl std::error::Error for BridgeError {}



/// Normalized Codex payload is complete even when unavailable.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CodexSnapshot {
    pub source_state: String,
    pub primary: Option<u8>,
    pub secondary: Option<u8>,
    pub reset_text: String,
    pub observation_age: String,
    pub reached_limit: Option<bool>,
    pub error_code: String,
}

impl Default for CodexSnapshot {
    fn default() -> Self {
        Self {
            source_state: "unavailable".to_owned(),
            primary: None,
            secondary: None,
            reset_text: "RESET N/A".to_owned(),
            observation_age: "AGE N/A".to_owned(),
            reached_limit: None,
            error_code: String::new(),
        }
    }
}


/// Boundary events accepted by the portable coordinator.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeEvent {
    HerdrInvalidated,
    HerdrUnavailable,
    HerdrAuthorityEnded,
    DeviceConnected { boot_id: String, session_id: String },
    DeviceDisconnected,
    AuthorityCancelled,
}


/// Explicit cancellation state shared by adapters and coordinator.
#[derive(Clone, Default)]
pub struct Cancellation {
    notify: Arc<Notify>,
}

impl Cancellation {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.notify.notify_waiters();
    }

    pub async fn cancelled(&self) {
        self.notify.notified().await;
    }
}

/// Clock/deadline seam. Tests may inject a deterministic implementation without
/// adding periodic wakeups.
pub trait Clock: Send + Sync + 'static {
    fn now(&self) -> Duration;
    fn deadline(&self, after: Duration) -> Deadline {
        Deadline(self.now().saturating_add(after))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Deadline(Duration);

impl Deadline {
    pub fn elapsed<C: Clock>(&self, clock: &C) -> bool {
        clock.now() >= self.0
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> Duration {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
    }
}

/// Core-facing Herdr port contract reserved for the adapter plan.
pub trait HerdrPort: Send {
    fn read_complete(&mut self) -> Pin<Box<dyn Future<Output = Result<HerdrSnapshot, BridgeError>> + Send + '_>>;
    fn focus(&mut self, pane_id: String) -> Pin<Box<dyn Future<Output = Result<HerdrFocusAck, BridgeError>> + Send + '_>>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HerdrSnapshot {
    pub agents: Vec<Value>,
    pub workspaces: Vec<Value>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HerdrFocusAck {
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Value,
    pub focused: bool,
}
