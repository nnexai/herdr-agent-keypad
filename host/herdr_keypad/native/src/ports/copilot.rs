//! Bounded GitHub Copilot AI-credit account adapter.
//!
//! The collector deliberately uses the first-party SDK as the process and
//! protocol owner. Only the small, allow-listed account/quota projection leaves
//! this module; credentials, raw RPC responses, and arbitrary SDK errors do not.

use github_copilot_sdk::{CliProgram, Client, ClientOptions, Transport};
use serde::Serialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::future::Future;
use std::path::Path;
use std::pin::Pin;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

type BoxFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;
pub type CopilotFuture<'a, T> = BoxFuture<'a, T>;

pub const DEFAULT_DEADLINE: Duration = Duration::from_secs(15);
pub const FULL_POLL_INTERVAL: Duration = Duration::from_secs(300);
pub const STALE_AFTER: Duration = Duration::from_secs(900);
pub const EXPECTED_PROTOCOL_VERSION: u32 = 3;
pub const EXPECTED_CLI_VERSION: &str = "1.0.81";
pub const SDK_VERSION: &str = "1.0.13-preview.2";
pub const MAX_CREDITS: u64 = 1_000_000_000;
pub const MAX_TEXT_BYTES: usize = 64;
pub const MAX_ERROR_TEXT: usize = 32;

const ERROR_REASON_CODES: [&str; 11] = [
    "", "auth_required", "cli_missing", "cli_version_mismatch", "protocol_mismatch",
    "unsupported_host", "quota_unavailable", "billing_mode_unsupported", "malformed_quota",
    "timeout", "transport_unavailable",
];

/// Closed state for the normalized Copilot source.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CopilotSourceState {
    Current,
    Stale,
    AuthRequired,
    Unavailable,
}

impl CopilotSourceState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Stale => "stale",
            Self::AuthRequired => "auth_required",
            Self::Unavailable => "unavailable",
        }
    }
}

/// Closed reason vocabulary for a source that cannot provide current AIC.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CopilotFailureReason {
    None,
    AuthRequired,
    CliMissing,
    CliVersionMismatch,
    ProtocolMismatch,
    UnsupportedHost,
    QuotaUnavailable,
    BillingModeUnsupported,
    MalformedQuota,
    Timeout,
    TransportUnavailable,
}

impl CopilotFailureReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::None => "",
            Self::AuthRequired => "auth_required",
            Self::CliMissing => "cli_missing",
            Self::CliVersionMismatch => "cli_version_mismatch",
            Self::ProtocolMismatch => "protocol_mismatch",
            Self::UnsupportedHost => "unsupported_host",
            Self::QuotaUnavailable => "quota_unavailable",
            Self::BillingModeUnsupported => "billing_mode_unsupported",
            Self::MalformedQuota => "malformed_quota",
            Self::Timeout => "timeout",
            Self::TransportUnavailable => "transport_unavailable",
        }
    }

    fn state(self) -> CopilotSourceState {
        if self == Self::AuthRequired {
            CopilotSourceState::AuthRequired
        } else {
            CopilotSourceState::Unavailable
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CopilotTransportError {
    MissingExecutable,
    Timeout,
    Protocol,
    UnsupportedHost,
    AuthRequired,
    Closed,
    Failed,
}

/// A safe operation fact used by focused tests and redacted evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CopilotOperation {
    pub name: String,
    pub completed: bool,
}

/// A small SDK seam. Production wraps `github-copilot-sdk`; tests return raw
/// JSON fixtures while recording exactly which account operations were asked.
pub trait CopilotConnection: Send {
    fn connect<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>>;
    fn current_auth<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>>;
    fn quota<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>>;
    fn shutdown<'a>(&'a mut self) -> CopilotFuture<'a, Result<(), CopilotTransportError>>;
}

pub trait CopilotProcessFactory: Send + Sync {
    fn start<'a>(&'a self, executable: &'a str) -> CopilotFuture<'a, Result<Box<dyn CopilotConnection>, CopilotTransportError>>;
}

/// Compatibility name for callers that describe this as the transport seam.
pub use CopilotProcessFactory as CopilotTransport;

#[derive(Debug, Default, Clone, Copy)]
pub struct StdCopilotProcessFactory;

