//! Event-driven integration of the completed native bridge ports.
//!
//! The coordinator owns only cross-boundary state: projection generations,
//! source/link readiness, reconnect deadlines, and focus fencing.  Herdr,
//! Codex, USB, lifecycle, and platform modules retain their own transport and
//! validation policy.

use super::focus::{FocusError, FocusExecutor, HerdrPort as FocusHerdrPort};
use super::model::{Binding, FocusIntent as ModelFocusIntent, FocusStatus, Identity, ProjectionSnapshot, SourceStatus as ModelSourceStatus};
use super::projection::InboxProjection;
use crate::ports::codex::{CodexCollector, FULL_POLL_INTERVAL};
use crate::ports::config::StartupConfig;
use crate::ports::herdr::{HerdrClient, HerdrError, HerdrEventStream};
use crate::ports::lifecycle::{LifecycleCommand, LifecycleOwner, ResourceMetrics, RuntimePaths};
use crate::ports::logging::{SafeLogger, TraceConfig};
use crate::ports::status::StatusSnapshot;
use crate::ports::usb::{UsbError, UsbEvent, UsbPort};
use crate::protocol::v2::{self, Agent, AgentSnapshot, Codex, Diagnostics, FocusIntentPayload, FocusOutcome, FocusResultPayload, FrameType, Payload, ProtocolFrame, SourceStatus as WireSourceStatus};
use crate::{BridgeError, Cancellation};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::future::Future;
use std::time::Duration;
use tokio::time::{sleep, Instant};

const DEFAULT_HERDR_TIMEOUT: Duration = Duration::from_secs(2);
const DEFAULT_CODEX_DEADLINE: Duration = Duration::from_secs(15);
const DEFAULT_RECONNECT_INITIAL: Duration = Duration::from_millis(500);
const DEFAULT_RECONNECT_MAX: Duration = Duration::from_secs(8);
const EVENT_WAIT: Duration = Duration::from_secs(24 * 60 * 60);
const FOCUS_QUEUE_LIMIT: usize = 16;

/// Integration timing knobs.  All values are bounded and deadlines are created
/// only for recovery/freshness work; a healthy event stream has no ticker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CoordinatorConfig {
    pub herdr_timeout: Duration,
    pub codex_deadline: Duration,
    pub reconnect_initial: Duration,
    pub reconnect_max: Duration,
}

impl Default for CoordinatorConfig {
    fn default() -> Self {
        Self {
            herdr_timeout: DEFAULT_HERDR_TIMEOUT,
            codex_deadline: DEFAULT_CODEX_DEADLINE,
            reconnect_initial: DEFAULT_RECONNECT_INITIAL,
            reconnect_max: DEFAULT_RECONNECT_MAX,
        }
    }
}

impl CoordinatorConfig {
    pub fn validate(self) -> Result<Self, BridgeError> {
        if self.herdr_timeout.is_zero()
            || self.herdr_timeout > Duration::from_secs(120)
            || self.codex_deadline.is_zero()
            || self.codex_deadline > Duration::from_secs(120)
            || self.reconnect_initial.is_zero()
            || self.reconnect_initial > self.reconnect_max
            || self.reconnect_max > DEFAULT_RECONNECT_MAX
        {
            return Err(BridgeError::invalid_input("coordinator timing is outside bounded limits"));
        }
        Ok(self)
    }
}

/// One production coordinator joining every completed port.
pub struct RuntimeCoordinator {
    paths: RuntimePaths,
    lifecycle: LifecycleOwner,
    herdr: HerdrClient,
    herdr_events: HerdrEventStream,
    codex: CodexCollector,
    usb: UsbPort,
    projection: InboxProjection,
    logger: SafeLogger,
    config: CoordinatorConfig,
    cancellation: Cancellation,
    pending_focus: VecDeque<ModelFocusIntent>,
    current: Option<ProjectionSnapshot>,
    last_payload: Option<Value>,
    herdr_healthy: bool,
    herdr_delay: Duration,
    herdr_due: Option<Instant>,
    usb_delay: Duration,
    usb_due: Option<Instant>,
    codex_due: Option<Instant>,
    device_ready: bool,
    event_count: u64,
    publication_count: u64,
    resource_metrics: ResourceMetrics,
}

