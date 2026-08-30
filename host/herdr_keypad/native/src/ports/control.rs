//! One-authority, same-user local control protocol.
//!
//! A lock file is the authority.  Socket and PID artifacts are merely
//! disposable transport details and are never used to decide whether a bridge
//! is running.  Every frame is admitted against the fixed 16 KiB cap before
//! JSON deserialization.

use super::status::StatusSnapshot;
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};

pub const CONTROL_PROTOCOL_VERSION: u8 = 1;
pub const CONTROL_PAYLOAD_LIMIT: usize = 16 * 1024;
pub const CONTROL_SOCKET_NAME: &str = "bridge.sock";
pub const CONTROL_LOCK_NAME: &str = "bridge.lock";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ControlError {
    code: ControlErrorCode,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ControlErrorCode {
    AlreadyOwned,
    InvalidPayload,
    OversizedPayload,
    WrongVersion,
    UnauthorizedPeer,
    BindFailed,
    Io,
}

impl ControlError {
    fn new(code: ControlErrorCode) -> Self {
        Self { code }
    }

    pub fn code(&self) -> ControlErrorCode {
        self.code
    }

    pub fn safe_code(&self) -> &'static str {
        match self.code {
            ControlErrorCode::AlreadyOwned => "already_owned",
            ControlErrorCode::InvalidPayload => "invalid_payload",
            ControlErrorCode::OversizedPayload => "oversized_payload",
            ControlErrorCode::WrongVersion => "wrong_version",
            ControlErrorCode::UnauthorizedPeer => "unauthorized_peer",
            ControlErrorCode::BindFailed => "bind_failed",
            ControlErrorCode::Io => "io",
        }
    }
}

impl From<io::Error> for ControlError {
    fn from(_: io::Error) -> Self {
        Self::new(ControlErrorCode::Io)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "request", deny_unknown_fields)]
pub enum ControlRequest {
    #[serde(rename = "start")]
    Start { version: u8, config_identity: String },
    #[serde(rename = "stop")]
    Stop { version: u8 },
    #[serde(rename = "restart")]
    Restart { version: u8, config_identity: String },
    #[serde(rename = "status")]
    Status { version: u8 },
    #[serde(rename = "repair")]
    Repair { version: u8 },
    #[serde(rename = "repair_pair")]
    RepairPair { version: u8 },
}

impl ControlRequest {
    pub fn start(config_identity: impl Into<String>) -> Self {
        Self::Start {
            version: CONTROL_PROTOCOL_VERSION,
            config_identity: config_identity.into(),
        }
    }

    pub fn stop() -> Self {
        Self::Stop { version: CONTROL_PROTOCOL_VERSION }
    }

    pub fn restart(config_identity: impl Into<String>) -> Self {
        Self::Restart {
            version: CONTROL_PROTOCOL_VERSION,
            config_identity: config_identity.into(),
        }
    }

    pub fn status() -> Self {
        Self::Status { version: CONTROL_PROTOCOL_VERSION }
    }

    pub fn repair() -> Self {
        Self::Repair { version: CONTROL_PROTOCOL_VERSION }
    }

    pub fn repair_pair() -> Self {
        Self::RepairPair { version: CONTROL_PROTOCOL_VERSION }
    }

    pub fn version(&self) -> u8 {
        match self {
            Self::Start { version, .. }
            | Self::Stop { version }
            | Self::Restart { version, .. }
            | Self::Status { version }
            | Self::Repair { version }
            | Self::RepairPair { version } => *version,
        }
    }

    pub fn config_identity(&self) -> Option<&str> {
        match self {
            Self::Start { config_identity, .. } | Self::Restart { config_identity, .. } => {
                Some(config_identity)
            }
            _ => None,
        }
    }