impl CopilotProcessFactory for StdCopilotProcessFactory {
    fn start<'a>(&'a self, executable: &'a str) -> CopilotFuture<'a, Result<Box<dyn CopilotConnection>, CopilotTransportError>> {
        let executable = executable.to_owned();
        Box::pin(async move {
            if executable.contains(std::path::MAIN_SEPARATOR) && !Path::new(&executable).is_file() {
                return Err(CopilotTransportError::MissingExecutable);
            }
            let mut options = ClientOptions::default();
            options.program = CliProgram::Path(executable.into());
            options.transport = Transport::Stdio;
            // Never replace the user's host or credentials. This only keeps
            // the CLI's normal stored-account path enabled when no token is set.
            options.use_logged_in_user = Some(true);
            let client = Client::start(options).await.map_err(map_sdk_error)?;
            Ok(Box::new(StdCopilotConnection { client }) as Box<dyn CopilotConnection>)
        })
    }
}

struct StdCopilotConnection {
    client: Client,
}

impl CopilotConnection for StdCopilotConnection {
    fn connect<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        Box::pin(async move {
            self.client
                .call("connect", Some(json!({})))
                .await
                .map_err(map_sdk_error)
        })
    }

    fn current_auth<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        Box::pin(async move {
            self.client
                .call("account.getCurrentAuth", Some(json!({})))
                .await
                .map_err(map_sdk_error)
        })
    }

    fn quota<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        Box::pin(async move {
            self.client
                .call("account.getQuota", Some(json!({})))
                .await
                .map_err(map_sdk_error)
        })
    }

    fn shutdown<'a>(&'a mut self) -> CopilotFuture<'a, Result<(), CopilotTransportError>> {
        Box::pin(async move { self.client.stop().await.map_err(|_| CopilotTransportError::Failed) })
    }
}

