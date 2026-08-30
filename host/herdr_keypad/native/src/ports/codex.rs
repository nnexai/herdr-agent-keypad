//! Bounded Codex app-server adapter.
//!
//! This module is the only place that consumes Codex JSONL. Responses are
//! normalized into a small presence-aware view before crossing the source
//! boundary; account data, raw errors, and child output never leave this file.

use herdr_keypad_native::CodexSnapshot;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const MAX_LINE_BYTES: usize = 4_096;
pub const MAX_BUCKET_KEYS: usize = 8;
pub const MAX_KEY_PREFIX: usize = 12;
pub const MAX_ERROR_CODE: usize = 16;
pub const DEFAULT_DEADLINE: Duration = Duration::from_secs(15);
pub const FULL_POLL_INTERVAL: Duration = Duration::from_secs(300);
pub const STALE_AFTER: Duration = Duration::from_secs(900);

const ERROR_CODES: [&str; 11] = [
    "", "E-2400", "E-2401", "E-2402", "E-2403", "E-2404", "E-2405", "E-2406", "E-2407",
    "E-2408", "E-2409",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChildExit {
    pub state: String,
    pub code: Option<i32>,
    pub signal: Option<i32>,
}

impl ChildExit {
    pub fn new(state: impl Into<String>, code: Option<i32>, signal: Option<i32>) -> Option<Self> {
        let state = state.into();
        if !matches!(state.as_str(), "not_started" | "running" | "exited" | "terminated" | "killed")
            || (code.is_some() && signal.is_some())
            || (matches!(state.as_str(), "not_started" | "running") && (code.is_some() || signal.is_some()))
            || (state == "exited" && signal.is_some())
            || code.is_some_and(|value| value < 0)
            || signal.is_some_and(|value| value <= 0)
        {
            return None;
        }
        Some(Self { state, code, signal })
    }

    pub fn not_started() -> Self {
        Self { state: "not_started".to_owned(), code: None, signal: None }
    }

    fn exited(code: i32) -> Self {
        Self { state: "exited".to_owned(), code: Some(code.max(0)), signal: None }
    }

    fn terminated(code: Option<i32>, signal: Option<i32>) -> Self {
        Self { state: "terminated".to_owned(), code: code.map(|value| value.max(0)), signal }
    }

    fn killed(code: Option<i32>, signal: Option<i32>) -> Self {
        Self { state: "killed".to_owned(), code: code.map(|value| value.max(0)), signal }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BucketManifest {
    pub present: bool,
    pub observed_key_count: usize,
    pub key_prefixes: Vec<String>,
    pub truncated: bool,
    pub selected_key: Option<String>,
}

impl Default for BucketManifest {
    fn default() -> Self {
        Self { present: false, observed_key_count: 0, key_prefixes: Vec::new(), truncated: false, selected_key: None }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Redaction {
    pub result: String,
    pub rejected_field_count: usize,
    pub bucket_manifest: BucketManifest,
}

impl Default for Redaction {
    fn default() -> Self {
        Self { result: "pass".to_owned(), rejected_field_count: 0, bucket_manifest: BucketManifest::default() }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodexView {
    pub source_state: String,
    pub primary: Option<u8>,
    pub secondary: Option<u8>,
    pub reset_text: String,
    pub observation_age: String,
    pub reached_limit: Option<bool>,
    pub error_code: String,
    pub internal_reason: String,
}

impl Default for CodexView {
    fn default() -> Self {
        Self {
            source_state: "unavailable".to_owned(),
            primary: None,
            secondary: None,
            reset_text: "RESET N/A".to_owned(),
            observation_age: "AGE N/A".to_owned(),
            reached_limit: None,
            error_code: String::new(),
            internal_reason: String::new(),
        }
    }
}

impl CodexView {
    pub fn as_payload(&self) -> Value {
        json!({
            "source_state": self.source_state,
            "primary": self.primary,
            "secondary": self.secondary,
            "reset_text": self.reset_text.chars().take(32).collect::<String>(),
            "observation_age": self.observation_age.chars().take(16).collect::<String>(),
            "reached_limit": self.reached_limit,
            "error_code": self.error_code.chars().take(MAX_ERROR_CODE).collect::<String>(),
        })
    }

    pub fn as_snapshot(&self) -> CodexSnapshot {
        CodexSnapshot {
            source_state: self.source_state.clone(),
            primary: self.primary,
            secondary: self.secondary,
            reset_text: self.reset_text.clone(),
            observation_age: self.observation_age.clone(),
            reached_limit: self.reached_limit,
            error_code: self.error_code.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodexResult {
    pub view: CodexView,
    pub handshake: Vec<String>,
    pub deadline_ms: u64,
    pub elapsed_ms: u64,
    pub child_exit: ChildExit,
    pub redaction: Redaction,
    pub account_observed: bool,
    pub rate_limits_observed: bool,
}

impl CodexResult {
    pub fn as_evidence(&self) -> Value {
        json!({
            "deadline_ms": self.deadline_ms,
            "elapsed_ms": self.elapsed_ms,
            "child_exit": {"state": self.child_exit.state, "code": self.child_exit.code, "signal": self.child_exit.signal},
            "handshake": self.handshake,
            "account_observed": self.account_observed,
            "rate_limits_observed": self.rate_limits_observed,
            "redaction": {
                "result": self.redaction.result,
                "rejected_field_count": self.redaction.rejected_field_count,
                "bucket_manifest": {
                    "present": self.redaction.bucket_manifest.present,
                    "observed_key_count": self.redaction.bucket_manifest.observed_key_count,
                    "key_prefixes": self.redaction.bucket_manifest.key_prefixes,
                    "truncated": self.redaction.bucket_manifest.truncated,
                    "selected_key": self.redaction.bucket_manifest.selected_key,
                },
            },
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CodexChildError {
    pub code: &'static str,
}

impl CodexChildError {
    fn new(code: &'static str) -> Self { Self { code } }
}

/// A deliberately small process seam. Tests inject a deterministic child;
/// production uses `StdCodexProcessFactory`, which invokes direct argv.
pub trait CodexProcess: Send {
    fn send_line(&mut self, line: &[u8]) -> Result<(), CodexChildError>;
    fn read_line(&mut self, timeout: Duration) -> Result<Vec<u8>, CodexChildError>;
    fn try_wait(&mut self) -> Result<Option<ChildExit>, CodexChildError>;
    fn terminate(&mut self) -> Result<(), CodexChildError>;
    fn kill(&mut self) -> Result<(), CodexChildError>;
    fn wait(&mut self, timeout: Duration) -> Result<Option<ChildExit>, CodexChildError>;
}

pub trait CodexProcessFactory: Send + Sync {
    fn spawn(&self, argv: &[String]) -> Result<Box<dyn CodexProcess>, CodexChildError>;
}

#[derive(Debug, Default, Clone, Copy)]
pub struct StdCodexProcessFactory;

impl CodexProcessFactory for StdCodexProcessFactory {
    fn spawn(&self, argv: &[String]) -> Result<Box<dyn CodexProcess>, CodexChildError> {
        let Some((executable, args)) = argv.split_first() else {
            return Err(CodexChildError::new("E-2400"));
        };
        let child = Command::new(executable)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| CodexChildError::new("E-2400"))?;
        StdCodexProcess::new(child)
            .map(|process| Box::new(process) as Box<dyn CodexProcess>)
            .map_err(|_| CodexChildError::new("E-2409"))
    }
}

struct StdCodexProcess {
    child: Child,
    stdin: ChildStdin,
    lines: mpsc::Receiver<Result<Vec<u8>, CodexChildError>>,
}

impl StdCodexProcess {
    fn new(mut child: Child) -> Result<Self, std::io::Error> {
        let stdin = child.stdin.take().ok_or_else(|| std::io::Error::other("stdin unavailable"))?;
        let mut stdout = child.stdout.take().ok_or_else(|| std::io::Error::other("stdout unavailable"))?;
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut line = Vec::with_capacity(MAX_LINE_BYTES);
            let mut byte = [0_u8; 1];
            loop {
                match stdout.read(&mut byte) {
                    Ok(0) => {
                        let _ = sender.send(Err(CodexChildError::new("E-2403")));
                        return;
                    }
                    Ok(_) if byte[0] == b'\n' => {
                        if sender.send(Ok(std::mem::take(&mut line))).is_err() { return; }
                        line.reserve(MAX_LINE_BYTES);
                    }
                    Ok(_) => {
                        if line.len() >= MAX_LINE_BYTES {
                            let _ = sender.send(Err(CodexChildError::new("E-2404")));
                            return;
                        }
                        line.push(byte[0]);
                    }
                    Err(_) => {
                        let _ = sender.send(Err(CodexChildError::new("E-2409")));
                        return;
                    }
                }
            }
        });
        Ok(Self { child, stdin, lines: receiver })
    }

    fn status_exit(status: std::process::ExitStatus) -> ChildExit {
        if status.success() { return ChildExit::exited(status.code().unwrap_or(0)); }
        #[cfg(unix)]
        {
            use std::os::unix::process::ExitStatusExt;
            if let Some(signal) = status.signal() { return ChildExit::terminated(None, Some(signal)); }
        }
        ChildExit::exited(status.code().unwrap_or(1))
    }
}

impl CodexProcess for StdCodexProcess {
    fn send_line(&mut self, line: &[u8]) -> Result<(), CodexChildError> {
        if line.len() > MAX_LINE_BYTES { return Err(CodexChildError::new("E-2408")); }
        self.stdin.write_all(line).map_err(|_| CodexChildError::new("E-2409"))?;
        self.stdin.flush().map_err(|_| CodexChildError::new("E-2409"))?;
        Ok(())
    }

    fn read_line(&mut self, timeout: Duration) -> Result<Vec<u8>, CodexChildError> {
        self.lines.recv_timeout(timeout).map_err(|error| match error {
            mpsc::RecvTimeoutError::Timeout => CodexChildError::new("E-2402"),
            mpsc::RecvTimeoutError::Disconnected => CodexChildError::new("E-2403"),
        })?
    }

    fn try_wait(&mut self) -> Result<Option<ChildExit>, CodexChildError> {
        self.child.try_wait().map_err(|_| CodexChildError::new("E-2409")).map(|status| status.map(Self::status_exit))
    }

    fn terminate(&mut self) -> Result<(), CodexChildError> { self.child.kill().map_err(|_| CodexChildError::new("E-2409")) }

    fn kill(&mut self) -> Result<(), CodexChildError> { self.child.kill().map_err(|_| CodexChildError::new("E-2409")) }

    fn wait(&mut self, timeout: Duration) -> Result<Option<ChildExit>, CodexChildError> {
        let deadline = std::time::Instant::now() + timeout;
        loop {
            if let Some(status) = self.child.try_wait().map_err(|_| CodexChildError::new("E-2409"))? {
                return Ok(Some(Self::status_exit(status)));
            }
            if std::time::Instant::now() >= deadline { return Ok(None); }
            thread::sleep(Duration::from_millis(2));
        }
    }
}

#[derive(Clone)]
pub struct CodexCollector {
    executable: String,
    deadline: Duration,
    clock: Arc<dyn Fn() -> Duration + Send + Sync>,
    factory: Arc<dyn CodexProcessFactory>,
    cache: Option<CacheSnapshot>,
    baseline_known: bool,
    last_full_observed_at: Option<Duration>,
    last_observed_at: Option<Duration>,
    next_full_at: Option<Duration>,
    refetch_pending: bool,
    state: String,
    error_code: String,
    internal_reason: String,
    account_marker: Option<[u8; 32]>,
    pub last_result: Option<CodexResult>,
}

impl std::fmt::Debug for CodexCollector {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.debug_struct("CodexCollector")
            .field("executable", &self.executable)
            .field("deadline", &self.deadline)
            .field("baseline_known", &self.baseline_known)
            .field("last_full_observed_at", &self.last_full_observed_at)
            .field("last_observed_at", &self.last_observed_at)
            .field("next_full_at", &self.next_full_at)
            .field("refetch_pending", &self.refetch_pending)
            .field("state", &self.state)
            .field("error_code", &self.error_code)
            .field("internal_reason", &self.internal_reason)
            .finish()
    }
}

impl CodexCollector {
    pub fn new() -> Self {
        Self::with_factory_and_clock("codex", DEFAULT_DEADLINE, Arc::new(StdCodexProcessFactory), Arc::new(system_now))
            .expect("default Codex collector configuration is valid")
    }

    pub fn try_new(executable: impl Into<String>, deadline: Duration) -> Result<Self, &'static str> {
        Self::with_factory_and_clock(executable, deadline, Arc::new(StdCodexProcessFactory), Arc::new(system_now))
    }

    pub fn with_factory(executable: impl Into<String>, deadline: Duration, factory: Arc<dyn CodexProcessFactory>) -> Result<Self, &'static str> {
        Self::with_factory_and_clock(executable, deadline, factory, Arc::new(system_now))
    }

    pub fn with_clock<C: Fn() -> Duration + Send + Sync + 'static>(executable: impl Into<String>, deadline: Duration, clock: C) -> Result<Self, &'static str> {
        Self::with_factory_and_clock(executable, deadline, Arc::new(StdCodexProcessFactory), Arc::new(clock))
    }

    pub fn with_factory_and_clock(executable: impl Into<String>, deadline: Duration, factory: Arc<dyn CodexProcessFactory>, clock: Arc<dyn Fn() -> Duration + Send + Sync>) -> Result<Self, &'static str> {
        if deadline.is_zero() || deadline > Duration::from_secs(120) { return Err("deadline is out of bounds"); }
        Ok(Self {
            executable: executable.into(), deadline, clock, factory,
            cache: None, baseline_known: false, last_full_observed_at: None, last_observed_at: None,
            next_full_at: None, refetch_pending: false, state: "unavailable".to_owned(),
            error_code: String::new(), internal_reason: String::new(), account_marker: None, last_result: None,
        })
    }

    fn now(&self) -> Duration { (self.clock)() }
    pub fn deadline(&self) -> Duration { self.deadline }
    pub fn last_full_observed_at(&self) -> Option<Duration> { self.last_full_observed_at }
    pub fn last_observed_at(&self) -> Option<Duration> { self.last_observed_at }
    pub fn refetch_pending(&self) -> bool { self.refetch_pending }

    pub fn view(&self) -> CodexView {
        let cache = self.cache.clone().unwrap_or_default();
        let mut state = self.state.clone();
        if !self.baseline_known && !matches!(state.as_str(), "auth_required" | "codex_offline" | "host_offline") {
            state = "unavailable".to_owned();
        } else if state == "current" && self.last_observed_at.is_some_and(|observed| self.now().saturating_sub(observed) >= STALE_AFTER) {
            state = "stale".to_owned();
        }
        CodexView {
            source_state: state, primary: cache.primary, secondary: cache.secondary,
            reset_text: reset_text(&cache, self.now()), observation_age: observation_age(self.last_observed_at, self.now()),
            reached_limit: cache.reached_limit, error_code: self.error_code.clone(), internal_reason: self.internal_reason.clone(),
        }
    }

    pub fn should_poll(&self, now: Option<Duration>) -> bool {
        let now = now.unwrap_or_else(|| self.now());
        self.refetch_pending || self.next_full_at.is_none_or(|deadline| now >= deadline)
    }

    pub fn consume_refetch(&mut self) -> bool {
        let pending = self.refetch_pending; self.refetch_pending = false; pending
    }

    fn schedule_refetch(&mut self) { self.refetch_pending = true; }

    pub fn apply_full_response(&mut self, response: &Value) -> CodexView {
        let Some(rate_limits) = response.get("rateLimits").and_then(Value::as_object) else {
            self.state = "unavailable".to_owned(); self.error_code = "E-2401".to_owned(); self.internal_reason = "bucket_unavailable".to_owned();
            if !self.baseline_known { self.cache = None; }
            return self.view();
        };
        let Ok(cache) = cache_from_full(rate_limits) else {
            self.state = "unavailable".to_owned(); self.error_code = "E-2401".to_owned(); self.internal_reason = "bucket_unavailable".to_owned();
            return self.view();
        };
        let now = self.now();
        self.cache = Some(cache.clone()); self.baseline_known = true; self.last_full_observed_at = Some(now); self.last_observed_at = Some(now);
        self.next_full_at = Some(now.saturating_add(FULL_POLL_INTERVAL)); self.refetch_pending = false;
        self.error_code = if cache.primary.is_some() || cache.secondary.is_some() { String::new() } else { "E-2401".to_owned() };
        self.internal_reason = if self.error_code.is_empty() { String::new() } else { "bucket_unavailable".to_owned() };
        self.state = if self.error_code.is_empty() { "current" } else { "unavailable" }.to_owned();
        self.view()
    }

    pub fn apply_sparse_update(&mut self, update: &Value) -> bool {
        let update = if update.get("method").and_then(Value::as_str) == Some("account/rateLimits/updated") { update.get("params").unwrap_or(&Value::Null) } else { update };
        if !self.baseline_known { self.schedule_refetch(); return false; }
        let Some(rate_limits) = update.get("rateLimits").and_then(Value::as_object) else { return false; };
        let mut next = self.cache.clone().unwrap_or_default(); let mut seen = false;
        for source in ["primary", "secondary"] {
            let Some(window) = rate_limits.get(source) else { continue; }; seen = true;
            let slot = if source == "primary" { next.source_primary_slot.clone() } else { next.source_secondary_slot.clone() };
            let reset_index = if slot == "primary" { 0 } else { 1 };
            if window.is_null() { set_slot(&mut next, &slot, None, None); continue; }
            let Some(object) = window.as_object() else { return false; };
            if object.keys().any(|key| !matches!(key.as_str(), "usedPercent" | "resetsAt" | "windowDurationMins")) || (!object.contains_key("usedPercent") && !object.contains_key("resetsAt")) { return false; }
            if object.contains_key("windowDurationMins") { let Ok(mapped) = window_slot(source, window) else { return false; }; if mapped != slot { return false; } }
            let percent = if let Some(value) = object.get("usedPercent") { match parse_percent(value) { Ok(value) => value, Err(()) => return false } } else { slot_value(&next, &slot) };
            let reset = if let Some(value) = object.get("resetsAt") { match parse_reset(value) { Ok(value) => value, Err(()) => return false } } else { slot_reset(&next, reset_index) };
            set_slot(&mut next, &slot, percent, reset);
        }
        if let Some(value) = rate_limits.get("rateLimitReachedType") {
            seen = true; if !value.is_null() && value.as_str().is_none() { return false; }
            if let Some(value) = value.as_str() { next.reached_limit = Some(!value.is_empty()); }
        }
        if let Some(value) = rate_limits.get("planType") {
            seen = true; if !value.is_null() && value.as_str().is_none() { return false; }
            if let Some(value) = value.as_str() { next.plan_type = Some(value.to_owned()); }
        }
        if let Some(value) = rate_limits.get("spendControlReached") {
            seen = true; if !value.is_null() && value.as_bool().is_none() { return false; }
            if let Some(value) = value.as_bool() { next.spend_control_reached = Some(value); }
        }
        if !seen { return false; }
        self.cache = Some(next.clone()); self.last_observed_at = Some(self.now()); self.state = "current".to_owned();
        self.error_code = if next.primary.is_some() || next.secondary.is_some() { String::new() } else { "E-2401".to_owned() };
        self.internal_reason = if self.error_code.is_empty() { String::new() } else { "bucket_unavailable".to_owned() };
        self.schedule_refetch(); true
    }

    pub fn account_changed(&mut self, auth_required: bool) -> CodexView {
        self.cache = None; self.baseline_known = false; self.last_full_observed_at = None; self.last_observed_at = None; self.next_full_at = None; self.refetch_pending = true;
        self.state = if auth_required { "auth_required" } else { "unavailable" }.to_owned(); self.error_code.clear(); self.internal_reason.clear(); self.view()
    }

    pub fn collect(&mut self) -> CodexResult {
        let started = self.now(); let deadline = started.saturating_add(self.deadline); let deadline_ms = self.deadline.as_millis().min(u128::from(u64::MAX)) as u64;
        let mut handshake = Vec::new(); let mut redaction = Redaction::default(); let mut account_observed = false; let mut rate_limits_observed = false; let mut failure: Option<(&'static str, &'static str)> = None;
        let mut child = match self.factory.spawn(&[self.executable.clone(), "app-server".to_owned(), "--stdio".to_owned()]) {
            Ok(child) => Some(child), Err(error) => { failure = Some(("codex_offline", valid_error_code(error.code))); None }
        };
        if let Some(process) = child.as_mut() {
            let stages = [
                (1_u64, "initialize", json!({"clientInfo":{"name":"herdr_agent_keypad","title":"Herdr Agent Keypad","version":"0.1.0"}})),
                (0_u64, "initialized", json!({})),
                (2_u64, "account/read", json!({"refreshToken":false})),
                (3_u64, "account/rateLimits/read", Value::Null),
            ];
            for (id, method, params) in stages {
                if method == "initialized" {
                    if let Err(error) = send_notification(process.as_mut(), method, params) { failure = Some(("codex_offline", valid_error_code(error.code))); break; }
                    handshake.push(method.to_owned()); continue;
                }
                if let Err(error) = send_request(process.as_mut(), id, method, params) { failure = Some(("codex_offline", valid_error_code(error.code))); break; }
                let response = match receive_message(process.as_mut(), id, remaining(deadline, self.now())) {
                    Ok(response) => response, Err((state, code)) => { failure = Some((state, code)); break; }
                };
                if method == "initialize" { handshake.push(method.to_owned()); }
                else if method == "account/read" {
                    account_observed = true; handshake.push(method.to_owned());
                    if auth_evidence(&response) { failure = Some(("auth_required", "")); break; }
                    let marker = account_marker(&response); if self.account_marker.is_some_and(|prior| prior != marker) { self.account_changed(false); }
                    self.account_marker = Some(marker);
                } else {
                    handshake.push(method.to_owned()); rate_limits_observed = true; redaction = redaction_from_response(&response); self.apply_full_response(&response);
                }
            }
        }
        let child_exit = match child.as_mut() { None => ChildExit::not_started(), Some(process) => stop_child(process.as_mut()) };
        if let Some((state, code)) = failure {
            if state == "auth_required" { self.account_changed(true); redaction = Redaction { bucket_manifest: redaction.bucket_manifest, ..Redaction::default() }; }
            else { self.state = state.to_owned(); self.error_code = if ERROR_CODES.contains(&code) { code.to_owned() } else { String::new() }; self.internal_reason.clear(); }
        }
        let elapsed_ms = self.now().saturating_sub(started).as_millis().min(u128::from(deadline_ms)) as u64;
        let result = CodexResult { view: self.view(), handshake, deadline_ms, elapsed_ms, child_exit, redaction, account_observed, rate_limits_observed };
        self.last_result = Some(result.clone()); result
    }

    pub async fn collect_async(&mut self) -> CodexResult { self.collect() }
}

#[derive(Debug, Clone, Default)]
struct CacheSnapshot {
    primary: Option<u8>, secondary: Option<u8>, primary_reset: Option<i64>, secondary_reset: Option<i64>, reached_limit: Option<bool>, plan_type: Option<String>, spend_control_reached: Option<bool>,
    source_primary_slot: String, source_secondary_slot: String,
}

impl CacheSnapshot {
    fn with_defaults() -> Self { Self { source_primary_slot: "primary".to_owned(), source_secondary_slot: "secondary".to_owned(), ..Self::default() } }
}

fn system_now() -> Duration { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default() }

fn observation_age(observed: Option<Duration>, now: Duration) -> String { observed.map_or_else(|| "AGE N/A".to_owned(), |value| format!("AGE {}M", now.saturating_sub(value).as_secs() / 60)) }

fn reset_text(cache: &CacheSnapshot, now: Duration) -> String {
    let now = now.as_secs() as i64; let mut candidates: Vec<(i64, String)> = Vec::new();
    for (reset, label) in [(cache.primary_reset, "5H"), (cache.secondary_reset, "WEEK")] {
        let Some(reset) = reset else { continue; }; if reset <= now { continue; }
        let remaining = ((reset - now + 59) / 60).max(1); let days = remaining / (24 * 60); let day_minutes = remaining % (24 * 60); let hours = day_minutes / 60; let minutes = day_minutes % 60; let prefix = format!("RESET {label} ");
        let mut duration = if days > 0 { let full = format!("{days}D{hours}H{minutes}M"); if prefix.len() + full.len() > 18 { format!("{days}D{hours}H") } else { full } } else if hours > 0 { if minutes > 0 { format!("{hours}H{minutes}M") } else { format!("{hours}H") } } else { format!("{minutes}M") };
        duration.truncate(32usize.saturating_sub(prefix.len())); candidates.push((reset, prefix + &duration));
    }
    candidates.into_iter().min_by_key(|entry| entry.0).map_or_else(|| "RESET N/A".to_owned(), |entry| entry.1)
}

fn manifest(value: Option<&Value>) -> BucketManifest {
    let Some(value) = value else { return BucketManifest::default(); }; if value.is_null() || !value.is_object() { return BucketManifest { present: true, ..BucketManifest::default() }; }
    let object = value.as_object().expect("checked object"); let mut prefixes: Vec<String> = object.keys().map(|key| hash_prefix(key)).collect(); prefixes.sort(); prefixes.truncate(MAX_BUCKET_KEYS);
    BucketManifest { present: true, observed_key_count: object.len().min(usize::from(u16::MAX)), key_prefixes: prefixes, truncated: object.len() > MAX_BUCKET_KEYS, selected_key: None }
}

fn hash_prefix(value: &str) -> String {
    let mut hasher = Sha256::new(); hasher.update(value.as_bytes()); let bytes = hasher.finalize(); let mut text = String::with_capacity(64); for byte in bytes { text.push_str(&format!("{byte:02x}")); } text.chars().take(MAX_KEY_PREFIX).collect()
}

fn parse_percent(value: &Value) -> Result<Option<u8>, ()> { if value.is_null() { return Ok(None); } let value = value.as_u64().ok_or(())?; if value > 100 { return Err(()); } Ok(Some(value as u8)) }
fn parse_reset(value: &Value) -> Result<Option<i64>, ()> { if value.is_null() { Ok(None) } else { value.as_i64().map(Some).ok_or(()) } }

fn window_slot(source: &str, window: &Value) -> Result<String, ()> {
    let Some(object) = window.as_object() else { return Ok(source.to_owned()); }; let Some(duration) = object.get("windowDurationMins") else { return Ok(source.to_owned()); }; let duration = duration.as_u64().ok_or(())?;
    match duration { 300 => Ok("primary".to_owned()), 10_080 => Ok("secondary".to_owned()), _ => Err(()) }
}

fn source_slots(rate_limits: &Map<String, Value>) -> Result<(String, String), ()> {
    let mut primary_slot = window_slot("primary", rate_limits.get("primary").unwrap_or(&Value::Null))?; let mut secondary_slot = window_slot("secondary", rate_limits.get("secondary").unwrap_or(&Value::Null))?;
    if primary_slot == secondary_slot {
        if rate_limits.get("primary").is_none_or(Value::is_null) { primary_slot = if primary_slot == "primary" { "secondary" } else { "primary" }.to_owned(); }
        else if rate_limits.get("secondary").is_none_or(Value::is_null) { secondary_slot = if secondary_slot == "primary" { "secondary" } else { "primary" }.to_owned(); }
        else { return Err(()); }
    }
    Ok((primary_slot, secondary_slot))
}

fn cache_from_full(rate_limits: &Map<String, Value>) -> Result<CacheSnapshot, ()> {
    let (source_primary_slot, source_secondary_slot) = source_slots(rate_limits)?; let mut cache = CacheSnapshot { source_primary_slot, source_secondary_slot, ..CacheSnapshot::with_defaults() };
    for (source, slot) in [("primary", cache.source_primary_slot.clone()), ("secondary", cache.source_secondary_slot.clone())] {
        let window = rate_limits.get(source).unwrap_or(&Value::Null); if !window.is_null() { let object = window.as_object().ok_or(())?; let percent = parse_percent(object.get("usedPercent").ok_or(())?)?; let reset = object.get("resetsAt").map_or(Ok(None), parse_reset)?; set_slot(&mut cache, &slot, percent, reset); }
    }
    if let Some(value) = rate_limits.get("rateLimitReachedType") { if !value.is_null() && value.as_str().is_none() { return Err(()); } cache.reached_limit = value.as_str().map(|value| !value.is_empty()); }
    if let Some(value) = rate_limits.get("spendControlReached") { if !value.is_null() && value.as_bool().is_none() { return Err(()); } cache.spend_control_reached = value.as_bool(); }
    if let Some(value) = rate_limits.get("planType") { if !value.is_null() && value.as_str().is_none() { return Err(()); } cache.plan_type = value.as_str().map(str::to_owned); }
    Ok(cache)
}

fn set_slot(cache: &mut CacheSnapshot, slot: &str, value: Option<u8>, reset: Option<i64>) { if slot == "primary" { cache.primary = value; cache.primary_reset = reset; } else { cache.secondary = value; cache.secondary_reset = reset; } }
fn slot_value(cache: &CacheSnapshot, slot: &str) -> Option<u8> { if slot == "primary" { cache.primary } else { cache.secondary } }
fn slot_reset(cache: &CacheSnapshot, slot: usize) -> Option<i64> { if slot == 0 { cache.primary_reset } else { cache.secondary_reset } }
fn valid_error_code(code: &'static str) -> &'static str { if ERROR_CODES.contains(&code) { code } else { "E-2409" } }
fn remaining(deadline: Duration, now: Duration) -> Duration { deadline.saturating_sub(now).max(Duration::from_millis(1)) }

fn send_request(process: &mut dyn CodexProcess, id: u64, method: &str, params: Value) -> Result<(), CodexChildError> { send_value(process, json!({"id": id, "method": method, "params": params})) }
fn send_notification(process: &mut dyn CodexProcess, method: &str, params: Value) -> Result<(), CodexChildError> { send_value(process, json!({"method": method, "params": params})) }
fn send_value(process: &mut dyn CodexProcess, value: Value) -> Result<(), CodexChildError> { let mut line = serde_json::to_vec(&value).map_err(|_| CodexChildError::new("E-2408"))?; line.push(b'\n'); if line.len() > MAX_LINE_BYTES { return Err(CodexChildError::new("E-2408")); } process.send_line(&line) }

fn receive_message(process: &mut dyn CodexProcess, id: u64, timeout: Duration) -> Result<Value, (&'static str, &'static str)> {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        let remaining = deadline.saturating_duration_since(std::time::Instant::now());
        if remaining.is_zero() {
            return Err(("codex_offline", "E-2402"));
        }
        let line = process
            .read_line(remaining)
            .map_err(|error| ("codex_offline", valid_error_code(error.code)))?;
        if line.len() > MAX_LINE_BYTES {
            return Err(("codex_offline", "E-2404"));
        }
        let value: Value = serde_json::from_slice(&line).map_err(|_| ("codex_offline", "E-2405"))?;
        let object = value.as_object().ok_or(("codex_offline", "E-2405"))?;
        if object.get("id").and_then(Value::as_u64) != Some(id) {
            continue;
        }
        if object.contains_key("error") {
            if auth_evidence(&value) {
                return Err(("auth_required", ""));
            }
            return Err(("codex_offline", "E-2406"));
        }
        return object
            .get("result")
            .filter(|value| value.is_object())
            .cloned()
            .ok_or(("codex_offline", "E-2407"));
    }
}

fn auth_evidence(value: &Value) -> bool {
    let Some(object) = value.as_object() else { return false; }; if object.get("account").is_some_and(Value::is_null) && object.get("requiresOpenaiAuth").and_then(Value::as_bool) == Some(true) { return true; }
    object.get("error").and_then(Value::as_object).and_then(|error| error.get("code")).and_then(Value::as_str).is_some_and(|code| matches!(code.to_ascii_lowercase().as_str(), "unauthorized" | "not_authenticated" | "auth_required" | "401"))
}

fn account_marker(value: &Value) -> [u8; 32] { let mut hasher = Sha256::new(); if let Some(account) = value.get("account") { if let Ok(bytes) = serde_json::to_vec(account) { hasher.update(bytes); } } hasher.finalize().into() }
fn redaction_from_response(response: &Value) -> Redaction { Redaction { bucket_manifest: manifest(response.get("rateLimitsByLimitId")), ..Redaction::default() } }

fn stop_child(process: &mut dyn CodexProcess) -> ChildExit {
    match process.try_wait() { Ok(Some(exit)) => return ChildExit { state: "exited".to_owned(), ..exit }, Ok(None) | Err(_) => {} }
    if process.terminate().is_ok() { if let Ok(Some(exit)) = process.wait(Duration::from_secs(1)) { return ChildExit { state: "terminated".to_owned(), ..exit }; } }
    let _ = process.kill(); match process.wait(Duration::from_secs(1)) { Ok(Some(exit)) => ChildExit { state: "killed".to_owned(), ..exit }, _ => ChildExit::killed(None, None) }
}

/// Reject evidence-shaped values recursively without returning any sensitive value to callers.
pub fn redaction_passes(value: &Value) -> bool {
    const FORBIDDEN: [&str; 10] = ["token", "secret", "password", "email", "codexhome", "path", "prompt", "transcript", "stderr", "stdout"];
    match value { Value::Object(object) => object.iter().all(|(key, item)| !FORBIDDEN.iter().any(|word| key.to_ascii_lowercase().contains(word)) && redaction_passes(item)), Value::Array(items) => items.iter().all(redaction_passes), _ => true }
}

pub fn normalize_rate_limits(response: &Value) -> (CodexView, Redaction) {
    let redaction = Redaction { bucket_manifest: manifest(response.get("rateLimitsByLimitId")), ..Redaction::default() };
    let Some(rate_limits) = response.get("rateLimits").and_then(Value::as_object) else { return (CodexView { error_code: "E-2401".to_owned(), internal_reason: "bucket_unavailable".to_owned(), ..CodexView::default() }, redaction); };
    let Ok(cache) = cache_from_full(rate_limits) else { return (CodexView { error_code: "E-2401".to_owned(), internal_reason: "bucket_unavailable".to_owned(), ..CodexView::default() }, redaction); };
    if cache.primary.is_none() && cache.secondary.is_none() { return (CodexView { error_code: "E-2401".to_owned(), internal_reason: "bucket_unavailable".to_owned(), ..CodexView::default() }, redaction); }
    (CodexView { source_state: "current".to_owned(), primary: cache.primary, secondary: cache.secondary, reset_text: reset_text(&cache, system_now()), reached_limit: cache.reached_limit, ..CodexView::default() }, redaction)
}