impl RuntimeCoordinator {
    /// Build the runtime from Herdr-provided paths and startup-validated config.
    /// The frozen binding path is explicit so this constructor cannot select a
    /// different pairing authority.
    pub fn new(
        paths: RuntimePaths,
        startup: StartupConfig,
        binding_path: impl Into<std::path::PathBuf>,
        platform: Box<dyn crate::ports::usb::PlatformSerial>,
    ) -> Result<Self, BridgeError> {
        Self::with_config(paths, startup, binding_path, platform, CoordinatorConfig::default())
    }

    pub fn with_config(
        paths: RuntimePaths,
        startup: StartupConfig,
        binding_path: impl Into<std::path::PathBuf>,
        platform: Box<dyn crate::ports::usb::PlatformSerial>,
        config: CoordinatorConfig,
    ) -> Result<Self, BridgeError> {
        let config = config.validate()?;
        let herdr = HerdrClient::new(paths.herdr_socket.clone(), config.herdr_timeout)
            .map_err(|error| BridgeError::protocol(format!("herdr client: {error}")))?;
        let herdr_events = HerdrEventStream::new(herdr.clone());
        let codex = CodexCollector::try_new("codex", config.codex_deadline)
            .map_err(|error| BridgeError::invalid_input(error))?;
        let lifecycle = LifecycleOwner::from_startup(paths.clone(), startup)
            .map_err(|error| BridgeError::protocol(format!("lifecycle authority: {error:?}")))?;
        let host_epoch = format!("host-{}", std::process::id());
        let projection = InboxProjection::new(host_epoch)
            .map_err(|error| BridgeError::invalid_input(error.to_string()))?;
        Ok(Self {
            paths,
            lifecycle,
            herdr,
            herdr_events,
            codex,
            usb: UsbPort::new(platform, binding_path),
            projection,
            logger: SafeLogger::new(TraceConfig { enabled: false }),
            config,
            cancellation: Cancellation::new(),
            pending_focus: VecDeque::with_capacity(FOCUS_QUEUE_LIMIT),
            current: None,
            last_payload: None,
            herdr_healthy: false,
            herdr_delay: config.reconnect_initial,
            herdr_due: None,
            usb_delay: config.reconnect_initial,
            usb_due: None,
            codex_due: None,
            device_ready: false,
            event_count: 0,
            publication_count: 0,
            resource_metrics: ResourceMetrics::idle(),
        })
    }

    pub fn cancellation(&self) -> Cancellation {
        self.cancellation.clone()
    }

    pub fn projection(&self) -> Option<&ProjectionSnapshot> {
        self.current.as_ref()
    }

    pub fn status(&self) -> StatusSnapshot {
        self.lifecycle.status()
    }

    pub fn resource_metrics(&self) -> ResourceMetrics {
        self.resource_metrics
    }

    pub fn event_count(&self) -> u64 {
        self.event_count
    }

    pub fn publication_count(&self) -> u64 {
        self.publication_count
    }

    pub fn lifecycle(&self) -> &LifecycleOwner {
        &self.lifecycle
    }

    /// Run until cancellation, Herdr authority termination, or all ingress
    /// boundaries are closed.  Reconnects and freshness are explicit deadlines,
    /// never a fixed-rate source poll.
    pub async fn run(mut self) -> Result<(), BridgeError> {
        let _ = self.lifecycle.handle(LifecycleCommand::Start);
        self.try_connect_herdr().await;
        self.try_connect_usb().await;
        self.collect_codex_and_publish().await;
        loop {
            tokio::select! {
                _ = self.cancellation.cancelled() => {
                    self.shutdown(false);
                    return Ok(());
                }
                event = async {
                    if self.herdr_events.active() {
                        self.herdr_events.next_event(EVENT_WAIT).await
                    } else {
                        std::future::pending().await
                    }
                } => self.handle_herdr_event(event).await?,
                frame = async {
                    if self.usb.connected() {
                        self.usb.poll().await
                    } else {
                        std::future::pending().await
                    }
                } => self.handle_usb_event(frame).await?,
                _ = reconnect_sleep(self.herdr_due) => {
                    self.herdr_due = None;
                    self.try_connect_herdr().await;
                }
                _ = reconnect_sleep(self.usb_due) => {
                    self.usb_due = None;
                    self.try_connect_usb().await;
                }
                _ = codex_sleep(self.codex_due) => {
                    self.codex_due = None;
                    self.collect_codex_and_publish().await;
                }
            }
        }
    }