fn map_sdk_error(error: github_copilot_sdk::Error) -> CopilotTransportError {
    match error.rpc_code() {
        Some(-32601) => CopilotTransportError::Protocol,
        Some(401 | 403) => CopilotTransportError::AuthRequired,
        Some(404) => CopilotTransportError::UnsupportedHost,
        _ if error.is_transport_failure() => CopilotTransportError::Failed,
        _ => CopilotTransportError::Failed,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CopilotView {
    pub provider: String,
    pub source_state: CopilotSourceState,
    pub has_quota: Option<bool>,
    pub used_credits: Option<u64>,
    pub included_credits: Option<u64>,
    pub used_percent: Option<u8>,
    pub overage_used: Option<u64>,
    pub overage_limit: Option<u64>,
    pub overage_permitted: Option<bool>,
    pub usage_allowed_with_exhausted_quota: Option<bool>,
    pub overage_allowed_with_exhausted_quota: Option<bool>,
    pub reset_text: String,
    pub observation_age: String,
    pub unlimited: bool,
    pub reached_limit: Option<bool>,
    pub failure_reason: CopilotFailureReason,
}

impl Default for CopilotView {
    fn default() -> Self {
        Self {
            provider: "github_copilot".to_owned(),
            source_state: CopilotSourceState::Unavailable,
            has_quota: None,
            used_credits: None,
            included_credits: None,
            used_percent: None,
            overage_used: None,
            overage_limit: None,
            overage_permitted: None,
            usage_allowed_with_exhausted_quota: None,
            overage_allowed_with_exhausted_quota: None,
            reset_text: "RESET N/A".to_owned(),
            observation_age: "AGE N/A".to_owned(),
            unlimited: false,
            reached_limit: None,
            failure_reason: CopilotFailureReason::QuotaUnavailable,
        }
    }
}

impl CopilotView {
    pub fn as_payload(&self) -> Value {
        json!({
            "provider": self.provider,
            "source_state": self.source_state.as_str(),
            "has_quota": self.has_quota,
            "used_credits": self.used_credits,
            "included_credits": self.included_credits,
            "used_percent": self.used_percent,
            "overage_used": self.overage_used,
            "overage_limit": self.overage_limit,
            "overage_permitted": self.overage_permitted,
            "usage_allowed_with_exhausted_quota": self.usage_allowed_with_exhausted_quota,
            "overage_allowed_with_exhausted_quota": self.overage_allowed_with_exhausted_quota,
            "reset_text": self.reset_text.chars().take(MAX_TEXT_BYTES).collect::<String>(),
            "observation_age": self.observation_age.chars().take(16).collect::<String>(),
            "unlimited": self.unlimited,
            "reached_limit": self.reached_limit,
            "failure_reason": self.failure_reason.as_str(),
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CopilotResult {
    pub view: CopilotView,
    pub handshake: Vec<(String, String)>,
    pub operations: Vec<CopilotOperation>,
    pub deadline_ms: u64,
    pub elapsed_ms: u64,
    pub account_observed: bool,
    pub quota_observed: bool,
}

impl CopilotResult {
    pub fn as_evidence(&self) -> Value {
        json!({
            "view": self.view.as_payload(),
            "handshake": self.handshake,
            "operations": self.operations,
            "deadline_ms": self.deadline_ms,
            "elapsed_ms": self.elapsed_ms,
            "account_observed": self.account_observed,
            "quota_observed": self.quota_observed,
            "sdk_version": SDK_VERSION,
        })
    }
}

#[derive(Clone)]
pub struct CopilotCollector {
    executable: String,
    deadline: Duration,
    clock: Arc<dyn Fn() -> Duration + Send + Sync>,
    factory: Arc<dyn CopilotProcessFactory>,
    cache: Option<CopilotView>,
    last_observed_at: Option<Duration>,
    next_full_at: Option<Duration>,
    state: CopilotSourceState,
    failure_reason: CopilotFailureReason,
    account_marker: Option<[u8; 32]>,
    test_cli_missing: bool,
    pub last_result: Option<CopilotResult>,
}

impl std::fmt::Debug for CopilotCollector {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("CopilotCollector")
            .field("executable", &self.executable)
            .field("deadline", &self.deadline)
            .field("last_observed_at", &self.last_observed_at)
            .field("next_full_at", &self.next_full_at)
            .field("state", &self.state)
            .field("failure_reason", &self.failure_reason)
            .field("has_baseline", &self.cache.is_some())
            .finish()
    }
}

impl CopilotCollector {
    pub fn new() -> Self {
        Self::with_transport_and_clock(
            "copilot",
            DEFAULT_DEADLINE,
            Arc::new(StdCopilotProcessFactory),
            system_now,
        )
        .expect("default Copilot collector configuration is valid")
    }

    pub fn try_new(executable: impl Into<String>, deadline: Duration) -> Result<Self, &'static str> {
        Self::with_transport_and_clock(executable, deadline, Arc::new(StdCopilotProcessFactory), system_now)
    }

    pub fn with_transport(
        executable: impl Into<String>,
        deadline: Duration,
        factory: Arc<dyn CopilotProcessFactory>,
    ) -> Result<Self, &'static str> {
        Self::with_transport_and_clock(executable, deadline, factory, system_now)
    }

    pub fn with_transport_and_clock<C: Fn() -> Duration + Send + Sync + 'static>(
        executable: impl Into<String>,
        deadline: Duration,
        factory: Arc<dyn CopilotProcessFactory>,
        clock: C,
    ) -> Result<Self, &'static str> {
        if deadline.is_zero() || deadline > Duration::from_secs(120) {
            return Err("deadline is out of bounds");
        }
        Ok(Self {
            executable: executable.into(),
            deadline,
            clock: Arc::new(clock),
            factory,
            cache: None,
            last_observed_at: None,
            next_full_at: None,
            state: CopilotSourceState::Unavailable,
            failure_reason: CopilotFailureReason::QuotaUnavailable,
            account_marker: None,
            test_cli_missing: false,
            last_result: None,
        })
    }

    fn now(&self) -> Duration {
        (self.clock)()
    }

    pub fn deadline(&self) -> Duration {
        self.deadline
    }

    pub fn last_observed_at(&self) -> Option<Duration> {
        self.last_observed_at
    }

    pub fn should_poll(&self, now: Option<Duration>) -> bool {
        let now = now.unwrap_or_else(|| self.now());
        self.next_full_at.is_none_or(|deadline| now >= deadline)
    }

    pub fn view(&self) -> CopilotView {
        let mut view = self.cache.clone().unwrap_or_default();
        view.source_state = self.state;
        view.failure_reason = self.failure_reason;
        view.observation_age = observation_age(self.last_observed_at, self.now());
        if self.state == CopilotSourceState::Current
            && self
                .last_observed_at
                .is_some_and(|observed| self.now().saturating_sub(observed) >= STALE_AFTER)
        {
            view.source_state = CopilotSourceState::Stale;
        }
        view
    }

    pub fn account_changed(&mut self, auth_required: bool) {
        self.cache = None;
        self.account_marker = None;
        self.last_observed_at = None;
        self.next_full_at = None;
        self.state = if auth_required { CopilotSourceState::AuthRequired } else { CopilotSourceState::Unavailable };
        self.failure_reason = if auth_required { CopilotFailureReason::AuthRequired } else { CopilotFailureReason::QuotaUnavailable };
    }

    pub fn mark_refresh_failed(&mut self, reason: CopilotFailureReason) {
        self.failure_reason = reason;
        self.state = if self.cache.is_some() { CopilotSourceState::Stale } else { reason.state() };
    }

    pub async fn collect_async(&mut self) -> CopilotResult {
        let started = self.now();
        let deadline = started.saturating_add(self.deadline);
        let deadline_ms = self.deadline.as_millis().min(u128::from(u64::MAX)) as u64;
        let mut handshake = Vec::new();
        let mut operations = Vec::new();
        let mut account_observed = false;
        let mut quota_observed = false;
        let mut result_reason = CopilotFailureReason::None;

        let start_result = if self.test_cli_missing {
            Err(CopilotTransportError::MissingExecutable)
        } else {
            match tokio::time::timeout(remaining(deadline, self.now()), self.factory.start(&self.executable)).await {
                Ok(value) => value,
                Err(_) => Err(CopilotTransportError::Timeout),
            }
        };
        let mut connection = match start_result {
            Ok(value) => value,
            Err(error) => {
                result_reason = reason_for_transport(error, true);
                self.mark_refresh_failed(result_reason);
                return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
            }
        };

        operations.push(CopilotOperation { name: "connect".to_owned(), completed: false });
        let connect = match tokio::time::timeout(remaining(deadline, self.now()), connection.connect()).await {
            Ok(value) => value,
            Err(_) => Err(CopilotTransportError::Timeout),
        };
        let connect = match connect {
            Ok(value) => value,
            Err(error) => {
                result_reason = reason_for_transport(error, false);
                self.mark_refresh_failed(result_reason);
                let _ = shutdown_connection(&mut *connection, deadline, self.now()).await;
                operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: true });
                return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
            }
        };
        let Some(connect_object) = connect.as_object() else {
            result_reason = CopilotFailureReason::ProtocolMismatch;
            self.mark_refresh_failed(result_reason);
            let _ = shutdown_connection(&mut *connection, deadline, self.now()).await;
            operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: true });
            return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
        };
        if connect_object.get("ok").and_then(Value::as_bool) != Some(true) {
            result_reason = CopilotFailureReason::ProtocolMismatch;
        } else if connect_object.get("protocolVersion").and_then(parse_u32) != Some(EXPECTED_PROTOCOL_VERSION) {
            result_reason = CopilotFailureReason::ProtocolMismatch;
        } else if connect_object.get("version").and_then(Value::as_str) != Some(EXPECTED_CLI_VERSION) {
            result_reason = CopilotFailureReason::CliVersionMismatch;
        }
        if result_reason != CopilotFailureReason::None {
            self.mark_refresh_failed(result_reason);
            let _ = shutdown_connection(&mut *connection, deadline, self.now()).await;
            operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: true });
            return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
        }
        operations[0].completed = true;
        handshake.push(("protocol".to_owned(), EXPECTED_PROTOCOL_VERSION.to_string()));
        handshake.push(("cli".to_owned(), EXPECTED_CLI_VERSION.to_owned()));

        operations.push(CopilotOperation { name: "account.getCurrentAuth".to_owned(), completed: false });
        let auth = match tokio::time::timeout(remaining(deadline, self.now()), connection.current_auth()).await {
            Ok(value) => value,
            Err(_) => Err(CopilotTransportError::Timeout),
        };
        let auth = match auth {
            Ok(value) => value,
            Err(error) => {
                result_reason = reason_for_transport(error, false);
                self.mark_refresh_failed(result_reason);
                let _ = shutdown_connection(&mut *connection, deadline, self.now()).await;
                operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: true });
                return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
            }
        };
        let marker = match auth_marker(&auth) {
            Ok(value) => value,
            Err(reason) => {
                self.mark_refresh_failed(reason);
                let _ = shutdown_connection(&mut *connection, deadline, self.now()).await;
                operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: true });
                return self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed);
            }
        };
        account_observed = true;
        operations[1].completed = true;
        if self.account_marker.is_some_and(|prior| prior != marker) {
            self.account_changed(false);
        }
        self.account_marker = Some(marker);

        operations.push(CopilotOperation { name: "account.getQuota".to_owned(), completed: false });
        let quota = match tokio::time::timeout(remaining(deadline, self.now()), connection.quota()).await {
            Ok(value) => value,
            Err(_) => Err(CopilotTransportError::Timeout),
        };
        match quota {
            Ok(value) => {
                quota_observed = true;
                match normalize_quota(&value) {
                    Ok(mut normalized) => {
                        normalized.source_state = CopilotSourceState::Current;
                        normalized.failure_reason = CopilotFailureReason::None;
                        normalized.observation_age = "AGE 0M".to_owned();
                        self.cache = Some(normalized);
                        self.last_observed_at = Some(self.now());
                        self.next_full_at = Some(self.now().saturating_add(FULL_POLL_INTERVAL));
                        self.state = CopilotSourceState::Current;
                        self.failure_reason = CopilotFailureReason::None;
                    }
                    Err(reason) => {
                        result_reason = reason;
                        self.mark_refresh_failed(reason);
                    }
                }
            }
            Err(error) => {
                result_reason = reason_for_transport(error, false);
                self.mark_refresh_failed(result_reason);
            }
        }
        operations[2].completed = true;
        let shutdown_ok = shutdown_connection(&mut *connection, deadline, self.now()).await;
        operations.push(CopilotOperation { name: "shutdown".to_owned(), completed: shutdown_ok });
        if result_reason != CopilotFailureReason::None && self.cache.is_none() {
            self.mark_refresh_failed(result_reason);
        }
        self.finish_result(started, deadline_ms, handshake, operations, account_observed, quota_observed)
    }

    fn finish_result(
        &mut self,
        started: Duration,
        deadline_ms: u64,
        handshake: Vec<(String, String)>,
        operations: Vec<CopilotOperation>,
        account_observed: bool,
        quota_observed: bool,
    ) -> CopilotResult {
        let elapsed_ms = self.now().saturating_sub(started).as_millis().min(u128::from(deadline_ms)) as u64;
        let result = CopilotResult {
            view: self.view(),
            handshake,
            operations,
            deadline_ms,
            elapsed_ms,
            account_observed,
            quota_observed,
        };
        self.last_result = Some(result.clone());
        result
    }

    // Test-only helpers keep fixture setup independent from production I/O.
    #[cfg(test)]
    pub fn set_test_cli_missing(&mut self) {
        self.test_cli_missing = true;
    }

    #[cfg(test)]
    pub fn set_test_baseline(&mut self, auth: Value, quota: Value) {
        if let Ok(marker) = auth_marker(&auth) {
            if let Ok(mut view) = normalize_quota(&quota) {
                view.source_state = CopilotSourceState::Current;
                view.failure_reason = CopilotFailureReason::None;
                view.observation_age = "AGE 0M".to_owned();
                self.account_marker = Some(marker);
                self.cache = Some(view);
                self.state = CopilotSourceState::Current;
                self.failure_reason = CopilotFailureReason::None;
                self.last_observed_at = Some(self.now());
            }
        }
    }
}

