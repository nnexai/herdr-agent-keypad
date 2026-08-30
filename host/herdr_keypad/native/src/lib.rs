//! Native Herdr keypad bridge boundary and first production coordinator.
//!
//! This crate keeps the process boundary small and typed. Herdr owns process
//! lifetime; the bridge reads authoritative state, publishes complete generations,
//! and exposes only exact `agent.focus`. There is no host HID operation or generic
//! action dispatch in this API.
//!
//! Ownership for downstream plans:
//! * Plan 03 owns protocol, projection, and focus additions under `protocol/` and
//!   `core/`; it consumes the event, effect, generation, and port contracts here.
//! * Plan 04 owns Herdr and Codex ports under `ports/`; Herdr keeps the sole typed
//!   `agent.focus` write and never forwards a generic method.
//! * Plan 05 owns USB and platform adapters; device/session authority remains
//!   fenced by the generation contracts here.
//! * Plan 06 owns lifecycle, configuration, control, status, and logging ports.
//! * Plan 07 alone may revisit shared manifests, root exports, entrypoint,
//!   coordinator wiring, and the plugin manifest.
//!
//! All ingress capacities and line limits are explicit. The coordinator is woken
//! only by a boundary event, device frame, or cancellation; it has no fixed-rate
//! polling loop.

pub mod core;
pub mod platform;
pub mod ports;
pub mod protocol;
extern crate self as herdr_keypad_native;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::fmt;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixStream;
use tokio::sync::{mpsc, Notify};

/// Maximum Herdr/control line size; device protocol has its own smaller limit.
pub const HERDR_LINE_LIMIT: usize = 65_536;
/// Maximum encoded device line including LF, matching protocol/schema/v2.json.
pub const DEVICE_LINE_LIMIT: usize = 4_096;
/// Hard bound on focus intents crossing one device session.
pub const PENDING_FOCUS_CAPACITY: usize = 16;
/// Fixed number of display slots in the v2 device protocol.
pub const SLOT_COUNT: usize = 3;
/// Explicit boundary capacities used by production adapters.
pub const HERDR_EVENT_CAPACITY: usize = 64;
pub const DEVICE_FRAME_CAPACITY: usize = 64;
pub const BRIDGE_EFFECT_CAPACITY: usize = 64;

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

/// Independent source state. Offline/stale is never presented as current.
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
    fn as_wire(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Empty => "empty",
            Self::Stale => "stale",
            Self::Unavailable => "unavailable",
            Self::Offline => "offline",
        }
    }
}

/// Opaque identity that must remain equal across focus revalidation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentIdentity {
    pub pane_id: String,
    pub terminal_id: String,
    pub agent_session: Option<String>,
    pub source_revision: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub workspace_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tab_id: Option<String>,
}

impl AgentIdentity {
    pub fn new(
        pane_id: impl Into<String>,
        terminal_id: impl Into<String>,
        agent_session: Option<String>,
        source_revision: u64,
    ) -> Result<Self, BridgeError> {
        if source_revision == 0 {
            return Err(BridgeError::invalid_input("source revision must be positive"));
        }
        Ok(Self {
            pane_id: bounded_identifier(pane_id.into())?,
            terminal_id: bounded_identifier(terminal_id.into())?,
            agent_session: agent_session.map(bounded_identifier).transpose()?,
            source_revision,
            workspace_id: None,
            tab_id: None,
        })
    }

    fn same_immutable_identity(&self, other: &Self) -> bool {
        self.pane_id == other.pane_id
            && self.terminal_id == other.terminal_id
            && self.agent_session == other.agent_session
            && self.source_revision == other.source_revision
            && self.workspace_id == other.workspace_id
            && self.tab_id == other.tab_id
    }
}

/// Normalized display entry. Empty slots have no identity and cannot be focused.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentInfo {
    pub slot: u8,
    pub entry_id: String,
    pub title: String,
    pub discriminator: String,
    pub since: String,
    pub age: String,
    pub state: String,
    pub stale: bool,
    pub state_change_seq: u64,
    #[serde(flatten)]
    pub identity: Option<AgentIdentity>,
}

