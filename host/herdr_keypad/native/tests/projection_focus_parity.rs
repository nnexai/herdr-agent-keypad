#[path = "../src/core/model.rs"]
mod model;
#[path = "../src/core/projection.rs"]
mod projection;
#[path = "../src/core/focus.rs"]
mod focus;

use focus::{FocusError, FocusExecutor, HerdrPort};
use model::{AgentEntry, FocusIntent, FocusStatus, Identity};
use projection::InboxProjection;
use serde_json::{json, Value};

fn fixture(name: &str) -> Value {
    let root: Value = serde_json::from_str(include_str!("fixtures/projection-focus.json")).unwrap();
    root["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == name)
        .unwrap_or_else(|| panic!("missing fixture {name}"))
        .clone()
}

fn row(pane: &str, rank: &str, sequence: u32) -> Value {
    json!({
        "pane_id": pane,
        "terminal_id": format!("term-{pane}"),
        "workspace_id": "workspace-1",
        "tab_id": format!("tab-{pane}"),
        "agent_status": "working",
        "focused": false,
        "revision": 1,
        "state_change_seq": sequence,
        "cwd": "repo",
        "title": "Title",
        "tokens": {"rank": rank, "title": "Plugin title"},
        "agent": "agent"
    })
}

fn workspace() -> Value {
    json!({"workspace_id": "workspace-1", "label": "repo"})
}

fn identity_view(identity: &Option<Identity>) -> Value {
    identity.as_ref().map_or(Value::Null, |identity| {
        json!({
            "pane_id": identity.pane_id,
            "terminal_id": identity.terminal_id,
            "agent_session": identity.agent_session,
            "source_revision": identity.source_revision,
            "workspace_id": identity.workspace_id,
            "tab_id": identity.tab_id
        })
    })
}

fn entry_view(entry: &AgentEntry) -> Value {
    json!({
        "slot": entry.slot,
        "entry_id": entry.entry_id,
        "title": entry.title,
        "discriminator": entry.discriminator,
        "since": entry.since,
        "age": entry.age,
        "state": entry.state,
        "rank": entry.rank,
        "state_change_seq": entry.state_change_seq,
        "stale": entry.stale,
        "identity": identity_view(&entry.identity)
    })
}

fn snapshot_view(snapshot: &model::ProjectionSnapshot) -> Value {
    json!({
        "host_epoch": snapshot.host_epoch,
        "snapshot_revision": snapshot.snapshot_revision,
        "source_status": snapshot.source_status.as_str(),
        "actionable": snapshot.actionable(),
        "entries": snapshot.entries.iter().map(entry_view).collect::<Vec<_>>()
    })
}

#[test]
fn projection_ordering_and_empty_slots_match_frozen_trace() {
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    let full = projection
        .refresh(&[row("p3", "2", 1), row("p1", "0", 2), row("p2", "1", 3)], &[workspace()])
        .unwrap();
    let partial = projection.refresh(&[row("p1", "0", 2)], &[workspace()]).unwrap();
    let expected = fixture("projection.order-full-and-empty-fill")["expected"].clone();
    assert_eq!(snapshot_view(&full), expected["full"]);
    assert_eq!(snapshot_view(&partial), expected["partial"]);
}

#[test]
fn equal_rank_uses_sequence_not_source_array_order() {
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    let first = projection.refresh(&[row("old", "2", 4), row("new", "2", 9)], &[workspace()]).unwrap();
    let reversed = projection.refresh(&[row("new", "2", 9), row("old", "2", 4)], &[workspace()]).unwrap();
    let expected = fixture("projection.rank-tie-state-sequence")["expected"].clone();
    assert_eq!(snapshot_view(&first), expected["first"]);
    assert_eq!(snapshot_view(&reversed), expected["reversed"]);
}

#[test]
fn malformed_rank_or_identity_fails_closed() {
    let mut missing_rank = row("missing-rank", "2", 1);
    missing_rank["tokens"].as_object_mut().unwrap().remove("rank");
    let mut projection = InboxProjection::new("epoch").unwrap();
    assert!(projection.refresh(&[missing_rank], &[]).is_err());
    let mut missing_identity = row("missing-identity", "2", 1);
    missing_identity.as_object_mut().unwrap().remove("terminal_id");
    assert!(projection.refresh(&[missing_identity], &[]).is_err());
}

#[test]
fn bounded_labels_prefer_workspace_and_never_emit_paths() {
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    let mut value = row("p1", "2", 1);
    value["title"] = Value::Null;
    value["cwd"] = Value::String("/home/me/repository".into());
    let snapshot = projection.refresh(&[value], &[workspace()]).unwrap();
    let expected = fixture("projection.bounded-title-discriminator")["expected"]["entry"].clone();
    assert_eq!(entry_view(&snapshot.entries[0]), expected);
    assert!(!snapshot.entries[0].discriminator.contains('/'));
}

#[test]
fn invalidation_preserves_identity_but_removes_actionability() {
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    let current = projection.refresh(&[row("p1", "2", 1)], &[workspace()]).unwrap();
    let stale = projection.invalidate("offline");
    let expected = fixture("projection.invalidation-preserves-stale-identity")["expected"].clone();
    assert_eq!(snapshot_view(&current), expected["before"]);
    assert_eq!(snapshot_view(&stale), expected["after"]);
    assert!(projection.binding(0).is_none());
    assert_eq!(stale.entries[0].identity, current.entries[0].identity);
}

#[test]
fn raw_revision_churn_does_not_advance_material_generation() {
    let mut projection = InboxProjection::new("epoch").unwrap();
    let initial = row("p1", "0", 1);
    let first = projection.refresh(std::slice::from_ref(&initial), &[]).unwrap();
    let mut revision_only = initial.clone();
    revision_only["revision"] = json!(99);
    let second = projection.refresh(std::slice::from_ref(&revision_only), &[]).unwrap();
    let mut material = revision_only;
    material["state_change_seq"] = json!(2);
    let third = projection.refresh(&[material], &[]).unwrap();
    let expected = fixture("projection.material-revision-rules")["expected"].clone();
    assert_eq!(first.snapshot_revision, second.snapshot_revision);
    assert_eq!(second.snapshot_revision, expected["revision_only"]);
    assert_eq!(third.snapshot_revision, expected["material"]);
    assert_eq!(second.entries[0].identity.as_ref().unwrap().source_revision, expected["source_revision"]);
}

#[test]
fn unavailable_source_is_not_current_or_actionable() {
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    let snapshot = projection.refresh_with_status(&[], &[], "unavailable").unwrap();
    let expected = fixture("projection.source-unavailable-is-not-empty-current")["expected"].clone();
    assert_eq!(snapshot_view(&snapshot), expected["snapshot"]);
    assert!(projection.binding(0).is_none());
}

#[derive(Debug)]
struct Spy {
    rows: Vec<Value>,
    responses: Vec<Result<Value, FocusError>>,
    calls: Vec<(String, Option<String>)>,
}

impl Spy {
    fn new(rows: Vec<Value>) -> Self { Self { rows, responses: Vec::new(), calls: Vec::new() } }
}

impl HerdrPort for Spy {
    fn complete_read(&mut self) -> Result<Vec<Value>, FocusError> {
        self.calls.push(("agent.list".into(), None));
        Ok(self.rows.clone())
    }

    fn focus(&mut self, pane: &str) -> Result<Value, FocusError> {
        self.calls.push(("agent.focus".into(), Some(pane.into())));
        if let Some(response) = self.responses.pop() { return response; }
        let mut agent = self.rows.iter().find(|row| row["pane_id"] == pane).cloned().unwrap();
        agent["focused"] = json!(true);
        Ok(json!({"type": "agent_info", "agent": agent}))
    }
}

fn focus_case(name: &str, spy: Spy, projection: &InboxProjection, intent: &FocusIntent) {
    let mut spy = spy;
    let result = FocusExecutor::new().execute(projection, intent, &mut spy);
    let expected = fixture(name)["expected"].clone();
    let calls = spy.calls.iter().map(|(method, target)| json!({"method": method, "target": target})).collect::<Vec<_>>();
    assert_eq!(calls, expected["calls"], "{name}");
    assert_eq!(result.status.as_str(), expected["status"], "{name}");
    assert_eq!(result.success(), expected["success"], "{name}");
}

#[test]
fn focus_policy_revalidates_exact_identity_and_allows_one_retry() {
    let rows = vec![row("p1", "2", 4)];
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    projection.refresh(&rows, &[workspace()]).unwrap();
    let binding = projection.binding(0).unwrap();
    let intent = FocusIntent::new("action-valid", binding.clone());
    focus_case("focus.accepted.exact-identity", Spy::new(rows.clone()), &projection, &intent);

    let mut retry = Spy::new(rows.clone());
    retry.responses.push(Ok(json!({"type": "agent_info", "agent": {"pane_id": "p1", "terminal_id": "term-p1", "workspace_id": "workspace-1", "tab_id": "tab-p1", "agent_session": null, "focused": true}})));
    retry.responses.push(Ok(json!({"type": "agent_info", "agent": {"pane_id": "p1", "terminal_id": "term-p1", "workspace_id": "workspace-1", "tab_id": "tab-p1", "agent_session": null, "focused": false}})));
    focus_case("focus.accepted.one-unfocused-retry", retry, &projection, &FocusIntent::new("action-retry", binding));
}

#[test]
fn focus_policy_maps_fences_and_failures_without_other_effects() {
    let rows = vec![row("p1", "2", 4)];
    let mut projection = InboxProjection::new("epoch-fixed").unwrap();
    projection.refresh(&rows, &[workspace()]).unwrap();
    let binding = projection.binding(0).unwrap();
    focus_case("focus.rejected.pane-reused", Spy::new(vec![{
        let mut reused = row("p1", "2", 4);
        reused["terminal_id"] = json!("different-terminal");
        reused
    }]), &projection, &FocusIntent::new("action-pane-reused", binding.clone()));

    projection.invalidate("stale");
    focus_case("focus.rejected.stale", Spy::new(rows.clone()), &projection, &FocusIntent::new("action-stale", binding.clone()));

    let mut fresh_projection = InboxProjection::new("epoch-fixed").unwrap();
    fresh_projection.refresh(&rows, &[workspace()]).unwrap();
    let fresh_binding = fresh_projection.binding(0).unwrap();
    focus_case("focus.rejected.vanished", Spy::new(vec![]), &fresh_projection, &FocusIntent::new("action-vanished", fresh_binding.clone()));

    let mut timeout = Spy::new(rows.clone());
    timeout.responses.push(Err(FocusError::timeout("timeout")));
    focus_case("focus.rejected.timeout-uncertain", timeout, &fresh_projection, &FocusIntent::new("action-timeout", fresh_binding.clone()));

    let mut malformed = Spy::new(rows.clone());
    malformed.responses.push(Ok(json!({"type": "error"})));
    focus_case("focus.rejected.malformed-ack", malformed, &fresh_projection, &FocusIntent::new("action-malformed", fresh_binding.clone()));

    let mut not_found = Spy::new(rows);
    not_found.responses.push(Err(FocusError::not_found("agent_not_found")));
    focus_case("focus.rejected.agent-not-found", not_found, &fresh_projection, &FocusIntent::new("action-not-found", fresh_binding));
}

#[test]
fn focus_status_enum_has_no_keyboard_or_generic_action_variant() {
    assert!(!FocusStatus::Accepted.as_str().contains("key"));
}
