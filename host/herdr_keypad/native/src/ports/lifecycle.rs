//! Herdr v0.8.2 one-shot lifecycle and explicit recovery.
//!
//! This owner has no watchdog, detached child, service, or live configuration
//! watcher. Herdr starts the process and the process ends when its Herdr
//! boundary ends. Explicit control actions are the only recovery path.

use super::config::{EffectiveConfig, StartupConfig};
use super::control::{
    AuthorityLock, ControlEndpoint, ControlError, ControlErrorCode, ControlReply, ControlRequest,
};
use super::status::{BridgeStatus, SafeCode, StatusSnapshot, TransitionRing};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimePaths {
    pub config_dir: PathBuf,
    pub state_dir: PathBuf,
    pub herdr_socket: PathBuf,
    pub herdr_binary: PathBuf,
    pub herdr_pid: u32,
}

impl RuntimePaths {
    pub fn new(
        config_dir: impl Into<PathBuf>,
        state_dir: impl Into<PathBuf>,
        herdr_socket: impl Into<PathBuf>,
        herdr_binary: impl Into<PathBuf>,
        herdr_pid: u32,
    ) -> Self {
        Self {
            config_dir: config_dir.into(),
            state_dir: state_dir.into(),
            herdr_socket: herdr_socket.into(),
            herdr_binary: herdr_binary.into(),
            herdr_pid,
        }
    }