impl AgentInfo {
    pub fn empty(slot: usize, status: SourceStatus) -> Self {
        Self {
            slot: slot as u8,
            entry_id: String::new(),
            title: String::new(),
            discriminator: String::new(),
            since: "-".to_owned(),
            age: "-".to_owned(),
            state: if matches!(status, SourceStatus::Current) {
                "empty".to_owned()
            } else {
                status.as_wire().to_owned()
            },
            stale: !matches!(status, SourceStatus::Current),
            state_change_seq: 0,
            identity: None,
        }
    }

    pub fn occupied(&self) -> bool {
        self.identity.is_some() && !self.entry_id.is_empty() && !self.stale
    }
}

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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
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

impl Default for Diagnostics {
    fn default() -> Self {
        Self {
            link_status: "offline".to_owned(),
            herdr_status: "unavailable".to_owned(),
            codex_status: "unavailable".to_owned(),
            sync_age: "AGE N/A".to_owned(),
            codex_age: "AGE N/A".to_owned(),
            firmware_version: "UNKNOWN".to_owned(),
            protocol_version: 2,
            bridge_version: env!("CARGO_PKG_VERSION").to_owned(),
            device_suffix: "NONE".to_owned(),
            session_suffix: "NONE".to_owned(),
            revision_suffix: "NONE".to_owned(),
            error_code: String::new(),
        }
    }
}

/// Complete host generation sent to the device. It always contains three slots.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Snapshot {
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub source_status: SourceStatus,
    pub agents: Vec<AgentInfo>,
    pub codex: CodexSnapshot,
    pub diagnostics: Diagnostics,
    /// Device boot/session authority is carried with the host generation so an
    /// ACK and focus result cannot be replayed across a fresh USB session.
    pub boot_id: String,
    pub session_id: String,
}

impl Snapshot {
    fn validate(&self) -> Result<(), BridgeError> {
        if self.snapshot_revision == 0 || self.agents.len() != SLOT_COUNT {
            return Err(BridgeError::protocol("snapshot is not complete"));
        }
        bounded_identifier(self.host_epoch.clone())?;
        bounded_identifier(self.boot_id.clone())?;
        bounded_identifier(self.session_id.clone())?;
        Ok(())
    }
}

/// Device acknowledgement of one complete snapshot generation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SnapshotAck {
    pub accepted: bool,
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub source_status: SourceStatus,
    pub reason: String,
    #[serde(default)]
    pub boot_id: Option<String>,
    #[serde(default)]
    pub session_id: Option<String>,
}

impl SnapshotAck {
    pub fn accepted(snapshot: &Snapshot) -> Self {
        Self {
            accepted: true,
            host_epoch: snapshot.host_epoch.clone(),
            snapshot_revision: snapshot.snapshot_revision,
            source_status: snapshot.source_status,
            reason: "accepted".to_owned(),
            boot_id: Some(snapshot.boot_id.clone()),
            session_id: Some(snapshot.session_id.clone()),
        }
    }

    fn matches(&self, snapshot: &Snapshot) -> bool {
        self.accepted
            && self.host_epoch == snapshot.host_epoch
            && self.snapshot_revision == snapshot.snapshot_revision
            && self.source_status == snapshot.source_status
            && self.boot_id.as_deref().map_or(true, |id| id == snapshot.boot_id)
            && self.session_id.as_deref().map_or(true, |id| id == snapshot.session_id)
    }
}

/// Exact intent received from a display key. It contains no keycode/HID authority.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FocusIntent {
    pub action_id: String,
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub slot: u8,
    pub entry_id: String,
    pub identity: AgentIdentity,
    #[serde(default)]
    pub boot_id: Option<String>,
    #[serde(default)]
    pub session_id: Option<String>,
}

