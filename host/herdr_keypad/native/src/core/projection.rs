//! Authoritative installed-inbox projection.
//!
//! Events only invalidate.  A complete `agent.list` plus `workspace.list` read
//! is the only operation that establishes ordering, fixed slots, and actionable
//! identity.  The installed plugin's literal rank mapping is intentionally kept
//! here instead of being recreated in an adapter or on the device.

use super::model::{
    opaque, session_token, text, AgentEntry, Identity, InboxRow, ProjectionError, ProjectionSnapshot,
    SourceStatus, Binding, MAX_DISCRIMINATOR, MAX_SLOTS, MAX_TEXT,
};
use serde_json::Value;
use std::collections::BTreeMap;

pub const PLUGIN_REVISION: &str = "78b243279b4da55150b58dc2cc3cffcdc2fd6a04";

pub struct InboxProjection {
    pub plugin_revision: String,
    pub schema_version: u32,
    pub host_epoch: String,
    pub snapshot_revision: u32,
    pub current: Option<ProjectionSnapshot>,
    last_entries: [AgentEntry; MAX_SLOTS],
    last_projection_key: Option<([AgentEntry; MAX_SLOTS], SourceStatus)>,
    workspace_labels: BTreeMap<String, String>,
}

impl InboxProjection {
    pub fn new(host_epoch: impl Into<String>) -> Result<Self, ProjectionError> {
        let host_epoch = host_epoch.into();
        opaque(&host_epoch, "host_epoch", false).map_err(|_| ProjectionError::unavailable())?;
        Ok(Self {
            plugin_revision: PLUGIN_REVISION.to_owned(),
            schema_version: 1,
            host_epoch,
            snapshot_revision: 0,
            current: None,
            last_entries: std::array::from_fn(|slot| AgentEntry::empty(slot, "empty")),
            last_projection_key: None,
            workspace_labels: BTreeMap::new(),
        })
    }

    pub fn refresh(&mut self, rows: &[Value], workspaces: &[Value]) -> Result<ProjectionSnapshot, ProjectionError> {
        self.refresh_with_status(rows, workspaces, "current")
    }

    pub fn refresh_with_status(
        &mut self,
        rows: &[Value],
        workspaces: &[Value],
        source_status: &str,
    ) -> Result<ProjectionSnapshot, ProjectionError> {
        let source_status = SourceStatus::parse(source_status).ok_or_else(ProjectionError::unavailable)?;
        let labels = workspace_labels(workspaces);
        let entries = self.project_entries(rows, &labels)?;
        let key = (entries.clone(), source_status);
        self.workspace_labels = labels;
        if self.current.is_some() && self.last_projection_key.as_ref() == Some(&key) {
            return Ok(self.current.clone().expect("current projection exists"));
        }
        self.snapshot_revision = self.snapshot_revision.saturating_add(1).max(1);
        let snapshot = ProjectionSnapshot {
            host_epoch: self.host_epoch.clone(),
            snapshot_revision: self.snapshot_revision,
            source_status,
            entries: entries.clone(),
        };
        self.last_entries = entries;
        self.last_projection_key = Some(key);
        self.current = Some(snapshot.clone());
        Ok(snapshot)
    }

    pub fn invalidate(&mut self, reason: &str) -> ProjectionSnapshot {
        let status = match reason {
            "offline" => SourceStatus::Offline,
            "unavailable" => SourceStatus::Unavailable,
            _ => SourceStatus::Stale,
        };
        self.snapshot_revision = self.snapshot_revision.saturating_add(1).max(1);
        let previous = self.current.clone();
        let source = previous
            .as_ref()
            .map(|snapshot| snapshot.entries.clone())
            .unwrap_or_else(|| self.last_entries.clone());
        let entries = source.map(|entry| {
            if entry.identity.is_some() {
                AgentEntry {
                    state: status.as_str().to_owned(),
                    stale: true,
                    ..entry
                }
            } else {
                AgentEntry::empty(entry.slot, status.as_str())
            }
        });
        let snapshot = ProjectionSnapshot {
            host_epoch: self.host_epoch.clone(),
            snapshot_revision: self.snapshot_revision,
            source_status: status,
            entries: entries.clone(),
        };
        self.last_entries = entries;
        self.last_projection_key = None;
        self.current = Some(snapshot.clone());
        snapshot
    }

    pub fn binding(&self, slot: usize) -> Option<Binding> {
        self.current.as_ref().and_then(|snapshot| snapshot.binding(slot))
    }

    pub fn complete_refresh_required(&self) -> bool {
        self.current.as_ref().is_none_or(|snapshot| {
            !snapshot.source_status.is_current() || snapshot.entries.iter().any(|entry| entry.stale)
        })
    }

    pub fn matches_current(&self, rows: &[Value]) -> Result<bool, ProjectionError> {
        let Some(snapshot) = &self.current else { return Ok(false) };
        if !snapshot.source_status.is_current() {
            return Ok(false);
        }
        let entries = self.project_entries(rows, &self.workspace_labels)?;
        Ok(self.last_projection_key.as_ref() == Some(&(entries, SourceStatus::Current)))
    }

    /// Normalize a complete live read for focus revalidation.  This does not
    /// commit a generation or change actionability.
    pub fn live_identity(&self, rows: &[Value], pane_id: &str) -> Result<Option<Identity>, ProjectionError> {
        let labels = &self.workspace_labels;
        let mut found = None;
        for value in rows {
            let row = InboxRow::from_value(value)?;
            if row.pane_id == pane_id {
                let entry = self.normalize(&row, labels)?;
                found = entry.identity;
                break;
            }
        }
        Ok(found)
    }