    pub fn state_dir(&self) -> &Path {
        &self.state_dir
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecycleCommand {
    Start,
    Stop,
    Restart,
    Status,
    Repair,
    RepairPair,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResourceMetrics {
    pub wakes: u64,
    pub source_polls: u64,
    pub timer_fires: u64,
    pub queue_high_water: usize,
    pub history_size: usize,
    pub max_payload: usize,
}

impl ResourceMetrics {
    pub const fn idle() -> Self {
        Self {
            wakes: 0,
            source_polls: 0,
            timer_fires: 0,
            queue_high_water: 0,
            history_size: 0,
            max_payload: 0,
        }
    }
}

pub type LifecycleError = ControlError;

/// Owns exactly one lock and therefore exactly one control authority.
pub struct LifecycleOwner {
    paths: RuntimePaths,
    lock: Option<AuthorityLock>,
    effective: EffectiveConfig,
    pending_config: Option<EffectiveConfig>,
    active: bool,
    herdr_alive: bool,
    sessions_valid: bool,
    session_epoch: u64,
    startup_available: bool,
    transitions: TransitionRing,
    metrics: ResourceMetrics,
}

impl LifecycleOwner {
    pub fn new(paths: RuntimePaths, effective: EffectiveConfig) -> Result<Self, LifecycleError> {
        let lock = AuthorityLock::acquire(paths.state_dir())?;
        Ok(Self {
            paths,
            lock: Some(lock),
            effective,
            pending_config: None,
            active: false,
            herdr_alive: true,
            sessions_valid: false,
            session_epoch: 1,
            startup_available: true,
            transitions: TransitionRing::default(),
            metrics: ResourceMetrics::idle(),
        })
    }

    pub fn from_startup(paths: RuntimePaths, startup: StartupConfig) -> Result<Self, LifecycleError> {
        let available = startup.available();
        let effective = startup.effective;
        let mut owner = Self::new(paths, effective)?;
        owner.startup_available = available;
        if let Some(issue) = startup.issue {
            let code = if issue.safe_code().starts_with("binding") {
                SafeCode::BindingInvalid
            } else {
                SafeCode::ConfigInvalid
            };
            owner.transitions.push(code, 0);
        }
        Ok(owner)
    }

    pub async fn bind_control(&self) -> Result<ControlEndpoint, LifecycleError> {
        let authority = self
            .lock
            .as_ref()
            .ok_or_else(|| ControlError::new(ControlErrorCode::BindFailed))?;
        authority.bind_control().await
    }

    pub fn handle_control(&mut self, request: ControlRequest) -> ControlReply {
        match request {
            ControlRequest::Start { config_identity, .. } => {
                if config_identity == self.effective.identity() {
                    self.handle(LifecycleCommand::Start)
                } else {
                    ControlReply::RestartRequired {
                        active_config_identity: self.effective.identity().to_owned(),
                        requested_config_identity: config_identity,
                    }
                }
            }
            ControlRequest::Restart { config_identity, .. } => {
                if config_identity == self.effective.identity() {
                    self.handle(LifecycleCommand::Restart)
                } else {
                    ControlReply::RestartRequired {
                        active_config_identity: self.effective.identity().to_owned(),
                        requested_config_identity: config_identity,
                    }
                }
            }
            ControlRequest::Stop { .. } => self.handle(LifecycleCommand::Stop),
            ControlRequest::Status { .. } => self.handle(LifecycleCommand::Status),
            ControlRequest::Repair { .. } => self.handle(LifecycleCommand::Repair),
            ControlRequest::RepairPair { .. } => self.handle(LifecycleCommand::RepairPair),
        }
    }

    pub fn handle(&mut self, command: LifecycleCommand) -> ControlReply {
        match command {
            LifecycleCommand::Start => self.start_with_config(self.effective.clone()),
            LifecycleCommand::Stop => {
                self.stop();
                ControlReply::Stopped
            }
            LifecycleCommand::Restart => self.restart_with_pending(),
            LifecycleCommand::Status => ControlReply::Status(self.status()),
            // Repair and re-pair remain explicit commands rather than status
            // side effects. Their actual pairing operation is owned by Plan 07.
            LifecycleCommand::Repair | LifecycleCommand::RepairPair => ControlReply::Accepted,
        }
    }

    pub fn start_with_config(&mut self, requested: EffectiveConfig) -> ControlReply {
        if requested.identity() != self.effective.identity() && self.active {
            self.pending_config = Some(requested.clone());
            self.transitions.push(SafeCode::RestartRequired, 0);
            return ControlReply::RestartRequired {
                active_config_identity: self.effective.identity().to_owned(),
                requested_config_identity: requested.identity().to_owned(),
            };
        }
        if requested.identity() != self.effective.identity() {
            self.effective = requested;
        }
        if self.ensure_authority().is_err() {
            return ControlReply::Rejected { code: "authority_unavailable".to_owned() };
        }
        if !self.startup_available {
            return ControlReply::Rejected { code: "config_unavailable".to_owned() };
        }
        self.active = true;
        self.sessions_valid = self.herdr_alive;
        self.transitions.push(SafeCode::BridgeStarted, 0);
        ControlReply::active(env!("CARGO_PKG_VERSION"), self.effective.identity())
    }

    pub fn restart_with_config(&mut self, requested: EffectiveConfig) -> ControlReply {
        self.pending_config = Some(requested);
        self.restart_with_pending()
    }

    fn restart_with_pending(&mut self) -> ControlReply {
        if let Some(config) = self.pending_config.take() {
            self.effective = config;
        }
        if self.ensure_authority().is_err() {
            return ControlReply::Rejected { code: "authority_unavailable".to_owned() };
        }
        self.active = true;
        self.herdr_alive = true;
        self.sessions_valid = true;
        self.session_epoch = self.session_epoch.saturating_add(1);
        self.transitions.push(SafeCode::BridgeRestarted, 0);
        ControlReply::Restarted {
            version: env!("CARGO_PKG_VERSION").to_owned(),
            config_identity: self.effective.identity().to_owned(),
        }
    }

    fn ensure_authority(&mut self) -> Result<(), LifecycleError> {
        if self.lock.is_none() {
            self.lock = Some(AuthorityLock::acquire(self.paths.state_dir())?);
        }
        Ok(())
    }

    fn stop(&mut self) {
        self.active = false;
        self.sessions_valid = false;
        self.transitions.push(SafeCode::BridgeStopped, 0);
        // Stop is a process-boundary action. Dropping the lock means another
        // explicit Herdr start can acquire authority immediately.
        self.lock.take();
    }

    pub fn on_herdr_exit(&mut self) {
        self.active = false;
        self.herdr_alive = false;
        self.sessions_valid = false;
        self.transitions.push(SafeCode::AuthorityEnded, 0);
        self.lock.take();
    }

    pub fn on_process_crash(&mut self) {
        self.active = false;
        self.sessions_valid = false;
        self.transitions.push(SafeCode::BridgeStopped, 0);
        self.lock.take();
    }

    pub fn on_suspend(&mut self) {
        if self.active {
            self.sessions_valid = false;
            self.session_epoch = self.session_epoch.saturating_add(1);
            self.transitions.push(SafeCode::Suspend, 0);
        }
    }

    pub fn on_resume(&mut self) {
        if self.active {
            self.herdr_alive = true;
            self.sessions_valid = true;
            self.session_epoch = self.session_epoch.saturating_add(1);
            self.transitions.push(SafeCode::Resume, 0);
        }
    }

    pub fn status(&self) -> StatusSnapshot {
        let mut snapshot = StatusSnapshot::stopped(self.effective.identity());
        if self.active {
            snapshot.state = if self.sessions_valid {
                BridgeStatus::Running
            } else {
                BridgeStatus::Stale
            };
            snapshot.device_state = if self.sessions_valid {
                BridgeStatus::Ready
            } else {
                BridgeStatus::DeviceUnavailable
            };
            snapshot.herdr_state = if self.herdr_alive {
                BridgeStatus::Running
            } else {
                BridgeStatus::HerdrUnavailable
            };
            snapshot.codex_state = BridgeStatus::Unavailable;
            snapshot.reconnect_attempt = if self.sessions_valid { 0 } else { 1 };
            snapshot.backoff_ms = if self.sessions_valid { 0 } else { self.effective.reconnect_initial_ms };
        }
        snapshot.last_error = self.transitions.as_slice().last().and_then(|event| {
            match event.code {
                SafeCode::ConfigInvalid
                | SafeCode::BindingInvalid
                | SafeCode::HerdrUnavailable
                | SafeCode::DeviceUnavailable
                | SafeCode::CodexUnavailable
                | SafeCode::ControlRejected
                | SafeCode::UnauthorizedPeer
                | SafeCode::PayloadRejected
                | SafeCode::CapacityReached => Some(event.code),
                _ => None,
            }
        });
        snapshot.transitions = self.transitions.as_slice();
        snapshot
    }

    pub fn effective_config(&self) -> &EffectiveConfig {
        &self.effective
    }

    pub fn session_epoch(&self) -> u64 {
        self.session_epoch
    }

    pub fn sessions_valid(&self) -> bool {
        self.active && self.herdr_alive && self.sessions_valid
    }

    pub const fn automatic_recovery(&self) -> bool {
        false
    }

    pub fn requested_identity_for_test(&self, logging_enabled: bool) -> String {
        let config = self.effective.clone();
        EffectiveConfig::from_toml(&format!(
            "logging_enabled = {logging_enabled}\nreconnect_initial_ms = {}\nreconnect_max_ms = {}\n",
            config.reconnect_initial_ms, config.reconnect_max_ms
        ))
        .map(|value| value.identity().to_owned())
        .unwrap_or_else(|_| self.effective.identity().to_owned())
    }

    pub fn resource_metrics(&self) -> ResourceMetrics {
        self.metrics
    }
}