    async fn handle_herdr_event(&mut self, event: Result<Option<crate::BridgeEvent>, HerdrError>) -> Result<(), BridgeError> {
        match event {
            Ok(Some(crate::BridgeEvent::HerdrInvalidated)) => {
                self.event_count = self.event_count.saturating_add(1);
                self.resource_metrics.wakes = self.resource_metrics.wakes.saturating_add(1);
                self.projection.invalidate("stale");
                self.device_ready = false;
                self.publish_current().await;
            }
            Ok(Some(crate::BridgeEvent::HerdrAuthorityEnded)) | Ok(Some(crate::BridgeEvent::AuthorityCancelled)) => {
                self.shutdown(true);
                return Err(BridgeError::protocol("Herdr authority ended"));
            }
            Ok(Some(crate::BridgeEvent::HerdrUnavailable)) | Err(_) => {
                self.mark_herdr_unavailable("offline").await;
            }
            Ok(Some(crate::BridgeEvent::DeviceDisconnected)) | Ok(Some(crate::BridgeEvent::DeviceConnected { .. })) | Ok(None) => {}
        }
        Ok(())
    }

    async fn handle_usb_event(&mut self, event: Result<Option<UsbEvent>, UsbError>) -> Result<(), BridgeError> {
        match event {
            Ok(Some(UsbEvent::Connected { .. })) => {
                self.device_ready = false;
                self.usb_due = None;
                self.usb_delay = self.config.reconnect_initial;
                self.publish_current().await;
            }
            Ok(Some(UsbEvent::SnapshotAck(ack))) => {
                self.device_ready = ack.accepted;
            }
            Ok(Some(UsbEvent::FocusIntent(intent))) => {
                self.accept_focus_payload(intent.payload, intent.sequence)?;
            }
            Ok(Some(UsbEvent::Disconnected)) => self.mark_usb_unavailable(),
            Ok(Some(UsbEvent::Failed { .. })) | Err(_) => self.mark_usb_unavailable(),
            Ok(None) => {}
        }
        if self.device_ready {
            self.drain_focus().await?;
        }
        Ok(())
    }

    async fn try_connect_herdr(&mut self) {
        match self.herdr_events.connect(self.config.herdr_timeout).await {
            Ok(()) => {
                self.herdr_healthy = true;
                self.herdr_due = None;
                self.herdr_delay = self.config.reconnect_initial;
                self.refresh_herdr().await;
            }
            Err(_) => {
                self.mark_herdr_unavailable("offline").await;
            }
        }
    }

    async fn try_connect_usb(&mut self) {
        match self.usb.connect().await {
            Ok(UsbEvent::Connected { .. }) => {
                self.device_ready = false;
                self.usb_due = None;
                self.usb_delay = self.config.reconnect_initial;
                self.publish_current().await;
            }
            Ok(_) | Err(_) => self.mark_usb_unavailable(),
        }
    }

    async fn refresh_herdr(&mut self) {
        match self.herdr.read_complete().await {
            Ok(snapshot) => {
                self.herdr_healthy = true;
                let result = self.projection.refresh(&snapshot.agents, &snapshot.workspaces);
                match result {
                    Ok(value) => {
                        self.current = Some(value);
                        self.publish_current().await;
                    }
                    Err(_) => self.mark_herdr_unavailable("unavailable").await,
                }
            }
            Err(_) => self.mark_herdr_unavailable("offline").await,
        }
    }

    async fn mark_herdr_unavailable(&mut self, reason: &str) {
        self.herdr_healthy = false;
        self.herdr_events.close();
        self.projection.invalidate(if reason == "offline" { "offline" } else { "unavailable" });
        self.current = self.projection.current.clone();
        self.device_ready = false;
        self.publish_current().await;
        self.schedule_herdr();
    }

    fn mark_usb_unavailable(&mut self) {
        self.device_ready = false;
        self.pending_focus.clear();
        self.usb.close();
        self.schedule_usb();
    }

