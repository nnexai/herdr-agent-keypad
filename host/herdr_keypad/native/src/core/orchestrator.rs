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
use crate::ports::control::{ControlEndpoint, ControlReply, ControlRequest};
use crate::ports::herdr::{HerdrClient, HerdrError, HerdrEventStream};
use crate::ports::lifecycle::{LifecycleCommand, LifecycleOwner, ResourceMetrics, RuntimePaths};
use crate::ports::logging::{SafeLogger, TraceConfig};
use crate::ports::status::{BridgeStatus, SafeCode, StatusSnapshot};
use crate::ports::usb::{UsbError, UsbEvent, UsbPort};
use crate::protocol::v2::{self, Agent, AgentSnapshot, Codex, Diagnostics, FocusIntentPayload, FocusOutcome, FocusResultPayload, FrameType, Payload, ProtocolFrame, SourceStatus as WireSourceStatus};
use crate::{BridgeError, Cancellation};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::future::{pending, ready, Future};
use std::time::Duration;
use tokio::time::{sleep, Instant};

const DEFAULT_HERDR_TIMEOUT: Duration = Duration::from_secs(2);
const DEFAULT_SNAPSHOT_ACK_TIMEOUT: Duration = Duration::from_secs(2);
const DEFAULT_CODEX_DEADLINE: Duration = Duration::from_secs(15);
const DEFAULT_RECONNECT_INITIAL: Duration = Duration::from_millis(500);
const DEFAULT_RECONNECT_MAX: Duration = Duration::from_secs(8);
const EVENT_WAIT: Duration = Duration::from_secs(24 * 60 * 60);
const CONTROL_REQUEST_TIMEOUT: Duration = Duration::from_secs(2);
pub const FOCUS_QUEUE_CAPACITY: usize = 16;
const UNAVAILABLE_DIAGNOSTIC: &str = "UNAVAL";

/// Integration timing knobs.  All values are bounded and deadlines are created
/// only for recovery/freshness work; a healthy event stream has no ticker.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CoordinatorConfig {
    pub herdr_timeout: Duration,
    pub snapshot_ack_timeout: Duration,
    pub codex_deadline: Duration,
    pub codex_interval: Duration,
    pub reconnect_initial: Duration,
    pub reconnect_max: Duration,
}

impl Default for CoordinatorConfig {
    fn default() -> Self {
        Self {
            herdr_timeout: DEFAULT_HERDR_TIMEOUT,
            snapshot_ack_timeout: DEFAULT_SNAPSHOT_ACK_TIMEOUT,
            codex_deadline: DEFAULT_CODEX_DEADLINE,
            codex_interval: FULL_POLL_INTERVAL,
            reconnect_initial: DEFAULT_RECONNECT_INITIAL,
            reconnect_max: DEFAULT_RECONNECT_MAX,
        }
    }
}

