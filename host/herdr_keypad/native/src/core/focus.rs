//! Exact focus-only authorization.
//!
//! A device press becomes one complete live read followed by at most two exact
//! `agent.focus` calls.  The port trait is intentionally closed: it has no
//! generic Herdr method, triage operation, keyboard operation, or keycode.

use super::model::{session_token, Binding, FocusIntent, FocusOutcome, FocusResult, FocusStatus, Identity};
use super::projection::InboxProjection;
use serde_json::Value;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FocusErrorKind {
    Offline,
    Timeout,
    NotFound,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FocusError {
    pub kind: FocusErrorKind,
    pub detail: String,
}

impl FocusError {
    pub fn offline(detail: impl Into<String>) -> Self { Self { kind: FocusErrorKind::Offline, detail: detail.into() } }
    pub fn timeout(detail: impl Into<String>) -> Self { Self { kind: FocusErrorKind::Timeout, detail: detail.into() } }
    pub fn not_found(detail: impl Into<String>) -> Self { Self { kind: FocusErrorKind::NotFound, detail: detail.into() } }
    pub fn failed(detail: impl Into<String>) -> Self { Self { kind: FocusErrorKind::Failed, detail: detail.into() } }
}

impl fmt::Display for FocusError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.write_str(&self.detail) }
}

impl std::error::Error for FocusError {}

pub trait HerdrPort {
    fn complete_read(&mut self) -> Result<Vec<Value>, FocusError>;
    fn focus(&mut self, pane_id: &str) -> Result<Value, FocusError>;
}

#[derive(Debug, Clone, Copy, Default)]
pub struct FocusExecutor {
    device_session: Option<&'static str>,
}

impl FocusExecutor {
    pub fn new() -> Self { Self { device_session: None } }