    async fn collect_codex_and_publish(&mut self) {
        let result = tokio::task::block_in_place(|| self.codex.collect());
        self.codex_due = Some(Instant::now() + FULL_POLL_INTERVAL);
        self.resource_metrics.timer_fires = self.resource_metrics.timer_fires.saturating_add(1);
        if let Some(snapshot) = self.current.as_ref() {
            let _ = result;
            let _ = self.publish_snapshot(snapshot.clone()).await;
        }
    }

    async fn publish_current(&mut self) {
        if let Some(snapshot) = self.current.clone() {
            let _ = self.publish_snapshot(snapshot).await;
        }
    }

    async fn publish_snapshot(&mut self, snapshot: ProjectionSnapshot) -> Result<(), BridgeError> {
        let payload = self.payload_for(&snapshot)?;
        self.last_payload = Some(payload.clone());
        if !self.usb.connected() {
            return Ok(());
        }
        match self.usb.publish_snapshot(payload).await {
            Ok(ack) => {
                self.device_ready = ack.accepted
                    && ack.host_epoch == snapshot.host_epoch
                    && ack.snapshot_revision == u64::from(snapshot.snapshot_revision)
                    && ack.source_status == snapshot.source_status.as_str();
                if self.device_ready {
                    self.publication_count = self.publication_count.saturating_add(1);
                    self.resource_metrics.wakes = self.resource_metrics.wakes.saturating_add(1);
                    self.drain_focus().await?;
                }
            }
            Err(_) => self.mark_usb_unavailable(),
        }
        Ok(())
    }