impl CoordinatorConfig {
    pub fn validate(self) -> Result<Self, BridgeError> {
        if self.herdr_timeout.is_zero()
            || self.herdr_timeout > Duration::from_secs(120)
            || self.snapshot_ack_timeout.is_zero()
            || self.snapshot_ack_timeout > Duration::from_secs(120)
            || self.codex_deadline.is_zero()
            || self.codex_deadline > Duration::from_secs(120)
            || self.codex_interval.is_zero()
            || self.codex_interval > FULL_POLL_INTERVAL
            || self.reconnect_initial.is_zero()
            || self.reconnect_initial > self.reconnect_max
            || self.reconnect_max > DEFAULT_RECONNECT_MAX
        {
            return Err(BridgeError::invalid_input("coordinator timing is outside bounded limits"));
        }
        Ok(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PendingPublication {
    request_sequence: u64,
    host_epoch: String,
    snapshot_revision: u64,
    source_status: String,
    ack_deadline: Instant,
}

/// One production coordinator joining every completed port.
pub struct RuntimeCoordinator {
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
    pending_publication: Option<PendingPublication>,
    publication_dirty: bool,
    herdr_healthy: bool,
    herdr_dirty: bool,
    herdr_delay: Duration,
    herdr_due: Option<Instant>,
    usb_delay: Duration,
    usb_due: Option<Instant>,
    codex_due: Option<Instant>,
    device_link_ready: bool,
    usb_reconnect_attempt: u32,
    usb_last_error: Option<SafeCode>,
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
        let logging_enabled = startup.effective.logging_enabled;
        let lifecycle = LifecycleOwner::from_startup(paths.clone(), startup)
            .map_err(|error| BridgeError::protocol(format!("lifecycle authority: {error:?}")))?;
        let host_epoch = format!("host-{}", std::process::id());
        let projection = InboxProjection::new(host_epoch)
            .map_err(|error| BridgeError::invalid_input(error.to_string()))?;
        Ok(Self {
            lifecycle,
            herdr,
            herdr_events,
            codex,
            usb: UsbPort::new(platform, binding_path),
            projection,
            logger: SafeLogger::new(TraceConfig { enabled: logging_enabled }),
            config,
            cancellation: Cancellation::new(),
            pending_focus: VecDeque::with_capacity(FOCUS_QUEUE_CAPACITY),
            current: None,
            last_payload: None,
            pending_publication: None,
            publication_dirty: false,
            herdr_healthy: false,
            herdr_dirty: false,
            herdr_delay: config.reconnect_initial,
            herdr_due: None,
            usb_delay: config.reconnect_initial,
            usb_due: None,
            codex_due: None,
            device_link_ready: false,
            usb_reconnect_attempt: 0,
            usb_last_error: None,
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
        let mut status = self.lifecycle.status();
        if status.state != BridgeStatus::Stopped {
            status.device_state = if self.usb.connected() && self.device_link_ready {
                BridgeStatus::Ready
            } else {
                BridgeStatus::DeviceUnavailable
            };
            status.herdr_state = match (
                self.herdr_healthy,
                self.current.as_ref().map(|snapshot| snapshot.source_status),
            ) {
                (true, Some(ModelSourceStatus::Current | ModelSourceStatus::Empty)) => {
                    BridgeStatus::Running
                }
                (true, Some(ModelSourceStatus::Stale)) => BridgeStatus::Stale,
                _ => BridgeStatus::HerdrUnavailable,
            };
            status.codex_state = match self.codex.view().source_state.as_str() {
                "current" => BridgeStatus::Ready,
                "stale" => BridgeStatus::Stale,
                "codex_offline" => BridgeStatus::CodexUnavailable,
                _ => BridgeStatus::Unavailable,
            };
            status.reconnect_attempt = self.usb_reconnect_attempt;
            status.backoff_ms = self
                .usb_due
                .map(|deadline| {
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_millis()
                        .min(u128::from(u64::MAX)) as u64
                })
                .unwrap_or(0);
            if let Some(error) = self.usb_last_error {
                status.last_error = Some(error);
            }
            status.state = aggregate_runtime_state(
                status.device_state,
                status.herdr_state,
                status.codex_state,
            );
        }
        status
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
        let _trace = self.logger.install_stderr();
        let _ = self.lifecycle.handle(LifecycleCommand::Start);
        let control = self
            .lifecycle
            .bind_control()
            .await
            .map_err(|error| BridgeError::protocol(format!("control endpoint: {error:?}")))?;
        self.try_connect_herdr().await;
        self.try_connect_usb().await;
        self.collect_codex_and_publish().await;
        loop {
            let publication_ack_due = self
                .pending_publication
                .as_ref()
                .map(|publication| publication.ack_deadline);
            tokio::select! {
                _ = self.cancellation.cancelled() => {
                    self.shutdown(false);
                    return Ok(());
                }
                control_stream = control.accept_same_user() => {
                    let mut stream = match control_stream {
                        Ok(stream) => stream,
                        Err(_) => continue,
                    };
                    let request = match tokio::time::timeout(
                        CONTROL_REQUEST_TIMEOUT,
                        control.receive_request(&mut stream),
                    )
                    .await
                    {
                        Ok(Ok(request)) => request,
                        _ => continue,
                    };
                    let stopping = matches!(&request, ControlRequest::Stop { .. });
                    let restarting = matches!(&request, ControlRequest::Restart { .. });
                    let reply = match request {
                        ControlRequest::Status { .. } => ControlReply::Status(self.status()),
                        request => self.lifecycle.handle_control(request),
                    };
                    ControlEndpoint::send_reply(&mut stream, &reply)
                        .await
                        .map_err(|error| BridgeError::protocol(format!("control reply: {error:?}")))?;
                    let restart_ack = restarting && matches!(&reply, crate::ports::control::ControlReply::Restarted { .. });
                    if stopping || restart_ack {
                        if restarting {
                            self.shutdown_for_restart();
                        } else {
                            self.close_boundaries();
                        }
                        return Ok(());
                    }
                }
                _ = async {
                    if self.herdr_dirty { ready(()) } else { pending().await }
                } => {
                    self.herdr_dirty = false;
                    self.refresh_herdr().await;
                }
                event = async {
                    if self.herdr_events.active() {
                        self.herdr_events.next_event(EVENT_WAIT).await
                    } else {
                        pending().await
                    }
                } => {
                    if matches!(
                        &event,
                        Ok(Some(crate::BridgeEvent::HerdrAuthorityEnded | crate::BridgeEvent::AuthorityCancelled))
                    ) {
                        self.shutdown(true);
                        return Ok(());
                    }
                    self.handle_herdr_event(event).await?;
                }
                frame = async {
                    if self.usb.connected() {
                        self.usb.poll().await
                    } else {
                        pending().await
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
                _ = reconnect_sleep(publication_ack_due) => {
                    self.mark_usb_unavailable(SafeCode::DeviceUnavailable);
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
                self.current = Some(self.projection.invalidate("stale"));
                self.herdr_dirty = true;
                self.publish_current().await;
            }
            Ok(Some(crate::BridgeEvent::HerdrAuthorityEnded)) | Ok(Some(crate::BridgeEvent::AuthorityCancelled)) => {
                self.shutdown(true);
            }
            Ok(Some(crate::BridgeEvent::HerdrUnavailable)) | Err(_) => {
                self.mark_herdr_unavailable("offline").await;
            }
            Ok(Some(crate::BridgeEvent::DeviceDisconnected))
            | Ok(Some(crate::BridgeEvent::DeviceConnected { .. }))
            | Ok(None) => {}
        }
        Ok(())
    }

    async fn handle_usb_event(&mut self, event: Result<Option<UsbEvent>, UsbError>) -> Result<(), BridgeError> {
        match event {
            Ok(Some(UsbEvent::Connected { .. })) => {
                self.device_link_ready = false;
                self.usb_due = None;
                self.usb_delay = self.config.reconnect_initial;
                self.publish_current().await;
            }
            Ok(Some(UsbEvent::SnapshotAck(ack))) => {
                let Some(expected) = self.pending_publication.take() else {
                    self.mark_usb_unavailable(SafeCode::PayloadRejected);
                    return Ok(());
                };
                let accepted = ack.accepted
                    && ack.reply_to == expected.request_sequence
                    && ack.host_epoch == expected.host_epoch
                    && ack.snapshot_revision == expected.snapshot_revision
                    && ack.source_status == expected.source_status;
                if !accepted {
                    self.mark_usb_unavailable(SafeCode::PayloadRejected);
                    return Ok(());
                }
                self.publication_count = self.publication_count.saturating_add(1);
                self.resource_metrics.wakes = self.resource_metrics.wakes.saturating_add(1);
                self.device_link_ready = true;
                self.usb_reconnect_attempt = 0;
                self.usb_last_error = None;
                if self.publication_dirty {
                    self.publication_dirty = false;
                    self.publish_current().await;
                }
            }
            Ok(Some(UsbEvent::FocusIntent(intent))) => {
                self.accept_focus_payload(intent.payload, intent.sequence)?;
            }
            Ok(Some(UsbEvent::Disconnected)) => {
                self.mark_usb_unavailable(SafeCode::DeviceUnavailable)
            }
            Ok(Some(UsbEvent::Failed { .. })) | Err(_) => {
                self.mark_usb_unavailable(SafeCode::DeviceUnavailable)
            }
            Ok(None) => {}
        }
        if self.device_link_ready {
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
                self.device_link_ready = false;
                self.usb_due = None;
                self.usb_delay = self.config.reconnect_initial;
                self.publish_current().await;
            }
            Ok(_) | Err(_) => self.mark_usb_unavailable(SafeCode::DeviceUnavailable),
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
        self.publish_current().await;
        self.schedule_herdr();
    }

    fn mark_usb_unavailable(&mut self, error: SafeCode) {
        self.device_link_ready = false;
        self.usb_reconnect_attempt = self.usb_reconnect_attempt.saturating_add(1);
        self.usb_last_error = Some(error);
        self.pending_focus.clear();
        self.pending_publication = None;
        self.publication_dirty = false;
        self.usb.close();
        self.schedule_usb();
    }

    async fn collect_codex_and_publish(&mut self) {
        let result = tokio::task::block_in_place(|| self.codex.collect());
        self.codex_due = Some(Instant::now() + self.config.codex_interval);
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
        if self.pending_publication.is_some() {
            self.publication_dirty = true;
            return Ok(());
        }
        let source_status = snapshot.source_status.as_str().to_owned();
        match self.usb.send_snapshot(payload).await {
            Ok(request_sequence) => {
                self.pending_publication = Some(PendingPublication {
                    request_sequence,
                    host_epoch: snapshot.host_epoch,
                    snapshot_revision: u64::from(snapshot.snapshot_revision),
                    source_status,
                    ack_deadline: Instant::now() + self.config.snapshot_ack_timeout,
                });
            }
            Err(_) => self.mark_usb_unavailable(SafeCode::DeviceUnavailable),
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
            firmware_version: UNAVAILABLE_DIAGNOSTIC.to_owned(),
            protocol_version: v2::PROTOCOL_VERSION,
            bridge_version: env!("CARGO_PKG_VERSION").to_owned(),
            device_suffix: UNAVAILABLE_DIAGNOSTIC.to_owned(),
            session_suffix: UNAVAILABLE_DIAGNOSTIC.to_owned(),
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
        if self.pending_focus.len() >= FOCUS_QUEUE_CAPACITY {
            self.pending_focus.pop_front();
        }
        if !self.pending_focus.iter().any(|pending| pending.action_id == intent.action_id) {
            self.pending_focus.push_back(intent);
        }
        self.resource_metrics.queue_high_water = self.resource_metrics.queue_high_water.max(self.pending_focus.len());
        Ok(())
    }

    async fn drain_focus(&mut self) -> Result<(), BridgeError> {
        if !self.device_link_ready {
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
                self.mark_usb_unavailable(SafeCode::DeviceUnavailable);
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

    fn close_boundaries(&mut self) {
        self.pending_focus.clear();
        self.pending_publication = None;
        self.publication_dirty = false;
        self.device_link_ready = false;
        self.usb_reconnect_attempt = 0;
        self.usb_last_error = None;
        self.herdr_events.close();
        self.usb.close();
    }

    fn shutdown_for_restart(&mut self) {
        self.close_boundaries();
        self.lifecycle.on_restart();
    }

    fn shutdown(&mut self, herdr_exit: bool) {
        self.close_boundaries();
        if herdr_exit {
            self.lifecycle.on_herdr_exit();
        } else {
            self.lifecycle.on_process_crash();
        }
    }
}

fn reconnect_sleep(deadline: Option<Instant>) -> impl Future<Output = ()> {
    async move {
        match deadline {
            Some(deadline) => sleep(deadline.saturating_duration_since(Instant::now())).await,
            None => pending().await,
        }
    }
}

fn codex_sleep(deadline: Option<Instant>) -> impl Future<Output = ()> {
    reconnect_sleep(deadline)
}

fn aggregate_runtime_state(
    device_state: BridgeStatus,
    herdr_state: BridgeStatus,
    codex_state: BridgeStatus,
) -> BridgeStatus {
    if device_state == BridgeStatus::Ready
        && herdr_state == BridgeStatus::Running
        && codex_state == BridgeStatus::Ready
    {
        BridgeStatus::Ready
    } else {
        BridgeStatus::Stale
    }
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
        state: if entry.identity.is_none() {
            v2::AgentState::Empty
        } else {
            match entry.state.as_str() {
                "blocked" => v2::AgentState::Blocked,
                "finished" => v2::AgentState::Finished,
                "working" => v2::AgentState::Working,
                "idle" => v2::AgentState::Idle,
                "settled" => v2::AgentState::Settled,
                _ => v2::AgentState::Unknown,
            }
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
    use crate::ports::codex::{
        ChildExit, CodexChildError, CodexProcess, CodexProcessFactory,
    };
    use crate::ports::usb::{
        DeviceCandidate, PlatformSerial, SerialConnection, SnapshotAck, UsbError,
        EXPECTED_CDC_INTERFACE, EXPECTED_PID, EXPECTED_SERIAL, EXPECTED_VID,
    };
    use serde_json::json;
    use std::collections::VecDeque;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    };
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, DuplexStream};
    use tokio::net::UnixListener;

    struct TestRoot(std::path::PathBuf);

    impl TestRoot {
        fn new() -> Self {
            let suffix = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("clock")
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "herdr-keypad-coordinator-{}-{suffix}",
                std::process::id()
            ));
            std::fs::create_dir(&path).expect("test root");
            Self(path)
        }
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[derive(Clone)]
    struct FakePlatform {
        streams: Arc<Mutex<VecDeque<DuplexStream>>>,
    }

    impl PlatformSerial for FakePlatform {
        fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError> {
            Ok(vec![DeviceCandidate {
                device: "/dev/serial/by-id/usb-herdr-test".to_owned(),
                vid: Some(EXPECTED_VID),
                pid: Some(EXPECTED_PID),
                serial_number: Some(EXPECTED_SERIAL.to_owned()),
                location: Some("1-1:1.1".to_owned()),
                manufacturer: Some("Espressif".to_owned()),
                product: Some("TinyUSB CDC".to_owned()),
                interface: Some(EXPECTED_CDC_INTERFACE.to_owned()),
                stable: true,
            }])
        }

        fn open(&self, _: &DeviceCandidate) -> Result<SerialConnection, UsbError> {
            self.streams
                .lock()
                .expect("stream queue")
                .pop_front()
                .map(|stream| Box::new(stream) as SerialConnection)
                .ok_or(UsbError::OpenFailed)
        }
    }

    #[derive(Clone)]
    struct CountingPlatform {
        streams: Arc<Mutex<VecDeque<DuplexStream>>>,
        opens: Arc<AtomicUsize>,
    }

    impl PlatformSerial for CountingPlatform {
        fn enumerate(&self) -> Result<Vec<DeviceCandidate>, UsbError> {
            FakePlatform {
                streams: Arc::new(Mutex::new(VecDeque::new())),
            }
            .enumerate()
        }

        fn open(&self, _: &DeviceCandidate) -> Result<SerialConnection, UsbError> {
            self.opens.fetch_add(1, Ordering::SeqCst);
            self.streams
                .lock()
                .expect("stream queue")
                .pop_front()
                .map(|stream| Box::new(stream) as SerialConnection)
                .ok_or(UsbError::OpenFailed)
        }
    }

    fn unconnected_coordinator(config: CoordinatorConfig) -> (TestRoot, RuntimeCoordinator) {
        let root = TestRoot::new();
        let config_dir = root.0.join("config");
        let state_dir = root.0.join("state");
        std::fs::create_dir(&config_dir).expect("config directory");
        std::fs::create_dir(&state_dir).expect("state directory");
        let binding = root.0.join("binding.json");
        std::fs::write(
            &binding,
            br#"{"schema_version":1,"device_id":"paired-device","protocol":1,"firmware":"phase1-bringup"}"#,
        )
        .expect("binding");
        let startup = StartupConfig::load(&config_dir, &binding);
        let paths = RuntimePaths::new(
            &config_dir,
            &state_dir,
            root.0.join("herdr.sock"),
            root.0.join("herdr"),
            std::process::id(),
        );
        let coordinator = RuntimeCoordinator::with_config(
            paths,
            startup,
            &binding,
            Box::new(FakePlatform {
                streams: Arc::new(Mutex::new(VecDeque::new())),
            }),
            config,
        )
        .expect("coordinator");
        (root, coordinator)
    }

    fn pending_publication() -> PendingPublication {
        PendingPublication {
            request_sequence: 7,
            host_epoch: "host-test".to_owned(),
            snapshot_revision: 11,
            source_status: "current".to_owned(),
            ack_deadline: Instant::now() + DEFAULT_SNAPSHOT_ACK_TIMEOUT,
        }
    }

    fn exact_ack() -> SnapshotAck {
        SnapshotAck {
            reply_to: 7,
            accepted: true,
            host_epoch: "host-test".to_owned(),
            snapshot_revision: 11,
            source_status: "current".to_owned(),
            reason: "committed".to_owned(),
        }
    }

    fn install_stale_projection(coordinator: &mut RuntimeCoordinator) -> ProjectionSnapshot {
        let current = coordinator
            .projection
            .refresh(
                &[herdr_agent(false)],
                &[json!({"workspace_id":"workspace-1","label":"repo"})],
            )
            .expect("current projection");
        coordinator.current = Some(current);
        let stale = coordinator.projection.invalidate("stale");
        coordinator
            .payload_for(&stale)
            .expect("stale coalesced projection must remain publishable");
        coordinator.current = Some(stale.clone());
        stale
    }

    struct RepeatingCodexFactory {
        spawns: Arc<AtomicUsize>,
    }

    impl CodexProcessFactory for RepeatingCodexFactory {
        fn spawn(&self, _: &[String]) -> Result<Box<dyn CodexProcess>, CodexChildError> {
            self.spawns.fetch_add(1, Ordering::SeqCst);
            Ok(Box::new(FakeCodexProcess {
                lines: VecDeque::from([
                    json!({"id":1,"result":{"ok":true}}),
                    json!({"id":2,"result":{"account":{"type":"chatgpt"}}}),
                    json!({
                        "id":3,
                        "result":{
                            "rateLimits":{
                                "primary":{"usedPercent":10},
                                "secondary":{"usedPercent":20}
                            }
                        }
                    }),
                ]),
                stopped: false,
            }))
        }
    }

    struct FakeCodexProcess {
        lines: VecDeque<Value>,
        stopped: bool,
    }

    impl CodexProcess for FakeCodexProcess {
        fn send_line(&mut self, _: &[u8]) -> Result<(), CodexChildError> {
            Ok(())
        }

        fn read_line(&mut self, _: Duration) -> Result<Vec<u8>, CodexChildError> {
            self.lines
                .pop_front()
                .map(|value| serde_json::to_vec(&value).expect("Codex response JSON"))
                .ok_or(CodexChildError { code: "E-2403" })
        }

        fn try_wait(&mut self) -> Result<Option<ChildExit>, CodexChildError> {
            Ok(self.stopped.then(|| {
                ChildExit::new("exited", Some(0), None).expect("valid child exit")
            }))
        }

        fn terminate(&mut self) -> Result<(), CodexChildError> {
            self.stopped = true;
            Ok(())
        }

        fn kill(&mut self) -> Result<(), CodexChildError> {
            self.stopped = true;
            Ok(())
        }

        fn wait(&mut self, _: Duration) -> Result<Option<ChildExit>, CodexChildError> {
            self.stopped = true;
            Ok(Some(
                ChildExit::new("exited", Some(0), None).expect("valid child exit"),
            ))
        }
    }

    fn herdr_agent(focused: bool) -> Value {
        json!({
            "pane_id":"pane-1",
            "terminal_id":"term-pane-1",
            "workspace_id":"workspace-1",
            "tab_id":"tab-pane-1",
            "agent_status":"working",
            "focused":focused,
            "revision":1,
            "state_change_seq":1,
            "cwd":"repo",
            "title":"Runtime",
            "tokens":{"rank":"0","title":"Runtime"},
            "agent":"agent",
            "agent_session":null
        })
    }

    async fn serve_herdr(listener: UnixListener) {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(async move {
                let (read_half, mut write_half) = stream.into_split();
                let mut lines = BufReader::new(read_half).lines();
                let Ok(Some(line)) = lines.next_line().await else {
                    return;
                };
                let Ok(request): Result<Value, _> = serde_json::from_str(&line) else {
                    return;
                };
                let method = request["method"].as_str().unwrap_or_default();
                let result = match method {
                    "events.subscribe" => json!({"accepted":true}),
                    "session.snapshot" => json!({"snapshot":{"revision":1}}),
                    "agent.list" => json!({"agents":[herdr_agent(false)]}),
                    "workspace.list" => {
                        json!({"workspaces":[{"workspace_id":"workspace-1","label":"repo"}]})
                    }
                    "agent.focus" => json!({"agent":herdr_agent(true)}),
                    _ => return,
                };
                let mut response = serde_json::to_vec(&json!({
                    "jsonrpc":"2.0",
                    "id":request["id"],
                    "result":result
                }))
                .expect("Herdr response JSON");
                response.push(b'\n');
                if write_half.write_all(&response).await.is_err() {
                    return;
                }
                if method == "events.subscribe" {
                    pending::<()>().await;
                }
            });
        }
    }

    fn test_digest(payload: &Value) -> String {
        fn canonical(value: &Value, output: &mut Vec<u8>) {
            match value {
                Value::Null => output.extend_from_slice(b"null"),
                Value::Bool(value) => {
                    output.extend_from_slice(if *value { b"true" } else { b"false" })
                }
                Value::Number(value) => output.extend_from_slice(value.to_string().as_bytes()),
                Value::String(value) => output.extend_from_slice(
                    serde_json::to_string(value).expect("string JSON").as_bytes(),
                ),
                Value::Array(values) => {
                    output.push(b'[');
                    for (index, value) in values.iter().enumerate() {
                        if index > 0 {
                            output.push(b',');
                        }
                        canonical(value, output);
                    }
                    output.push(b']');
                }
                Value::Object(values) => {
                    output.push(b'{');
                    let mut keys: Vec<_> = values.keys().collect();
                    keys.sort();
                    for (index, key) in keys.into_iter().enumerate() {
                        if index > 0 {
                            output.push(b',');
                        }
                        output.extend_from_slice(
                            serde_json::to_string(key).expect("key JSON").as_bytes(),
                        );
                        output.push(b':');
                        canonical(&values[key], output);
                    }
                    output.push(b'}');
                }
            }
        }
        let mut bytes = Vec::new();
        canonical(payload, &mut bytes);
        let mut digest = 0xcbf29ce484222325u64;
        for byte in bytes {
            digest ^= u64::from(byte);
            digest = digest.wrapping_mul(0x100000001b3);
        }
        format!("{digest:016x}")
    }

    fn test_frame(
        frame_type: &str,
        session_id: &str,
        sequence: u64,
        reply_to: Option<u64>,
        payload: Value,
    ) -> Value {
        json!({
            "v":2,
            "type":frame_type,
            "boot_id":"device-boot-1",
            "session_id":session_id,
            "seq":sequence,
            "reply_to":reply_to,
            "digest":test_digest(&payload),
            "payload":payload
        })
    }

    async fn write_test_frame(
        writer: &mut (impl tokio::io::AsyncWrite + Unpin),
        frame: Value,
    ) {
        let mut bytes = serde_json::to_vec(&frame).expect("device frame JSON");
        bytes.push(b'\n');
        writer.write_all(&bytes).await.expect("device frame write");
    }

    async fn serve_device_without_snapshot_ack(stream: DuplexStream) {
        let (read_half, mut write_half) = tokio::io::split(stream);
        let mut lines = BufReader::new(read_half).lines();
        let hello_line = lines
            .next_line()
            .await
            .expect("hello read")
            .expect("hello line");
        let hello: Value = serde_json::from_str(&hello_line).expect("hello JSON");
        let session = hello["session_id"].as_str().expect("session");
        let hello_payload = json!({
            "accepted":true,
            "device_id":"paired-device",
            "firmware":"phase1-bringup",
            "protocol":1
        });
        let mut hello_ack = serde_json::to_vec(&json!({
            "v":1,
            "type":"hello_ack",
            "boot_id":"device-boot-1",
            "session_id":session,
            "seq":1,
            "reply_to":1,
            "digest":test_digest(&hello_payload),
            "payload":hello_payload
        }))
        .expect("hello ACK JSON");
        hello_ack.push(b'\n');
        write_half
            .write_all(&hello_ack)
            .await
            .expect("hello ACK write");
        let snapshot = lines
            .next_line()
            .await
            .expect("snapshot read")
            .expect("snapshot line");
        let frame: Value = serde_json::from_str(&snapshot).expect("snapshot JSON");
        assert_eq!(frame["type"], "agent_snapshot");
        pending::<()>().await;
    }

    async fn serve_device(
        stream: DuplexStream,
        snapshots: Arc<AtomicUsize>,
        focus_results: Arc<AtomicUsize>,
    ) {
        let (read_half, mut write_half) = tokio::io::split(stream);
        let mut lines = BufReader::new(read_half).lines();
        let hello_line = lines
            .next_line()
            .await
            .expect("hello read")
            .expect("hello line");
        let hello: Value = serde_json::from_str(&hello_line).expect("hello JSON");
        let session = hello["session_id"].as_str().expect("session").to_owned();
        let mut sequence = 1_u64;
        let hello_payload = json!({
            "accepted":true,
            "device_id":"paired-device",
            "firmware":"phase1-bringup",
            "protocol":1
        });
        let mut hello_ack = serde_json::to_vec(&json!({
            "v":1,
            "type":"hello_ack",
            "boot_id":"device-boot-1",
            "session_id":session,
            "seq":sequence,
            "reply_to":1,
            "digest":test_digest(&hello_payload),
            "payload":hello_payload
        }))
        .expect("hello ACK JSON");
        hello_ack.push(b'\n');
        write_half
            .write_all(&hello_ack)
            .await
            .expect("hello ACK write");

        let mut focus_sent = false;
        while let Ok(Some(line)) = lines.next_line().await {
            let frame: Value = serde_json::from_str(&line).expect("host frame JSON");
            match frame["type"].as_str() {
                Some("agent_snapshot") => {
                    snapshots.fetch_add(1, Ordering::SeqCst);
                    let payload = frame["payload"].clone();
                    sequence += 1;
                    write_test_frame(
                        &mut write_half,
                        test_frame(
                            "snapshot_ack",
                            &session,
                            sequence,
                            frame["seq"].as_u64(),
                            json!({
                                "accepted":true,
                                "host_epoch":payload["host_epoch"],
                                "snapshot_revision":payload["snapshot_revision"],
                                "source_status":payload["source_status"],
                                "reason":"committed"
                            }),
                        ),
                    )
                    .await;
                    if !focus_sent
                        && payload["codex"]["source_state"].as_str() == Some("current")
                    {
                        focus_sent = true;
                        let agent = &payload["agents"][0];
                        sequence += 1;
                        write_test_frame(
                            &mut write_half,
                            test_frame(
                                "focus_intent",
                                &session,
                                sequence,
                                None,
                                json!({
                                    "action_id":"focus-1",
                                    "host_epoch":payload["host_epoch"],
                                    "snapshot_revision":payload["snapshot_revision"],
                                    "slot":agent["slot"],
                                    "entry_id":agent["entry_id"],
                                    "pane_id":agent["pane_id"],
                                    "terminal_id":agent["terminal_id"],
                                    "agent_session":agent["agent_session"],
                                    "source_revision":agent["source_revision"]
                                }),
                            ),
                        )
                        .await;
                    }
                }
                Some("focus_result") => {
                    assert_eq!(frame["payload"]["outcome"], "accepted");
                    assert_eq!(frame["payload"]["focused"], true);
                    focus_results.fetch_add(1, Ordering::SeqCst);
                }
                _ => {}
            }
        }
    }

    #[tokio::test]
    async fn invalidation_before_an_exact_ack_still_establishes_link_readiness() {
        let (_root, mut coordinator) = unconnected_coordinator(CoordinatorConfig::default());
        coordinator.pending_publication = Some(pending_publication());
        coordinator.publication_dirty = true;
        install_stale_projection(&mut coordinator);

        coordinator
            .handle_usb_event(Ok(Some(UsbEvent::SnapshotAck(exact_ack()))))
            .await
            .expect("exact ACK handling");

        assert!(
            coordinator.device_link_ready,
            "an accepted exact ACK proves link health even when a newer generation is coalesced"
        );
        assert!(!coordinator.publication_dirty);
        assert!(
            coordinator.last_payload.is_some(),
            "the coalesced generation must continue publication after the accepted ACK"
        );
        assert_eq!(
            coordinator.current.as_ref().map(|snapshot| snapshot.source_status),
            Some(ModelSourceStatus::Stale)
        );
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn focus_waiting_during_coalesced_publication_gets_a_bounded_result() {
        let (_root, mut coordinator) = unconnected_coordinator(CoordinatorConfig::default());
        coordinator.pending_publication = Some(pending_publication());
        coordinator.publication_dirty = true;
        install_stale_projection(&mut coordinator);
        coordinator.pending_focus.push_back(ModelFocusIntent::new(
            "focus-during-coalesce",
            Binding {
                host_epoch: "host-test".to_owned(),
                snapshot_revision: 10,
                slot: 0,
                entry_id: "pane-1".to_owned(),
                identity: Identity {
                    pane_id: "pane-1".to_owned(),
                    terminal_id: "terminal-1".to_owned(),
                    agent_session: None,
                    source_revision: 1,
                    workspace_id: String::new(),
                    tab_id: String::new(),
                },
            },
        ));

        coordinator
            .handle_usb_event(Ok(Some(UsbEvent::SnapshotAck(exact_ack()))))
            .await
            .expect("exact ACK handling");

        assert!(
            coordinator.pending_focus.is_empty(),
            "stale-generation focus must be rejected and published rather than waiting for quiescence"
        );
    }

    #[tokio::test]
    async fn mismatched_snapshot_ack_fields_never_establish_link_readiness() {
        let mut mismatches = Vec::new();
        let mut rejected = exact_ack();
        rejected.accepted = false;
        mismatches.push(rejected);
        let mut wrong_reply = exact_ack();
        wrong_reply.reply_to += 1;
        mismatches.push(wrong_reply);
        let mut wrong_epoch = exact_ack();
        wrong_epoch.host_epoch = "wrong-host".to_owned();
        mismatches.push(wrong_epoch);
        let mut wrong_revision = exact_ack();
        wrong_revision.snapshot_revision += 1;
        mismatches.push(wrong_revision);
        let mut wrong_source = exact_ack();
        wrong_source.source_status = "stale".to_owned();
        mismatches.push(wrong_source);

        for ack in mismatches {
            let (_root, mut coordinator) =
                unconnected_coordinator(CoordinatorConfig::default());
            coordinator.pending_publication = Some(pending_publication());
            coordinator
                .handle_usb_event(Ok(Some(UsbEvent::SnapshotAck(ack))))
                .await
                .expect("mismatched ACK handling");
            assert!(!coordinator.device_link_ready);
            assert_eq!(coordinator.usb_last_error, Some(SafeCode::PayloadRejected));
        }
    }

    #[test]
    fn ack_timeout_recovery_surfaces_bounded_safe_status() {
        let (_root, mut coordinator) = unconnected_coordinator(CoordinatorConfig::default());
        let _ = coordinator.lifecycle.handle(LifecycleCommand::Start);
        coordinator.mark_usb_unavailable(SafeCode::DeviceUnavailable);

        let status = coordinator.status();
        assert_eq!(status.device_state, BridgeStatus::DeviceUnavailable);
        assert_eq!(status.last_error, Some(SafeCode::DeviceUnavailable));
        assert_eq!(status.reconnect_attempt, 1);
        assert!(status.backoff_ms <= coordinator.config.reconnect_max.as_millis() as u64);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn sent_publication_without_ack_reconnects_within_the_bounded_deadline() {
        let root = TestRoot::new();
        let config_dir = root.0.join("config");
        let state_dir = root.0.join("state");
        std::fs::create_dir(&config_dir).expect("config directory");
        std::fs::create_dir(&state_dir).expect("state directory");
        let binding = root.0.join("binding.json");
        std::fs::write(
            &binding,
            br#"{"schema_version":1,"device_id":"paired-device","protocol":1,"firmware":"phase1-bringup"}"#,
        )
        .expect("binding");
        let herdr_socket = root.0.join("herdr.sock");
        let listener = UnixListener::bind(&herdr_socket).expect("Herdr listener");
        let herdr_task = tokio::spawn(serve_herdr(listener));
        let mut host_streams = VecDeque::new();
        let mut device_tasks = Vec::new();
        for _ in 0..2 {
            let (host_stream, device_stream) = tokio::io::duplex(64 * 1024);
            host_streams.push_back(host_stream);
            device_tasks.push(tokio::spawn(serve_device_without_snapshot_ack(device_stream)));
        }
        let opens = Arc::new(AtomicUsize::new(0));
        let platform = CountingPlatform {
            streams: Arc::new(Mutex::new(host_streams)),
            opens: opens.clone(),
        };
        let startup = StartupConfig::load(&config_dir, &binding);
        let paths = RuntimePaths::new(
            &config_dir,
            &state_dir,
            &herdr_socket,
            root.0.join("herdr"),
            std::process::id(),
        );
        let config = CoordinatorConfig {
            herdr_timeout: Duration::from_millis(250),
            snapshot_ack_timeout: Duration::from_millis(40),
            codex_deadline: Duration::from_millis(250),
            codex_interval: Duration::from_millis(100),
            reconnect_initial: Duration::from_millis(10),
            reconnect_max: Duration::from_millis(20),
        };
        let mut coordinator = RuntimeCoordinator::with_config(
            paths,
            startup,
            &binding,
            Box::new(platform),
            config,
        )
        .expect("coordinator");
        coordinator.codex = CodexCollector::with_factory(
            "codex",
            Duration::from_millis(250),
            Arc::new(RepeatingCodexFactory {
                spawns: Arc::new(AtomicUsize::new(0)),
            }),
        )
        .expect("Codex collector");
        let cancellation = coordinator.cancellation();
        let runtime = tokio::spawn(coordinator.run());

        tokio::time::timeout(Duration::from_millis(500), async {
            while opens.load(Ordering::SeqCst) < 2 {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("missing snapshot ACK never triggered bounded reconnect");

        cancellation.cancel();
        tokio::time::timeout(Duration::from_secs(1), runtime)
            .await
            .expect("runtime cancellation")
            .expect("runtime task")
            .expect("runtime result");
        herdr_task.abort();
        for task in device_tasks {
            task.abort();
        }
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn production_coordinator_advances_codex_cadence_and_focus_together() {
        let root = TestRoot::new();
        let config_dir = root.0.join("config");
        let state_dir = root.0.join("state");
        std::fs::create_dir(&config_dir).expect("config directory");
        std::fs::create_dir(&state_dir).expect("state directory");
        let binding = root.0.join("binding.json");
        std::fs::write(
            &binding,
            br#"{"schema_version":1,"device_id":"paired-device","protocol":1,"firmware":"phase1-bringup"}"#,
        )
        .expect("binding");

        let herdr_socket = root.0.join("herdr.sock");
        let listener = UnixListener::bind(&herdr_socket).expect("Herdr listener");
        let herdr_task = tokio::spawn(serve_herdr(listener));

        let (host_stream, device_stream) = tokio::io::duplex(64 * 1024);
        let platform = FakePlatform {
            streams: Arc::new(Mutex::new(VecDeque::from([host_stream]))),
        };
        let snapshots = Arc::new(AtomicUsize::new(0));
        let focus_results = Arc::new(AtomicUsize::new(0));
        let device_task = tokio::spawn(serve_device(
            device_stream,
            snapshots.clone(),
            focus_results.clone(),
        ));

        let startup = StartupConfig::load(&config_dir, &binding);
        let paths = RuntimePaths::new(
            &config_dir,
            &state_dir,
            &herdr_socket,
            root.0.join("herdr"),
            std::process::id(),
        );
        let config = CoordinatorConfig {
            herdr_timeout: Duration::from_millis(250),
            snapshot_ack_timeout: Duration::from_millis(100),
            codex_deadline: Duration::from_millis(250),
            codex_interval: Duration::from_millis(40),
            reconnect_initial: Duration::from_millis(100),
            reconnect_max: Duration::from_millis(200),
        };
        let mut coordinator = RuntimeCoordinator::with_config(
            paths,
            startup,
            &binding,
            Box::new(platform),
            config,
        )
        .expect("coordinator");
        let codex_spawns = Arc::new(AtomicUsize::new(0));
        coordinator.codex = CodexCollector::with_factory(
            "codex",
            Duration::from_millis(250),
            Arc::new(RepeatingCodexFactory {
                spawns: codex_spawns.clone(),
            }),
        )
        .expect("Codex collector");
        let cancellation = coordinator.cancellation();
        let runtime = tokio::spawn(coordinator.run());

        tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                if codex_spawns.load(Ordering::SeqCst) >= 2
                    && snapshots.load(Ordering::SeqCst) >= 3
                    && focus_results.load(Ordering::SeqCst) >= 1
                {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("Codex cadence and focus result did not progress together");

        cancellation.cancel();
        tokio::time::timeout(Duration::from_secs(1), runtime)
            .await
            .expect("runtime cancellation")
            .expect("runtime task")
            .expect("runtime result");
        herdr_task.abort();
        device_task.abort();
    }

    #[test]
    fn readiness_is_false_when_any_required_live_path_is_stalled() {
        assert_eq!(
            aggregate_runtime_state(
                BridgeStatus::Ready,
                BridgeStatus::Running,
                BridgeStatus::Ready,
            ),
            BridgeStatus::Ready
        );
        for states in [
            (
                BridgeStatus::DeviceUnavailable,
                BridgeStatus::Running,
                BridgeStatus::Ready,
            ),
            (
                BridgeStatus::Ready,
                BridgeStatus::HerdrUnavailable,
                BridgeStatus::Ready,
            ),
            (
                BridgeStatus::Ready,
                BridgeStatus::Running,
                BridgeStatus::Stale,
            ),
        ] {
            assert_eq!(
                aggregate_runtime_state(states.0, states.1, states.2),
                BridgeStatus::Stale
            );
        }
    }

    #[test]
    fn default_config_has_bounded_explicit_deadlines() {
        let config = CoordinatorConfig::default();
        assert!(config.validate().is_ok());
        assert!(config.reconnect_max <= DEFAULT_RECONNECT_MAX);
        assert!(config.snapshot_ack_timeout <= Duration::from_secs(120));

        let mut zero = config;
        zero.snapshot_ack_timeout = Duration::ZERO;
        assert!(zero.validate().is_err());

        let mut maximum = config;
        maximum.snapshot_ack_timeout = Duration::from_secs(120);
        assert!(maximum.validate().is_ok());

        let mut over_maximum = config;
        over_maximum.snapshot_ack_timeout = Duration::from_secs(121);
        assert!(over_maximum.validate().is_err());
    }

    #[test]
    fn unavailable_diagnostics_match_python_and_device_admission_sentinel() {
        assert_eq!(UNAVAILABLE_DIAGNOSTIC, "UNAVAL");
    }

    #[test]
    fn focus_payload_keeps_authorization_tied_to_accepted_and_focused() {
        let intent = ModelFocusIntent::new(
            "action",
            Binding {
                host_epoch: "epoch".into(),
                snapshot_revision: 4,
                slot: 0,
                entry_id: "pane-1".into(),
                identity: Identity {
                    pane_id: "pane-1".into(),
                    terminal_id: "terminal-1".into(),
                    agent_session: Some("herdr:omp:omp:path".into()),
                    source_revision: 7,
                    workspace_id: String::new(),
                    tab_id: String::new(),
                },
            },
        );

        let accepted: FocusResultPayload = serde_json::from_value(focus_payload(
            &intent,
            FocusStatus::Accepted,
            true,
        ))
        .expect("accepted focus payload");
        assert_eq!(accepted.outcome, FocusOutcome::Accepted);
        assert!(accepted.focused);

        let rejected: FocusResultPayload = serde_json::from_value(focus_payload(
            &intent,
            FocusStatus::SessionChanged,
            false,
        ))
        .expect("rejected focus payload");
        assert_eq!(rejected.outcome, FocusOutcome::Rejected);
        assert!(!rejected.focused);
    }
}