    pub fn encode(&self) -> Result<Vec<u8>, ControlError> {
        validate_request(self)?;
        let mut bytes = serde_json::to_vec(self).map_err(|_| ControlError::new(ControlErrorCode::InvalidPayload))?;
        bytes.push(b'\n');
        if bytes.len() > CONTROL_PAYLOAD_LIMIT {
            return Err(ControlError::new(ControlErrorCode::OversizedPayload));
        }
        Ok(bytes)
    }

    pub fn decode(bytes: &[u8]) -> Result<Self, ControlError> {
        if bytes.len() > CONTROL_PAYLOAD_LIMIT {
            return Err(ControlError::new(ControlErrorCode::OversizedPayload));
        }
        let request: Self = serde_json::from_slice(bytes)
            .map_err(|_| ControlError::new(ControlErrorCode::InvalidPayload))?;
        validate_request(&request)?;
        Ok(request)
    }
}

fn validate_request(request: &ControlRequest) -> Result<(), ControlError> {
    if request.version() != CONTROL_PROTOCOL_VERSION {
        return Err(ControlError::new(ControlErrorCode::WrongVersion));
    }
    if let Some(identity) = request.config_identity() {
        if identity.is_empty()
            || identity.len() > 25
            || !identity
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() || matches!(byte, b'_' | b'-'))
        {
            return Err(ControlError::new(ControlErrorCode::InvalidPayload));
        }
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "reply", deny_unknown_fields)]
pub enum ControlReply {
    #[serde(rename = "active")]
    Active { version: String, config_identity: String },
    #[serde(rename = "restart_required")]
    RestartRequired { active_config_identity: String, requested_config_identity: String },
    #[serde(rename = "stopped")]
    Stopped,
    #[serde(rename = "restarted")]
    Restarted { version: String, config_identity: String },
    #[serde(rename = "status")]
    Status(StatusSnapshot),
    #[serde(rename = "accepted")]
    Accepted,
    #[serde(rename = "rejected")]
    Rejected { code: String },
}

impl ControlReply {
    pub fn active(version: impl Into<String>, config_identity: impl Into<String>) -> Self {
        Self::Active { version: version.into(), config_identity: config_identity.into() }
    }

    pub fn encode(&self) -> Result<Vec<u8>, ControlError> {
        let mut bytes = serde_json::to_vec(self).map_err(|_| ControlError::new(ControlErrorCode::InvalidPayload))?;
        if bytes.len() > CONTROL_PAYLOAD_LIMIT {
            return Err(ControlError::new(ControlErrorCode::OversizedPayload));
        }
        bytes.push(b'\n');
        Ok(bytes)
    }

    pub fn decode(bytes: &[u8]) -> Result<Self, ControlError> {
        if bytes.len() > CONTROL_PAYLOAD_LIMIT {
            return Err(ControlError::new(ControlErrorCode::OversizedPayload));
        }
        serde_json::from_slice(bytes).map_err(|_| ControlError::new(ControlErrorCode::InvalidPayload))
    }

    pub fn state(&self) -> super::status::BridgeStatus {
        match self {
            Self::Stopped => super::status::BridgeStatus::Stopped,
            Self::Status(snapshot) => snapshot.state,
            Self::Active { .. } | Self::Restarted { .. } => super::status::BridgeStatus::Running,
            Self::RestartRequired { .. } | Self::Accepted | Self::Rejected { .. } => {
                super::status::BridgeStatus::Unavailable
            }
        }
    }

    pub fn status(&self) -> Option<&StatusSnapshot> {
        match self {
            Self::Status(snapshot) => Some(snapshot),
            _ => None,
        }
    }
}

/// The lock is held for the lifetime of the owner.  Its path is intentionally
/// stable, but the file itself carries no PID or authority metadata.
pub struct AuthorityLock {
    file: File,
    state_dir: PathBuf,
    socket_path: PathBuf,
}