impl FocusIntent {
    pub fn from_agent(action_id: impl Into<String>, agent: &AgentInfo, snapshot: &Snapshot) -> Self {
        Self {
            action_id: action_id.into(),
            host_epoch: snapshot.host_epoch.clone(),
            snapshot_revision: snapshot.snapshot_revision,
            slot: agent.slot,
            entry_id: agent.entry_id.clone(),
            identity: agent.identity.clone().expect("focus intent requires occupied agent"),
            boot_id: Some(snapshot.boot_id.clone()),
            session_id: Some(snapshot.session_id.clone()),
        }
    }
}

/// Closed result vocabulary matching the device v2 focus-result schema.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BridgeOutcome {
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

/// Correlated exact focus result. All authority fields are copied from intent.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FocusResult {
    pub action_id: String,
    pub outcome: BridgeOutcome,
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub slot: u8,
    pub entry_id: String,
    pub identity: AgentIdentity,
    pub focused: bool,
    pub boot_id: String,
    pub session_id: String,
    pub reason: String,
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

/// Effects visible to device/lifecycle adapters. There is intentionally no
/// keyboard/HID effect and no generic Herdr method effect.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeEffect {
    PublishSnapshot(Snapshot),
    FocusResult(FocusResult),
    AuthorityEnded,
}

/// Device frames after bounded line admission and session framing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DeviceFrame {
    SnapshotAck(SnapshotAck),
    FocusIntent(FocusIntent),
}

/// Decode one bounded v2 device line after transport admission.
pub fn decode_device_line(line: &[u8]) -> Result<DeviceFrame, BridgeError> {
    if line.len() > DEVICE_LINE_LIMIT {
        return Err(BridgeError::protocol("device line exceeds 4096-byte limit"));
    }
    let envelope: Value = serde_json::from_slice(line)
        .map_err(|error| BridgeError::protocol(format!("invalid device JSON: {error}")))?;
    let kind = envelope
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| BridgeError::protocol("device frame has no type"))?;
    let payload = envelope
        .get("payload")
        .cloned()
        .ok_or_else(|| BridgeError::protocol("device frame has no payload"))?;
    match kind {
        "snapshot_ack" => serde_json::from_value(payload)
            .map(DeviceFrame::SnapshotAck)
            .map_err(|error| BridgeError::protocol(format!("invalid snapshot ACK: {error}"))),
        "focus_intent" => serde_json::from_value(payload)
            .map(DeviceFrame::FocusIntent)
            .map_err(|error| BridgeError::protocol(format!("invalid focus intent: {error}"))),
        _ => Err(BridgeError::protocol("unknown device frame type")),
    }
}

/// Encode a complete snapshot or device response for local transport adapters.
/// Protocol Plan 03 owns canonical digest admission; this bootstrap boundary
/// still emits a versioned envelope and enforces the independent line cap.
pub fn encode_device_line(frame_type: &str, payload: Value, generation: &Generation, seq: u64) -> Result<Vec<u8>, BridgeError> {
    if seq == 0 {
        return Err(BridgeError::protocol("device sequence must be positive"));
    }
    let mut line = serde_json::to_vec(&json!({
        "v": 2,
        "type": frame_type,
        "boot_id": generation.boot_id,
        "session_id": generation.session_id,
        "seq": seq,
        "reply_to": Value::Null,
        "digest": "0000000000000000",
        "payload": payload,
    }))
    .map_err(|error| BridgeError::protocol(error.to_string()))?;
    line.push(b'\n');
    if line.len() > DEVICE_LINE_LIMIT {
        return Err(BridgeError::protocol("encoded device line exceeds 4096-byte limit"));
    }
    Ok(line)
}

/// A generation fence used by all later ports.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Generation {
    pub host_epoch: String,
    pub snapshot_revision: u64,
    pub boot_id: String,
    pub session_id: String,
}

impl Generation {
    pub fn from_snapshot(snapshot: &Snapshot) -> Self {
        Self {
            host_epoch: snapshot.host_epoch.clone(),
            snapshot_revision: snapshot.snapshot_revision,
            boot_id: snapshot.boot_id.clone(),
            session_id: snapshot.session_id.clone(),
        }
    }

