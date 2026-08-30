//! Default-off, bounded, redacted operational tracing.
//!
//! The bridge emits only the same allowlisted `SafeCode` vocabulary used by the
//! status transition ring.  There is no file logger, rotating sink, journald
//! integration, ingestion stream, or raw upstream diagnostic path.

use super::status::{SafeCode, SafeEvent, StatusError, STATUS_PAYLOAD_LIMIT};
use serde::Serialize;
use std::io::{self, Write};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct TraceConfig {
    pub enabled: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct SafeLogRecord {
    event: &'static str,
    schema_version: u8,
    code: SafeCode,
    at_ms: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LogError {
    Invalid,
    Oversized,
    Io,
}

impl From<StatusError> for LogError {
    fn from(error: StatusError) -> Self {
        match error {
            StatusError::Invalid => Self::Invalid,
            StatusError::Oversized => Self::Oversized,
        }
    }
}

/// A logger is inert unless startup config explicitly enables it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SafeLogger {
    config: TraceConfig,
}

impl SafeLogger {
    pub const fn new(config: TraceConfig) -> Self {
        Self { config }
    }

    pub const fn enabled(&self) -> bool {
        self.config.enabled
    }

    pub fn serialize(&self, code: SafeCode, at_ms: u64) -> Option<String> {
        if !self.enabled() {
            return None;
        }
        let record = SafeLogRecord {
            event: "herdr_keypad",
            schema_version: 1,
            code,
            at_ms,
        };
        let bytes = serde_json::to_vec(&record).ok()?;
        if bytes.len() > STATUS_PAYLOAD_LIMIT {
            return None;
        }
        String::from_utf8(bytes).ok()
    }

    /// Emit a safe event to an explicitly supplied sink.  Production passes
    /// stderr; keeping the operation line-oriented prevents an unbounded event
    /// stream or accidental raw payload forwarding.
    pub fn emit_to<W: Write>(&self, sink: &mut W, code: SafeCode, at_ms: u64) -> Result<bool, LogError> {
        let Some(line) = self.serialize(code, at_ms) else {
            return Ok(false);
        };
        sink.write_all(line.as_bytes()).map_err(|_| LogError::Io)?;
        sink.write_all(b"\n").map_err(|_| LogError::Io)?;
        Ok(true)
    }

    /// Install a scoped `tracing-subscriber` stderr formatter only after
    /// validated startup config opted in.  Callers retain the guard for the
    /// desired bridge lifetime.
    pub fn install_stderr(&self) -> Option<TraceGuard> {
        if !self.enabled() {
            return None;
        }
        let subscriber = tracing_subscriber::fmt()
            .with_ansi(false)
            .with_max_level(tracing::Level::INFO)
            .finish();
        Some(TraceGuard { guard: tracing::subscriber::set_default(subscriber) })
    }

    /// Record one allowlisted event through tracing.  The call is a no-op when
    /// tracing was not enabled at startup.
    pub fn emit(&self, code: SafeCode, at_ms: u64) -> bool {
        if !self.enabled() {
            return false;
        }
        tracing::info!(target: "herdr_keypad", code = ?code, at_ms, "bridge_event");
        true
    }

    pub fn emit_stderr(&self, code: SafeCode, at_ms: u64) -> Result<bool, LogError> {
        let mut stderr = io::stderr().lock();
        self.emit_to(&mut stderr, code, at_ms)
    }
}

pub struct TraceGuard {
    guard: tracing::dispatcher::DefaultGuard,
}

impl Drop for TraceGuard {
    fn drop(&mut self) {
        // Keeping the field makes the scoped subscriber lifetime explicit.
        let _ = &self.guard;
    }
}

/// Validate an externally captured log line before accepting it into a bounded
/// invocation-log test or status fixture.  This function never returns text.
pub fn validate_safe_line(line: &[u8]) -> Result<SafeEvent, LogError> {
    if line.len() > STATUS_PAYLOAD_LIMIT {
        return Err(LogError::Oversized);
    }
    let event: SafeEvent = serde_json::from_slice(line).map_err(|_| LogError::Invalid)?;
    if event.schema_version != 1 {
        return Err(LogError::Invalid);
    }
    Ok(event)
}