async fn shutdown_connection(connection: &mut dyn CopilotConnection, deadline: Duration, now: Duration) -> bool {
    tokio::time::timeout(remaining(deadline, now), connection.shutdown()).await.is_ok_and(|value| value.is_ok())
}

fn reason_for_transport(error: CopilotTransportError, starting: bool) -> CopilotFailureReason {
    match error {
        CopilotTransportError::MissingExecutable => CopilotFailureReason::CliMissing,
        CopilotTransportError::Timeout => CopilotFailureReason::Timeout,
        CopilotTransportError::Protocol => CopilotFailureReason::ProtocolMismatch,
        CopilotTransportError::UnsupportedHost => CopilotFailureReason::UnsupportedHost,
        CopilotTransportError::AuthRequired => CopilotFailureReason::AuthRequired,
        CopilotTransportError::Closed | CopilotTransportError::Failed => {
            if starting { CopilotFailureReason::CliMissing } else { CopilotFailureReason::TransportUnavailable }
        }
    }
}

fn system_now() -> Duration {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default()
}

fn remaining(deadline: Duration, now: Duration) -> Duration {
    deadline.saturating_sub(now).max(Duration::from_millis(1))
}

fn observation_age(observed: Option<Duration>, now: Duration) -> String {
    observed.map_or_else(|| "AGE N/A".to_owned(), |value| format!("AGE {}M", now.saturating_sub(value).as_secs() / 60))
}