    pub fn matches_snapshot(&self, snapshot: &Snapshot) -> bool {
        self.host_epoch == snapshot.host_epoch
            && self.snapshot_revision == snapshot.snapshot_revision
            && self.boot_id == snapshot.boot_id
            && self.session_id == snapshot.session_id
    }
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

/// Requests to the narrow Herdr public API. Generic method forwarding is not
/// represented by this type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HerdrRequest {
    socket_path: PathBuf,
}

impl HerdrRequest {
    pub fn unix_socket(path: impl Into<PathBuf>) -> Self {
        Self {
            socket_path: path.into(),
        }
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
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
    pub agent_session: Option<String>,
    pub focused: bool,
}

/// Device adapter contract. Framing and physical I/O remain outside the core.
pub trait DevicePort: Send {
    fn publish_snapshot(&mut self, snapshot: Snapshot) -> Pin<Box<dyn Future<Output = Result<SnapshotAck, BridgeError>> + Send + '_>>;
    fn send_focus_result(&mut self, result: FocusResult) -> Pin<Box<dyn Future<Output = Result<(), BridgeError>> + Send + '_>>;
}

/// Construct bounded channels for adapters; capacities are part of the API.
pub fn bounded_channels() -> (
    mpsc::Sender<BridgeEvent>,
    mpsc::Receiver<BridgeEvent>,
    mpsc::Sender<DeviceFrame>,
    mpsc::Receiver<DeviceFrame>,
    mpsc::Sender<BridgeEffect>,
    mpsc::Receiver<BridgeEffect>,
) {
    let (herdr_tx, herdr_rx) = mpsc::channel(HERDR_EVENT_CAPACITY);
    let (device_tx, device_rx) = mpsc::channel(DEVICE_FRAME_CAPACITY);
    let (effect_tx, effect_rx) = mpsc::channel(BRIDGE_EFFECT_CAPACITY);
    (herdr_tx, herdr_rx, device_tx, device_rx, effect_tx, effect_rx)
}

/// First production coordinator. Later plans can replace transport fields with
/// concrete ports while preserving run, event, effect, and generation types.
pub struct Coordinator {
    herdr: HerdrSocket,
    herdr_events: mpsc::Receiver<BridgeEvent>,
    device_frames: mpsc::Receiver<DeviceFrame>,
    effects: mpsc::Sender<BridgeEffect>,
    current: Option<Snapshot>,
    acknowledged: Option<Generation>,
    pending_focus: VecDeque<FocusIntent>,
    revision: u64,
    boot_id: String,
    session_id: String,
}

impl Coordinator {
    pub fn new(
        request: HerdrRequest,
        herdr_events: mpsc::Receiver<BridgeEvent>,
        device_frames: mpsc::Receiver<DeviceFrame>,
        effects: mpsc::Sender<BridgeEffect>,
    ) -> Result<Self, BridgeError> {
        Ok(Self {
            herdr: HerdrSocket::new(request.socket_path().to_owned()),
            herdr_events,
            device_frames,
            effects,
            current: None,
            acknowledged: None,
            pending_focus: VecDeque::with_capacity(PENDING_FOCUS_CAPACITY),
            revision: 0,
            boot_id: "bridge-boot".to_owned(),
            session_id: "bridge-session".to_owned(),
        })
    }