    /// Configure an optional current device session fence.  Device sessions
    /// are opaque and never become an action target.
    pub fn for_device_session(session: &'static str) -> Self { Self { device_session: Some(session) } }

    pub fn execute<P: HerdrPort>(&self, projection: &InboxProjection, intent: &FocusIntent, port: &mut P) -> FocusOutcome {
        if let Some(device_session) = self.device_session {
            if intent.device_session.as_deref() != Some(device_session) {
                return outcome(intent, FocusStatus::WrongEpoch, "device session differs");
            }
        }
        let Some(current) = &projection.current else {
            return outcome(intent, FocusStatus::Offline, "no committed projection");
        };
        if matches!(current.source_status, super::model::SourceStatus::Offline | super::model::SourceStatus::Unavailable) {
            return outcome(intent, FocusStatus::Offline, "source is not current");
        }
        if !current.source_status.is_current() || current.entries.iter().any(|entry| entry.stale) {
            return outcome(intent, FocusStatus::Stale, "projection generation is stale");
        }
        let binding = &intent.binding;
        if binding.host_epoch != current.host_epoch {
            return outcome(intent, FocusStatus::WrongEpoch, "host epoch differs");
        }
        if binding.snapshot_revision != current.snapshot_revision {
            return outcome(intent, FocusStatus::WrongRevision, "snapshot revision differs");
        }
        if binding.slot >= current.entries.len() {
            return outcome(intent, FocusStatus::WrongSlot, "slot is outside fixed projection");
        }
        let committed = &current.entries[binding.slot];
        if !committed.occupied() || committed.entry_id != binding.entry_id {
            return outcome(intent, FocusStatus::Empty, "slot is not an occupied binding");
        }
        if binding.entry_id != binding.identity.pane_id {
            return outcome(intent, FocusStatus::PaneReused, "entry and pane identity differ");
        }

        let rows = match port.complete_read() {
            Ok(rows) => rows,
            Err(error) => return outcome(intent, read_failure(error), "complete agent read failed"),
        };
        let live = match projection.live_identity(&rows, &binding.identity.pane_id) {
            Ok(Some(identity)) => identity,
            Ok(None) => return outcome(intent, FocusStatus::Vanished, "pane is absent from current agent.list"),
            Err(_) => return outcome(intent, FocusStatus::PaneReused, "current AgentInfo identity is malformed"),
        };
        if live.pane_id != binding.identity.pane_id
            || live.terminal_id != binding.identity.terminal_id
            || (!binding.identity.workspace_id.is_empty() && live.workspace_id != binding.identity.workspace_id)
            || (!binding.identity.tab_id.is_empty() && live.tab_id != binding.identity.tab_id)
        {
            return outcome(intent, FocusStatus::PaneReused, "current AgentInfo identity differs");
        }
        if live.agent_session != binding.identity.agent_session {
            return outcome(intent, FocusStatus::SessionChanged, "agent session differs");
        }
        if live.source_revision != binding.identity.source_revision {
            return outcome(intent, FocusStatus::SourceRevisionChanged, "source revision differs");
        }

        let first = match port.focus(&binding.identity.pane_id) {
            Ok(response) => response,
            Err(error) => return outcome(intent, write_failure(error), "agent.focus failed"),
        };
        let Some(first_agent) = acknowledgement_agent(&first) else {
            return outcome(intent, FocusStatus::Rejected, "focus response is not AgentInfo");
        };
        if let Some(status) = acknowledgement_status(&first_agent, binding) {
            return outcome(intent, status, "focus acknowledgement identity differs");
        }
        if first_agent.get("focused").and_then(Value::as_bool) != Some(true) {
            let retry = match port.focus(&binding.identity.pane_id) {
                Ok(response) => response,
                Err(error) => return outcome(intent, write_failure(error), "agent.focus retry failed"),
            };
            let Some(retry_agent) = acknowledgement_agent(&retry) else {
                return outcome(intent, FocusStatus::Rejected, "focus retry response is not AgentInfo");
            };
            if let Some(status) = acknowledgement_status(&retry_agent, binding) {
                return outcome(intent, status, "focus retry identity differs");
            }
            if retry_agent.get("focused").and_then(Value::as_bool) != Some(true) {
                return outcome(intent, FocusStatus::Rejected, "AgentInfo is not focused");
            }
        }
        outcome(intent, FocusStatus::Accepted, "agent.focus acknowledged")
    }

    pub fn result(&self, intent: FocusIntent, outcome: &FocusOutcome) -> FocusResult {
        FocusResult {
            intent,
            outcome: outcome.status,
            focused: outcome.success(),
            reason: outcome.reason.clone(),
        }
    }
}

fn outcome(intent: &FocusIntent, status: FocusStatus, reason: impl Into<String>) -> FocusOutcome {
    FocusOutcome { status, action_id: intent.action_id.clone(), reason: reason.into() }
}

fn read_failure(error: FocusError) -> FocusStatus {
    match error.kind {
        FocusErrorKind::Timeout => FocusStatus::Uncertain,
        FocusErrorKind::NotFound | FocusErrorKind::Offline => FocusStatus::Offline,
        FocusErrorKind::Failed => FocusStatus::Failed,
    }
}

fn write_failure(error: FocusError) -> FocusStatus {
    match error.kind {
        FocusErrorKind::Timeout => FocusStatus::Uncertain,
        FocusErrorKind::NotFound => FocusStatus::Vanished,
        FocusErrorKind::Offline => FocusStatus::Offline,
        FocusErrorKind::Failed => FocusStatus::Failed,
    }
}

fn acknowledgement_agent(response: &Value) -> Option<&serde_json::Map<String, Value>> {
    let object = response.as_object()?;
    if object.get("type").and_then(Value::as_str) == Some("agent_info") {
        return object.get("agent").and_then(Value::as_object);
    }
    object
        .get("agent_info")
        .or_else(|| object.get("agent"))
        .and_then(Value::as_object)
        .or_else(|| (object.contains_key("pane_id") && object.contains_key("terminal_id")).then_some(object))
}

fn acknowledgement_status(agent: &serde_json::Map<String, Value>, binding: &Binding) -> Option<FocusStatus> {
    if agent.get("pane_id").and_then(Value::as_str) != Some(binding.identity.pane_id.as_str())
        || agent.get("terminal_id").and_then(Value::as_str) != Some(binding.identity.terminal_id.as_str())
        || (!binding.identity.workspace_id.is_empty() && agent.get("workspace_id").and_then(Value::as_str) != Some(binding.identity.workspace_id.as_str()))
        || (!binding.identity.tab_id.is_empty() && agent.get("tab_id").and_then(Value::as_str) != Some(binding.identity.tab_id.as_str()))
    {
        return Some(FocusStatus::PaneReused);
    }
    let session = session_token(agent.get("agent_session").unwrap_or(&Value::Null)).ok()?;
    if session != binding.identity.agent_session {
        return Some(FocusStatus::SessionChanged);
    }
    None
}

#[allow(dead_code)]
fn _identity_matches(left: &Identity, right: &Identity) -> bool { left.live_exact(right) }