    fn project_entries(
        &self,
        rows: &[Value],
        labels: &BTreeMap<String, String>,
    ) -> Result<[AgentEntry; MAX_SLOTS], ProjectionError> {
        let mut normalized = rows
            .iter()
            .map(|value| InboxRow::from_value(value).and_then(|row| self.normalize(&row, labels)))
            .collect::<Result<Vec<_>, _>>()?;
        normalized.sort_by_key(|entry| (entry.rank.unwrap_or(99), std::cmp::Reverse(entry.state_change_seq)));
        normalized.truncate(MAX_SLOTS);
        let mut entries = normalized;
        while entries.len() < MAX_SLOTS {
            entries.push(AgentEntry::empty(entries.len(), "empty"));
        }
        let mut result: [AgentEntry; MAX_SLOTS] = entries.try_into().map_err(|_| ProjectionError::unavailable())?;
        for (slot, entry) in result.iter_mut().enumerate() {
            entry.slot = slot;
        }
        if let Some(current) = &self.current {
            for (candidate, committed) in result.iter_mut().zip(current.entries.iter()) {
                if candidate.identity.is_some() && committed.identity.is_some() && candidate.logical_eq(committed) {
                    if let (Some(identity), Some(previous)) = (&mut candidate.identity, &committed.identity) {
                        identity.source_revision = previous.source_revision;
                    }
                }
            }
        }
        Ok(result)
    }

    fn normalize(&self, row: &InboxRow, labels: &BTreeMap<String, String>) -> Result<AgentEntry, ProjectionError> {
        let tokens = row.tokens.as_object().ok_or_else(ProjectionError::unavailable)?;
        let rank = match tokens.get("rank").and_then(Value::as_str) {
            Some("0") => 0,
            Some("1") => 1,
            Some("2") => 2,
            Some("3") => 3,
            Some("4") => 4,
            Some("5") => 5,
            _ => return Err(ProjectionError::unavailable()),
        };
        let title_value = row
            .title
            .as_deref()
            .filter(|value| !value.is_empty())
            .or_else(|| tokens.get("title").and_then(Value::as_str))
            .or_else(|| row.agent.as_deref())
            .ok_or_else(ProjectionError::unavailable)?;
        let title: String = title_value.chars().filter(char::is_ascii).collect::<String>().trim().to_owned();
        let title = if title.is_empty() { "UNKNOWN AGENT".to_owned() } else { title };
        text(&title, "title", MAX_TEXT, false).map_err(|_| ProjectionError::unavailable())?;
        let discriminator = labels
            .get(&row.workspace_id)
            .cloned()
            .or_else(|| row.cwd.as_deref().and_then(repo_basename))
            .unwrap_or_else(|| "NO WORKSPACE".to_owned());
        text(&discriminator, "discriminator", MAX_DISCRIMINATOR, false)
            .map_err(|_| ProjectionError::unavailable())?;
        let since = tokens.get("since").and_then(Value::as_str).filter(|value| !value.is_empty()).unwrap_or("-");
        let age = tokens.get("age").and_then(Value::as_str).filter(|value| !value.is_empty()).unwrap_or("-");
        text(since, "since", 16, false).map_err(|_| ProjectionError::unavailable())?;
        text(age, "age", 16, false).map_err(|_| ProjectionError::unavailable())?;
        let identity = Identity {
            pane_id: row.pane_id.clone(),
            terminal_id: row.terminal_id.clone(),
            agent_session: session_token(&row.agent_session)?,
            source_revision: row.revision,
            workspace_id: row.workspace_id.clone(),
            tab_id: row.tab_id.clone(),
        };
        let state = ["blocked", "finished", "working", "idle", "unknown", "settled"][rank as usize].to_owned();
        Ok(AgentEntry {
            slot: usize::MAX,
            entry_id: row.pane_id.clone(),
            title,
            discriminator,
            since: since.to_owned(),
            age: age.to_owned(),
            state,
            rank: Some(rank),
            state_change_seq: row.state_change_seq,
            identity: Some(identity),
            stale: false,
        })
    }
}

fn workspace_labels(workspaces: &[Value]) -> BTreeMap<String, String> {
    let mut labels = BTreeMap::new();
    for workspace in workspaces {
        let Some(object) = workspace.as_object() else { continue };
        let Some(workspace_id) = object.get("workspace_id").and_then(Value::as_str) else { continue };
        if workspace_id.is_empty() { continue; }
        let label = object
            .get("label")
            .or_else(|| object.get("name"))
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty());
        if let Some(label) = label {
            let bounded: String = label.chars().filter(char::is_ascii).collect();
            if text(&bounded, "workspace label", MAX_DISCRIMINATOR, false).is_ok() {
                labels.insert(workspace_id.to_owned(), bounded);
            }
        }
    }
    labels
}

fn repo_basename(cwd: &str) -> Option<String> {
    let trimmed = cwd.trim_end_matches('/');
    let name = trimmed.rsplit('/').next().filter(|name| !name.is_empty() && *name != "." && *name != "..")?;
    let name: String = name.chars().filter(char::is_ascii).collect();
    text(&name, "repository", MAX_DISCRIMINATOR, false).ok().map(str::to_owned)
}