    /// Run until Herdr authority ends or an ingress boundary closes.
    pub async fn run(mut self) -> Result<(), BridgeError> {
        loop {
            tokio::select! {
                event = self.herdr_events.recv() => {
                    match event {
                        Some(BridgeEvent::HerdrInvalidated) => self.refresh_and_publish().await?,
                        Some(BridgeEvent::HerdrUnavailable) | Some(BridgeEvent::DeviceDisconnected) => {
                            self.acknowledged = None;
                            self.pending_focus.clear();
                        }
                        Some(BridgeEvent::DeviceConnected { boot_id, session_id }) => {
                            self.boot_id = bounded_identifier(boot_id)?;
                            self.session_id = bounded_identifier(session_id)?;
                            self.acknowledged = None;
                            self.pending_focus.clear();
                        }
                        Some(BridgeEvent::HerdrAuthorityEnded) | Some(BridgeEvent::AuthorityCancelled) | None => {
                            self.pending_focus.clear();
                            let _ = self.effects.send(BridgeEffect::AuthorityEnded).await;
                            return Ok(());
                        }
                    }
                }
                frame = self.device_frames.recv() => {
                    match frame {
                        Some(DeviceFrame::SnapshotAck(ack)) => self.on_snapshot_ack(ack).await?,
                        Some(DeviceFrame::FocusIntent(intent)) => self.on_focus_intent(intent).await?,
                        None => return Ok(()),
                    }
                }
            }
        }
    }

    async fn refresh_and_publish(&mut self) -> Result<(), BridgeError> {
        let complete = self.herdr.read_complete().await?;
        let snapshot = self.normalize_snapshot(complete)?;
        snapshot.validate()?;
        self.current = Some(snapshot.clone());
        self.acknowledged = None;
        self.effects
            .send(BridgeEffect::PublishSnapshot(snapshot))
            .await
            .map_err(|_| BridgeError::channel("effect channel closed"))
    }

    fn normalize_snapshot(&mut self, complete: HerdrSnapshot) -> Result<Snapshot, BridgeError> {
        self.revision = self.revision.saturating_add(1).max(1);
        let workspaces = workspace_labels(&complete.workspaces);
        let mut rows = complete
            .agents
            .iter()
            .map(|row| normalize_agent(row, &workspaces))
            .collect::<Result<Vec<_>, _>>()?;
        rows.sort_by_key(|agent| {
            let rank = complete
                .agents
                .iter()
                .find(|row| row.get("pane_id").and_then(Value::as_str) == Some(agent.entry_id.as_str()))
                .and_then(|row| row.get("tokens"))
                .and_then(Value::as_object)
                .and_then(|tokens| tokens.get("rank"))
                .and_then(Value::as_str)
                .and_then(|rank| rank.parse::<u8>().ok())
                .unwrap_or(255);
            (rank, std::cmp::Reverse(agent.state_change_seq))
        });
        rows.truncate(SLOT_COUNT);
        let source_status = if rows.is_empty() {
            SourceStatus::Empty
        } else {
            SourceStatus::Current
        };
        for slot in rows.len()..SLOT_COUNT {
            rows.push(AgentInfo::empty(slot, SourceStatus::Current));
        }
        for (slot, agent) in rows.iter_mut().enumerate() {
            agent.slot = slot as u8;
        }
        Ok(Snapshot {
            host_epoch: "host-epoch".to_owned(),
            snapshot_revision: self.revision,
            source_status,
            agents: rows,
            codex: CodexSnapshot::default(),
            diagnostics: Diagnostics {
                herdr_status: source_status.as_wire().to_owned(),
                ..Diagnostics::default()
            },
            boot_id: self.boot_id.clone(),
            session_id: self.session_id.clone(),
        })
    }

    async fn on_snapshot_ack(&mut self, ack: SnapshotAck) -> Result<(), BridgeError> {
        let Some(snapshot) = self.current.clone() else {
            return Ok(());
        };
        if !ack.matches(&snapshot) {
            return Ok(());
        }
        self.acknowledged = Some(Generation::from_snapshot(&snapshot));
        self.drain_pending_focus().await
    }

    async fn on_focus_intent(&mut self, intent: FocusIntent) -> Result<(), BridgeError> {
        if !self.ready_for(&intent) {
            if self.pending_focus.len() < PENDING_FOCUS_CAPACITY {
                self.pending_focus.push_back(intent);
            }
            return Ok(());
        }
        self.execute_focus(intent).await
    }