fn parse_u32(value: &Value) -> Option<u32> {
    value.as_u64().and_then(|value| u32::try_from(value).ok())
}

fn parse_count(value: Option<&Value>, allow_unlimited: bool) -> Result<Option<u64>, CopilotFailureReason> {
    let value = value.ok_or(CopilotFailureReason::MalformedQuota)?;
    if allow_unlimited && value.as_i64() == Some(-1) {
        return Ok(None);
    }
    let value = value.as_f64().ok_or(CopilotFailureReason::MalformedQuota)?;
    if !value.is_finite() || value < 0.0 || value.fract() != 0.0 || value > MAX_CREDITS as f64 {
        return Err(CopilotFailureReason::MalformedQuota);
    }
    Ok(Some(value as u64))
}

fn parse_bool(value: Option<&Value>) -> Result<bool, CopilotFailureReason> {
    value.and_then(Value::as_bool).ok_or(CopilotFailureReason::MalformedQuota)
}

fn parse_percent(value: Option<&Value>) -> Result<u8, CopilotFailureReason> {
    let value = value.and_then(Value::as_f64).ok_or(CopilotFailureReason::MalformedQuota)?;
    if !value.is_finite() || !(0.0..=100.0).contains(&value) || value.fract() != 0.0 {
        return Err(CopilotFailureReason::MalformedQuota);
    }
    Ok(value as u8)
}