impl AuthorityLock {
    pub fn acquire(state_dir: &Path) -> Result<Self, ControlError> {
        fs::create_dir_all(state_dir).map_err(|_| ControlError::new(ControlErrorCode::Io))?;
        set_private_dir(state_dir)?;
        let lock_path = state_dir.join(CONTROL_LOCK_NAME);
        let file = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(&lock_path)
            .map_err(|_| ControlError::new(ControlErrorCode::Io))?;
        set_private_file(&lock_path)?;
        file.try_lock_exclusive()
            .map_err(|_| ControlError::new(ControlErrorCode::AlreadyOwned))?;
        // Only after owning the lock may a stale endpoint be removed.
        let socket_path = state_dir.join(CONTROL_SOCKET_NAME);
        remove_stale_endpoint(&socket_path)?;
        Ok(Self { file, state_dir: state_dir.to_path_buf(), socket_path })
    }

    pub fn state_dir(&self) -> &Path {
        &self.state_dir
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }

    pub async fn bind_control(&self) -> Result<ControlEndpoint, ControlError> {
        remove_stale_endpoint(&self.socket_path)?;
        let listener = UnixListener::bind(&self.socket_path)
            .map_err(|_| ControlError::new(ControlErrorCode::BindFailed))?;
        set_private_file(&self.socket_path)?;
        Ok(ControlEndpoint { listener, path: self.socket_path.clone(), state_dir: self.state_dir.clone() })
    }
}

impl Drop for AuthorityLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
        let _ = remove_stale_endpoint(&self.socket_path);
    }
}

pub struct ControlEndpoint {
    listener: UnixListener,
    path: PathBuf,
    state_dir: PathBuf,
}

impl ControlEndpoint {
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Accept one connection only when its kernel credential belongs to the
    /// owner of the private state directory.  A rejected peer is closed.
    pub async fn accept_same_user(&self) -> Result<UnixStream, ControlError> {
        let (stream, _) = self.listener.accept().await.map_err(ControlError::from)?;
        if peer_is_same_user(&stream, &self.state_dir) {
            Ok(stream)
        } else {
            Err(ControlError::new(ControlErrorCode::UnauthorizedPeer))
        }
    }

    pub async fn receive_request(&self, stream: UnixStream) -> Result<ControlRequest, ControlError> {
        if !peer_is_same_user(&stream, &self.state_dir) {
            return Err(ControlError::new(ControlErrorCode::UnauthorizedPeer));
        }
        let mut reader = BufReader::new(stream);
        let mut line = Vec::new();
        reader
            .read_until(b'\n', &mut line)
            .await
            .map_err(ControlError::from)?;
        ControlRequest::decode(&line)
    }

    pub async fn send_reply(stream: &mut UnixStream, reply: &ControlReply) -> Result<(), ControlError> {
        let bytes = reply.encode()?;
        stream.write_all(&bytes).await.map_err(ControlError::from)
    }
}

fn remove_stale_endpoint(path: &Path) -> Result<(), ControlError> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(ControlError::new(ControlErrorCode::Io)),
    }
}

#[cfg(unix)]
fn set_private_dir(path: &Path) -> Result<(), ControlError> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
        .map_err(|_| ControlError::new(ControlErrorCode::Io))
}

#[cfg(not(unix))]
fn set_private_dir(_: &Path) -> Result<(), ControlError> {
    Ok(())
}

#[cfg(unix)]
fn set_private_file(path: &Path) -> Result<(), ControlError> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
        .map_err(|_| ControlError::new(ControlErrorCode::Io))
}

#[cfg(not(unix))]
fn set_private_file(_: &Path) -> Result<(), ControlError> {
    Ok(())
}

#[cfg(unix)]
fn peer_is_same_user(stream: &UnixStream, state_dir: &Path) -> bool {
    use std::os::unix::fs::MetadataExt;
    stream
        .peer_cred()
        .ok()
        .zip(fs::metadata(state_dir).ok())
        .map(|(peer, owner)| peer.uid() == owner.uid())
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn peer_is_same_user(_: &UnixStream, _: &Path) -> bool {
    false
}