    fn ready_for(&self, intent: &FocusIntent) -> bool {
        let Some(snapshot) = self.current.as_ref() else {
            return false;
        };
        let Some(generation) = self.acknowledged.as_ref() else {
            return false;
        };
        if !generation.matches_snapshot(snapshot)
            || intent.host_epoch != snapshot.host_epoch
            || intent.snapshot_revision != snapshot.snapshot_revision
            || intent.boot_id.as_deref().map_or(true, |id| id != snapshot.boot_id)
            || intent.session_id.as_deref().map_or(true, |id| id != snapshot.session_id)
        {
            return false;
        }
        let Some(agent) = snapshot.agents.get(intent.slot as usize) else {
            return false;
        };
        agent.occupied()
            && agent.entry_id == intent.entry_id
            && agent
                .identity
                .as_ref()
                .is_some_and(|identity| identity.same_immutable_identity(&intent.identity))
    }

    async fn drain_pending_focus(&mut self) -> Result<(), BridgeError> {
        while let Some(intent) = self.pending_focus.pop_front() {
            if self.ready_for(&intent) {
                self.execute_focus(intent).await?;
            }
        }
        Ok(())
    }

    async fn execute_focus(&mut self, intent: FocusIntent) -> Result<(), BridgeError> {
        let outcome = match self.herdr.revalidate_and_focus(&intent.identity).await {
            Ok(ack) if ack.focused && ack.same_identity(&intent.identity) => BridgeOutcome::Accepted,
            Ok(_) => BridgeOutcome::Rejected,
            Err(error) if error.code() == "io" => BridgeOutcome::HerdrOffline,
            Err(_) => BridgeOutcome::Uncertain,
        };
        let focused = matches!(outcome, BridgeOutcome::Accepted);
        let result = FocusResult {
            action_id: intent.action_id,
            outcome,
            host_epoch: intent.host_epoch,
            snapshot_revision: intent.snapshot_revision,
            slot: intent.slot,
            entry_id: intent.entry_id,
            identity: intent.identity,
            focused,
            boot_id: intent.boot_id.unwrap_or_else(|| self.boot_id.clone()),
            session_id: intent.session_id.unwrap_or_else(|| self.session_id.clone()),
            reason: if focused {
                "agent.focus acknowledged".to_owned()
            } else {
                "agent.focus rejected".to_owned()
            },
        };
        self.effects
            .send(BridgeEffect::FocusResult(result))
            .await
            .map_err(|_| BridgeError::channel("effect channel closed"))
    }
}

struct HerdrSocket {
    path: PathBuf,
    connection: Option<HerdrConnection>,
    next_id: u64,
}

struct HerdrConnection {
    reader: BufReader<OwnedReadHalf>,
    writer: OwnedWriteHalf,
}

impl HerdrSocket {
    fn new(path: PathBuf) -> Self {
        Self {
            path,
            connection: None,
            next_id: 0,
        }
    }

    async fn connection(&mut self) -> Result<&mut HerdrConnection, BridgeError> {
        if self.connection.is_none() {
            let stream = UnixStream::connect(&self.path).await.map_err(BridgeError::io)?;
            let (reader, writer) = stream.into_split();
            self.connection = Some(HerdrConnection {
                reader: BufReader::new(reader),
                writer,
            });
        }
        self.connection
            .as_mut()
            .ok_or_else(|| BridgeError::io(std::io::Error::new(std::io::ErrorKind::NotConnected, "Herdr connection missing")))
    }

    async fn request(&mut self, method: &str, params: Value) -> Result<Value, BridgeError> {
        self.next_id = self.next_id.saturating_add(1).max(1);
        let id = self.next_id;
        let request = json!({"jsonrpc":"2.0", "id": id, "method": method, "params": params});
        let mut line = serde_json::to_vec(&request).map_err(|error| BridgeError::protocol(error.to_string()))?;
        line.push(b'\n');
        if line.len() > HERDR_LINE_LIMIT {
            return Err(BridgeError::protocol("Herdr request line too long"));
        }
        let connection = self.connection().await?;
        connection.writer.write_all(&line).await.map_err(BridgeError::io)?;
        connection.writer.flush().await.map_err(BridgeError::io)?;
        let mut response_line = Vec::new();
        let read = connection
            .reader
            .read_until(b'\n', &mut response_line)
            .await
            .map_err(BridgeError::io)?;
        if read == 0 || response_line.len() > HERDR_LINE_LIMIT {
            return Err(BridgeError::protocol("Herdr response line unavailable"));
        }
        let response: Value = serde_json::from_slice(&response_line)
            .map_err(|error| BridgeError::protocol(format!("malformed Herdr response: {error}")))?;
        if response.get("id").and_then(Value::as_u64) != Some(id) {
            return Err(BridgeError::protocol("unrelated Herdr response"));
        }
        if let Some(error) = response.get("error") {
            return Err(BridgeError::protocol(safe_error(error)));
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| BridgeError::protocol("missing Herdr result"))
    }