fn parse_reset(value: Option<&Value>) -> Result<String, CopilotFailureReason> {
    let Some(value) = value else { return Ok("RESET N/A".to_owned()) };
    if value.is_null() {
        return Ok("RESET N/A".to_owned());
    }
    let value = value.as_str().ok_or(CopilotFailureReason::MalformedQuota)?;
    if value.is_empty() || value.len() > MAX_TEXT_BYTES || !value.is_ascii() || value.bytes().any(|byte| byte < 0x20 || byte == 0x7f) {
        return Err(CopilotFailureReason::MalformedQuota);
    }
    Ok(format!("RESET {value}"))
}

fn normalize_quota(response: &Value) -> Result<CopilotView, CopilotFailureReason> {
    let snapshots = response
        .get("quotaSnapshots")
        .and_then(Value::as_object)
        .ok_or(CopilotFailureReason::QuotaUnavailable)?;
    let snapshot = snapshots
        .get("premium_interactions")
        .and_then(Value::as_object)
        .ok_or(CopilotFailureReason::QuotaUnavailable)?;
    match snapshot.get("tokenBasedBilling").and_then(Value::as_bool) {
        Some(true) => {}
        Some(false) | None => return Err(CopilotFailureReason::BillingModeUnsupported),
    }
    let has_quota = parse_bool(snapshot.get("hasQuota"))?;
    let is_unlimited = parse_bool(snapshot.get("isUnlimitedEntitlement"))?;
    let entitlement = parse_count(snapshot.get("entitlementRequests"), true)?;
    let used = parse_count(snapshot.get("usedRequests"), false)?;
    let overage_used = parse_count(snapshot.get("overage"), false)?;
    let overage_limit = parse_count(snapshot.get("overageEntitlement"), false)?;
    let remaining_percent = parse_percent(snapshot.get("remainingPercentage"))?;
    let reset_text = parse_reset(snapshot.get("resetDate"))?;
    let usage_allowed = parse_bool(snapshot.get("usageAllowedWithExhaustedQuota"))?;
    let overage_allowed = parse_bool(snapshot.get("overageAllowedWithExhaustedQuota"))?;
    let unlimited = is_unlimited || entitlement.is_none();
    let included_credits = if unlimited { None } else { entitlement };
    let used_percent = if unlimited { None } else { Some(100_u8.saturating_sub(remaining_percent)) };
    let reached_limit = if unlimited { None } else { Some(!has_quota) };
    Ok(CopilotView {
        provider: "github_copilot".to_owned(),
        source_state: CopilotSourceState::Current,
        has_quota: Some(has_quota),
        used_credits: used,
        included_credits,
        used_percent,
        overage_used,
        overage_limit,
        overage_permitted: Some(overage_allowed),
        usage_allowed_with_exhausted_quota: Some(usage_allowed),
        overage_allowed_with_exhausted_quota: Some(overage_allowed),
        reset_text,
        observation_age: "AGE N/A".to_owned(),
        unlimited,
        reached_limit,
        failure_reason: CopilotFailureReason::None,
    })
}