    fn payload_for(&self, snapshot: &ProjectionSnapshot) -> Result<Value, BridgeError> {
        let agents: [Agent; v2::SLOT_COUNT] = snapshot
            .entries
            .iter()
            .map(wire_agent)
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| BridgeError::protocol("projection does not contain three slots"))?;
        let codex_view = self.codex.view();
        let source_status = wire_source_status(snapshot.source_status);
        let diagnostics = Diagnostics {
            link_status: if self.usb.connected() { "current" } else { "offline" }.to_owned(),
            herdr_status: snapshot.source_status.as_str().to_owned(),
            codex_status: codex_view.source_state.clone(),
            sync_age: "AGE N/A".to_owned(),
            codex_age: codex_view.observation_age.clone(),
            firmware_version: "UNKNOWN".to_owned(),
            protocol_version: v2::PROTOCOL_VERSION,
            bridge_version: env!("CARGO_PKG_VERSION").to_owned(),
            device_suffix: "NONE".to_owned(),
            session_suffix: "NONE".to_owned(),
            revision_suffix: format!("{:06X}", snapshot.snapshot_revision),
            error_code: codex_view.error_code.clone(),
        };
        let typed = AgentSnapshot {
            host_epoch: snapshot.host_epoch.clone(),
            snapshot_revision: snapshot.snapshot_revision,
            source_status,
            agents,
            codex: Codex {
                source_state: codex_view.source_state,
                primary: codex_view.primary,
                secondary: codex_view.secondary,
                reset_text: codex_view.reset_text,
                observation_age: codex_view.observation_age,
                reached_limit: codex_view.reached_limit,
                error_code: codex_view.error_code,
            },
            diagnostics,
        };
        let frame = ProtocolFrame::new(
            FrameType::AgentSnapshot,
            "bridge",
            "bridge",
            snapshot.snapshot_revision,
            None,
            Payload::AgentSnapshot(typed),
        )
        .map_err(|error| BridgeError::protocol(error.to_string()))?;
        let encoded = frame.encode_line().map_err(|error| BridgeError::protocol(error.to_string()))?;
        let value: Value = serde_json::from_slice(&encoded)
            .map_err(|error| BridgeError::protocol(format!("snapshot encoding: {error}")))?;
        value.get("payload").cloned().ok_or_else(|| BridgeError::protocol("snapshot payload missing"))
    }

    fn accept_focus_payload(&mut self, payload: Value, sequence: u64) -> Result<(), BridgeError> {
        let (boot_id, session_id) = self
            .usb
            .session_identity()
            .ok_or_else(|| BridgeError::protocol("focus arrived without a device session"))?;
        if sequence > u64::from(u32::MAX) {
            return Err(BridgeError::protocol("device sequence exceeds v2 range"));
        }
        let typed: FocusIntentPayload = serde_json::from_value(payload)
            .map_err(|error| BridgeError::protocol(format!("invalid focus intent: {error}")))?;
        ProtocolFrame::new(
            FrameType::FocusIntent,
            boot_id,
            session_id,
            sequence as u32,
            None,
            Payload::FocusIntent(typed.clone()),
        )
        .map_err(|error| BridgeError::protocol(error.to_string()))?;
        let identity = Identity {
            pane_id: typed.pane_id,
            terminal_id: typed.terminal_id,
            agent_session: typed.agent_session,
            source_revision: typed.source_revision,
            workspace_id: String::new(),
            tab_id: String::new(),
        };
        let binding = Binding {
            host_epoch: typed.host_epoch,
            snapshot_revision: typed.snapshot_revision,
            slot: usize::from(typed.slot),
            entry_id: typed.entry_id,
            identity,
        };
        let intent = ModelFocusIntent::new(typed.action_id, binding).with_device_session(session_id.to_owned());
        if self.pending_focus.len() >= FOCUS_QUEUE_LIMIT {
            self.pending_focus.pop_front();
        }
        if !self.pending_focus.iter().any(|pending| pending.action_id == intent.action_id) {
            self.pending_focus.push_back(intent);
        }
        self.resource_metrics.queue_high_water = self.resource_metrics.queue_high_water.max(self.pending_focus.len());
        Ok(())
    }

    async fn drain_focus(&mut self) -> Result<(), BridgeError> {
        if !self.device_ready || !self.herdr_healthy {
            return Ok(());
        }
        while let Some(intent) = self.pending_focus.pop_front() {
            let outcome = {
                let projection = &self.projection;
                let client = &mut self.herdr;
                tokio::task::block_in_place(|| {
                    let mut port = BlockingHerdr { client };
                    FocusExecutor::new().execute(projection, &intent, &mut port)
                })
            };
            let payload = focus_payload(&intent, outcome.status, outcome.success());
            if self.usb.send_focus_result(payload).await.is_err() {
                self.mark_usb_unavailable();
                break;
            }
        }
        Ok(())
    }

    fn schedule_herdr(&mut self) {
        if self.herdr_due.is_none() {
            self.herdr_due = Some(Instant::now() + self.herdr_delay);
            self.herdr_delay = self.herdr_delay.saturating_mul(2).min(self.config.reconnect_max);
            self.resource_metrics.timer_fires = self.resource_metrics.timer_fires.saturating_add(1);
        }
    }

    fn schedule_usb(&mut self) {
        if self.usb_due.is_none() {
            self.usb_due = Some(Instant::now() + self.usb_delay);
            self.usb_delay = self.usb_delay.saturating_mul(2).min(self.config.reconnect_max);
            self.resource_metrics.timer_fires = self.resource_metrics.timer_fires.saturating_add(1);
        }
    }

    fn shutdown(&mut self, herdr_exit: bool) {
        self.pending_focus.clear();
        self.device_ready = false;
        self.herdr_events.close();
        self.usb.close();
        if herdr_exit {
            self.lifecycle.on_herdr_exit();
        } else {
            self.lifecycle.on_process_crash();
        }
    }
}

fn reconnect_sleep(deadline: Option<Instant>) -> impl std::future::Future<Output = ()> {
    async move {
        match deadline {
            Some(deadline) => sleep(deadline.saturating_duration_since(Instant::now())).await,
            None => std::future::pending().await,
        }
    }
}

fn codex_sleep(deadline: Option<Instant>) -> impl std::future::Future<Output = ()> {
    reconnect_sleep(deadline)
}

fn wire_source_status(status: ModelSourceStatus) -> WireSourceStatus {
    match status {
        ModelSourceStatus::Current => WireSourceStatus::Current,
        ModelSourceStatus::Empty => WireSourceStatus::Empty,
        ModelSourceStatus::Stale => WireSourceStatus::Stale,
        ModelSourceStatus::Unavailable => WireSourceStatus::Unavailable,
        ModelSourceStatus::Offline => WireSourceStatus::Offline,
    }
}