    async fn read_complete(&mut self) -> Result<HerdrSnapshot, BridgeError> {
        let _ = self.request("session.snapshot", json!({})).await?;
        let agents_result = self.request("agent.list", json!({})).await?;
        let workspaces_result = self.request("workspace.list", json!({})).await?;
        let agents = agents_result
            .get("agents")
            .and_then(Value::as_array)
            .cloned()
            .ok_or_else(|| BridgeError::protocol("agent.list result has no agents array"))?;
        let workspaces = workspaces_result
            .get("workspaces")
            .and_then(Value::as_array)
            .cloned()
            .ok_or_else(|| BridgeError::protocol("workspace.list result has no workspaces array"))?;
        Ok(HerdrSnapshot { agents, workspaces })
    }

    async fn revalidate_and_focus(&mut self, identity: &AgentIdentity) -> Result<HerdrFocusAck, BridgeError> {
        let agents_result = self.request("agent.list", json!({})).await?;
        let agents = agents_result
            .get("agents")
            .and_then(Value::as_array)
            .ok_or_else(|| BridgeError::protocol("revalidation has no agents array"))?;
        let current = agents
            .iter()
            .find(|row| row.get("pane_id").and_then(Value::as_str) == Some(identity.pane_id.as_str()))
            .ok_or_else(|| BridgeError::protocol("pane vanished during focus revalidation"))?;
        let terminal_id = current
            .get("terminal_id")
            .and_then(Value::as_str)
            .ok_or_else(|| BridgeError::protocol("focus identity has no terminal"))?;
        let agent_session = current
            .get("agent_session")
            .and_then(Value::as_str)
            .map(str::to_owned);
        let current_identity = AgentIdentity {
            pane_id: identity.pane_id.clone(),
            terminal_id: terminal_id.to_owned(),
            agent_session,
            source_revision: current
                .get("revision")
                .and_then(Value::as_u64)
                .unwrap_or(identity.source_revision),
            workspace_id: current
                .get("workspace_id")
                .and_then(Value::as_str)
                .map(str::to_owned),
            tab_id: current.get("tab_id").and_then(Value::as_str).map(str::to_owned),
        };
        if !current_identity.same_immutable_identity(identity) {
            return Ok(HerdrFocusAck {
                pane_id: current_identity.pane_id,
                terminal_id: current_identity.terminal_id,
                agent_session: current_identity.agent_session,
                focused: false,
            });
        }
        let response = self
            .request("agent.focus", json!({"target": identity.pane_id}))
            .await?;
        let focused = response
            .get("agent")
            .and_then(Value::as_object)
            .or_else(|| response.as_object())
            .and_then(|agent| agent.get("focused"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        Ok(HerdrFocusAck {
            pane_id: identity.pane_id.clone(),
            terminal_id: identity.terminal_id.clone(),
            agent_session: identity.agent_session.clone(),
            focused,
        })
    }
}

fn normalize_agent(row: &Value, workspaces: &[(String, String)]) -> Result<AgentInfo, BridgeError> {
    let object = row
        .as_object()
        .ok_or_else(|| BridgeError::protocol("agent row is not an object"))?;
    let pane_id = required_string(object, "pane_id")?;
    let terminal_id = required_string(object, "terminal_id")?;
    let workspace_id = required_string(object, "workspace_id")?;
    let tab_id = required_string(object, "tab_id")?;
    let revision = object
        .get("revision")
        .and_then(Value::as_u64)
        .filter(|revision| *revision > 0)
        .ok_or_else(|| BridgeError::protocol("agent revision is invalid"))?;
    let status = required_string(object, "agent_status")?;
    let tokens = object
        .get("tokens")
        .and_then(Value::as_object)
        .ok_or_else(|| BridgeError::protocol("agent rank is missing"))?;
    let _rank = tokens
        .get("rank")
        .and_then(Value::as_str)
        .and_then(|rank| rank.parse::<u8>().ok())
        .filter(|rank| *rank <= 5)
        .ok_or_else(|| BridgeError::protocol("agent rank is invalid"))?;
    let state_change_seq = object
        .get("state_change_seq")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let title = ascii_bounded(
        object
            .get("title")
            .and_then(Value::as_str)
            .or_else(|| tokens.get("title").and_then(Value::as_str))
            .unwrap_or("UNKNOWN AGENT"),
        64,
    );
    let discriminator = workspaces
        .iter()
        .find(|(id, _)| id == &workspace_id)
        .map(|(_, label)| label.clone())
        .unwrap_or_else(|| "NO WORKSPACE".to_owned());
    let agent_session = object
        .get("agent_session")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let mut identity = AgentIdentity::new(pane_id.clone(), terminal_id, agent_session, revision)?;
    identity.workspace_id = Some(workspace_id);
    identity.tab_id = Some(tab_id);
    Ok(AgentInfo {
        slot: 0,
        entry_id: pane_id,
        title,
        discriminator: ascii_bounded(&discriminator, 32),
        since: bounded_display(tokens.get("since").and_then(Value::as_str).unwrap_or("-"), 16),
        age: bounded_display(tokens.get("age").and_then(Value::as_str).unwrap_or("-"), 16),
        state: status,
        stale: false,
        state_change_seq,
        identity: Some(identity),
    })
}

fn workspace_labels(workspaces: &[Value]) -> Vec<(String, String)> {
    workspaces
        .iter()
        .filter_map(|workspace| {
            let object = workspace.as_object()?;
            let id = object.get("workspace_id")?.as_str()?.to_owned();
            let label = object
                .get("label")
                .and_then(Value::as_str)
                .or_else(|| object.get("name").and_then(Value::as_str))?;
            Some((id, ascii_bounded(label, 32)))
        })
        .collect()
}

fn required_string(object: &serde_json::Map<String, Value>, key: &str) -> Result<String, BridgeError> {
    let value = object
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| BridgeError::protocol(format!("agent field {key} is missing")))?;
    bounded_identifier(value.to_owned())
}

fn bounded_identifier(value: String) -> Result<String, BridgeError> {
    if value.is_empty() || value.len() > 64 || !value.bytes().all(|byte| (0x21..=0x7e).contains(&byte)) {
        return Err(BridgeError::invalid_input("identifier is outside bounded printable ASCII"));
    }
    Ok(value)
}

fn bounded_display(value: &str, max: usize) -> String {
    value.chars().take(max).collect()
}

fn ascii_bounded(value: &str, max: usize) -> String {
    let sanitized: String = value
        .chars()
        .filter(|character| character.is_ascii())
        .take(max)
        .collect();
    if sanitized.trim().is_empty() {
        "UNKNOWN AGENT".to_owned()
    } else {
        sanitized.trim().to_owned()
    }
}

fn safe_error(value: &Value) -> String {
    let text = value
        .get("code")
        .and_then(Value::as_str)
        .or_else(|| value.get("message").and_then(Value::as_str))
        .unwrap_or("Herdr error");
    bounded_display(text, 160)
}

impl HerdrFocusAck {
    fn same_identity(&self, identity: &AgentIdentity) -> bool {
        self.pane_id == identity.pane_id
            && self.terminal_id == identity.terminal_id
            && self.agent_session == identity.agent_session
    }
}