fn auth_marker(value: &Value) -> Result<[u8; 32], CopilotFailureReason> {
    let object = value.as_object().ok_or(CopilotFailureReason::AuthRequired)?;
    if object.get("authErrors").and_then(Value::as_array).is_some_and(|errors| !errors.is_empty()) {
        return Err(CopilotFailureReason::AuthRequired);
    }
    let auth = object
        .get("authInfo")
        .or_else(|| object.get("auth_info"))
        .and_then(Value::as_object)
        .ok_or(CopilotFailureReason::AuthRequired)?;
    let host = auth.get("host").and_then(Value::as_str).ok_or(CopilotFailureReason::AuthRequired)?;
    if host.is_empty() || host.len() > MAX_TEXT_BYTES || !host.is_ascii() {
        return Err(CopilotFailureReason::AuthRequired);
    }
    let login = auth
        .get("login")
        .and_then(Value::as_str)
        .or_else(|| auth.get("copilotUser").and_then(Value::as_object).and_then(|user| user.get("login")).and_then(Value::as_str))
        .ok_or(CopilotFailureReason::AuthRequired)?;
    if login.is_empty() || login.len() > MAX_TEXT_BYTES || !login.is_ascii() {
        return Err(CopilotFailureReason::AuthRequired);
    }
    let kind = auth.get("type").and_then(Value::as_str).unwrap_or("user");
    if kind.len() > MAX_ERROR_TEXT || !kind.is_ascii() {
        return Err(CopilotFailureReason::AuthRequired);
    }
    let mut hasher = Sha256::new();
    hasher.update(host.as_bytes());
    hasher.update([0]);
    hasher.update(login.as_bytes());
    hasher.update([0]);
    hasher.update(kind.as_bytes());
    Ok(hasher.finalize().into())
}

/// Return false for any evidence-shaped key that could carry credentials or
/// raw upstream data. This is intentionally shared by collector tests only;
/// production status serialization is closed by `StatusSnapshot` validation.
pub fn redaction_passes(value: &Value) -> bool {
    const FORBIDDEN: [&str; 14] = [
        "token", "secret", "password", "email", "login", "auth", "host", "path", "prompt", "transcript", "stderr", "stdout", "response", "raw",
    ];
    match value {
        Value::Object(object) => object.iter().all(|(key, item)| {
            !FORBIDDEN.iter().any(|word| key.to_ascii_lowercase().contains(word)) && redaction_passes(item)
        }),
        Value::Array(items) => items.iter().all(redaction_passes),
        _ => true,
    }
}

/// Expose strict normalization for focused compatibility tests without
/// exposing the raw response through any collector state.
pub fn normalize_current_aic(response: &Value) -> Result<CopilotView, CopilotFailureReason> {
    normalize_quota(response)
}

#[allow(dead_code)]
fn _bounded_error_reason(reason: CopilotFailureReason) -> &'static str {
    let value = reason.as_str();
    if ERROR_REASON_CODES.contains(&value) { value } else { "transport_unavailable" }
}

#[allow(dead_code)]
fn _object_len(value: &Map<String, Value>) -> usize {
    value.len()
}