fn wire_agent(entry: &super::model::AgentEntry) -> Agent {
    let (pane_id, terminal_id, agent_session, source_revision) = entry.identity.as_ref().map_or_else(
        || (String::new(), String::new(), None, 0),
        |identity| (
            identity.pane_id.clone(),
            identity.terminal_id.clone(),
            identity.agent_session.clone(),
            identity.source_revision,
        ),
    );
    Agent {
        slot: entry.slot as u8,
        entry_id: entry.entry_id.clone(),
        title: entry.title.clone(),
        discriminator: entry.discriminator.clone(),
        since: entry.since.clone(),
        age: entry.age.clone(),
        state: match entry.state.as_str() {
            "blocked" => v2::AgentState::Blocked,
            "finished" => v2::AgentState::Finished,
            "working" => v2::AgentState::Working,
            "idle" => v2::AgentState::Idle,
            "settled" => v2::AgentState::Settled,
            "empty" => v2::AgentState::Empty,
            _ => v2::AgentState::Unknown,
        },
        pane_id,
        terminal_id,
        agent_session,
        source_revision,
    }
}

fn focus_payload(intent: &ModelFocusIntent, status: FocusStatus, focused: bool) -> Value {
    let outcome = match status {
        FocusStatus::Accepted => FocusOutcome::Accepted,
        FocusStatus::Vanished => FocusOutcome::Vanished,
        FocusStatus::Offline => FocusOutcome::HerdrOffline,
        FocusStatus::Uncertain => FocusOutcome::Uncertain,
        FocusStatus::Stale | FocusStatus::WrongEpoch | FocusStatus::WrongRevision | FocusStatus::SourceRevisionChanged => FocusOutcome::StaleTarget,
        FocusStatus::Empty => FocusOutcome::NotFound,
        _ => FocusOutcome::Rejected,
    };
    let identity = &intent.binding.identity;
    let typed = FocusResultPayload {
        action_id: intent.action_id.clone(),
        outcome,
        host_epoch: intent.binding.host_epoch.clone(),
        snapshot_revision: intent.binding.snapshot_revision,
        slot: intent.binding.slot as u8,
        entry_id: intent.binding.entry_id.clone(),
        pane_id: identity.pane_id.clone(),
        terminal_id: identity.terminal_id.clone(),
        agent_session: identity.agent_session.clone(),
        source_revision: identity.source_revision,
        focused,
    };
    serde_json::to_value(typed).unwrap_or_else(|_| json!({
        "action_id": intent.action_id,
        "outcome": "failed",
        "host_epoch": intent.binding.host_epoch,
        "snapshot_revision": intent.binding.snapshot_revision,
        "slot": intent.binding.slot,
        "entry_id": intent.binding.entry_id,
        "pane_id": identity.pane_id,
        "terminal_id": identity.terminal_id,
        "agent_session": identity.agent_session,
        "source_revision": identity.source_revision,
        "focused": false,
    }))
}

struct BlockingHerdr<'a> {
    client: &'a mut HerdrClient,
}

impl FocusHerdrPort for BlockingHerdr<'_> {
    fn complete_read(&mut self) -> Result<Vec<Value>, FocusError> {
        tokio::runtime::Handle::current()
            .block_on(self.client.agent_list())
            .map_err(map_focus_error)
    }

    fn focus(&mut self, pane_id: &str) -> Result<Value, FocusError> {
        tokio::runtime::Handle::current()
            .block_on(self.client.focus_pane(pane_id.to_owned()))
            .map(|ack| json!({
                "pane_id": ack.pane_id,
                "terminal_id": ack.terminal_id,
                "agent_session": ack.agent_session,
                "focused": ack.focused,
            }))
            .map_err(map_focus_error)
    }
}

fn map_focus_error(error: HerdrError) -> FocusError {
    match error.kind() {
        crate::ports::herdr::HerdrErrorCode::Unavailable | crate::ports::herdr::HerdrErrorCode::EndOfStream => FocusError::offline("Herdr unavailable"),
        crate::ports::herdr::HerdrErrorCode::Timeout => FocusError::timeout("Herdr request timed out"),
        crate::ports::herdr::HerdrErrorCode::InvalidShape | crate::ports::herdr::HerdrErrorCode::MissingResult => FocusError::failed("Herdr response shape invalid"),
        _ => FocusError::failed("Herdr request failed"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_has_bounded_explicit_deadlines() {
        let config = CoordinatorConfig::default();
        assert!(config.validate().is_ok());
        assert!(config.reconnect_max <= DEFAULT_RECONNECT_MAX);
    }
}
