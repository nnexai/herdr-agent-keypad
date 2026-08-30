use herdr_keypad_native::core::model::{AgentEntry, Identity, ProjectionSnapshot};
use herdr_keypad_native::core::projection::InboxProjection;
use herdr_keypad_native::protocol::v2::{self, ProtocolSession};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

const FIXTURE_ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures");
const ORACLE_EXPORTER: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../tests/export_rust_oracle.py");
const FAMILIES: [(&str, &str); 4] = [
    ("protocol.json", "protocol"),
    ("projection-focus.json", "projection-focus"),
    ("codex.json", "codex"),
    ("lifecycle.json", "lifecycle"),
];

fn fixture(name: &str) -> Value {
    let path = Path::new(FIXTURE_ROOT).join(name);
    serde_json::from_str(&fs::read_to_string(path).expect("fixture is readable")).expect("fixture JSON")
}

fn canonical(value: &Value) -> Value {
    match value {
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(key, value)| (key.clone(), canonical(value)))
                .collect::<std::collections::BTreeMap<_, _>>()
                .into_iter()
                .collect(),
        ),
        Value::Array(values) => Value::Array(values.iter().map(canonical).collect()),
        other => other.clone(),
    }
}

fn sha256_json(value: &Value) -> String {
    let bytes = serde_json::to_vec(&canonical(value)).expect("canonical JSON");
    Sha256::digest(bytes).iter().map(|byte| format!("{byte:02x}")).collect()
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

fn snapshot_view(snapshot: &ProjectionSnapshot) -> Value {
    json!({
        "host_epoch": snapshot.host_epoch,
        "snapshot_revision": snapshot.snapshot_revision,
        "source_status": snapshot.source_status.as_str(),
        "actionable": snapshot.actionable(),
        "entries": snapshot.entries.iter().map(entry_view).collect::<Vec<_>>()
    })
}

fn protocol_input(root: &Value, case: &Value) -> Vec<u8> {
    let input = &case["input"];
    if let Some(length) = input.get("line_bytes").and_then(Value::as_u64) {
        let source_case = root["cases"]
            .as_array()
            .expect("protocol cases")
            .iter()
            .find(|candidate| candidate["name"] == "protocol.accepted.agent_snapshot")
            .expect("snapshot source fixture");
        let source = source_case["input"]["line"].as_str().expect("source line").as_bytes();
        let mut line = source[..source.len() - 1].to_vec();
        line.resize(length as usize - 1, b' ');
        line.push(b'\n');
        return line;
    }
    input["line"].as_str().expect("line case").as_bytes().to_vec()
}

#[test]
fn every_frozen_fixture_has_a_valid_content_hash_and_closed_family() {
    let mut names = std::collections::BTreeSet::new();
    for (filename, family) in FAMILIES {
        let root = fixture(filename);
        assert_eq!(root["family"], family, "family marker for {filename}");
        assert_eq!(root["schema_version"], 1, "schema version for {filename}");
        let body = json!({
            "schema_version": root["schema_version"],
            "family": root["family"],
            "sources": root["sources"],
            "cases": root["cases"]
        });
        assert_eq!(sha256_json(&body), root["fixture_sha256"], "fixture hash for {filename}");
        for case in root["cases"].as_array().expect("cases array") {
            let name = case["name"].as_str().expect("case name");
            assert!(names.insert(name.to_owned()), "duplicate frozen case {name}");
            let case_body = json!({"name": case["name"], "input": case["input"], "expected": case["expected"]});
            assert_eq!(sha256_json(&case_body), case["sha256"], "case hash for {name}");
        }
    }
    assert!(names.len() >= 40, "the parity corpus must remain substantive");
}

#[test]
fn python_oracle_export_is_byte_identical_to_checked_in_corpus() {
    let root = std::env::temp_dir().join(format!(
        "herdr-keypad-oracle-{}-{}",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH).expect("clock").as_nanos()
    ));
    fs::create_dir_all(&root).expect("oracle output directory");
    let output = Command::new("python3")
        .arg(ORACLE_EXPORTER)
        .arg("--output-root")
        .arg(&root)
        .output()
        .expect("python3 oracle process");
    assert!(output.status.success(), "oracle failed: {}", String::from_utf8_lossy(&output.stderr));
    for (filename, _) in FAMILIES {
        let generated = fs::read(root.join(filename)).expect("generated fixture");
        let checked_in = fs::read(Path::new(FIXTURE_ROOT).join(filename)).expect("checked-in fixture");
        assert_eq!(generated, checked_in, "oracle output drifted for {filename}");
    }
    fs::remove_dir_all(root).expect("oracle cleanup");
}

#[test]
fn every_protocol_trace_matches_public_rust_admission_contract() {
    let root = fixture("protocol.json");
    for case in root["cases"].as_array().expect("protocol cases") {
        if case["input"]["kind"] == "session" {
            continue;
        }
        let result = v2::classify_line(&protocol_input(&root, case));
        assert_eq!(result.accepted, case["expected"]["accepted"], "accepted: {}", case["name"]);
        assert_eq!(result.dispatched, case["expected"]["dispatch"], "dispatch: {}", case["name"]);
        assert_eq!(result.reason, case["expected"]["reason"], "reason: {}", case["name"]);
        if case["expected"]["accepted"] == true {
            assert!(result.frame.is_some(), "accepted trace carries a frame: {}", case["name"]);
        }
    }
}

#[test]
fn session_trace_fences_duplicate_stale_and_foreign_authority() {
    let root = fixture("protocol.json");
    let focus_line = root["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.focus_intent")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();
    let mut session = ProtocolSession::new("boot-a", "session-a", 16).expect("session");
    for (index, expected) in [(1, "ok"), (1, "duplicate"), (2, "ok"), (1, "duplicate")] {
        let mut frame: Value = serde_json::from_str(focus_line).expect("focus frame");
        frame["seq"] = json!(index);
        let line = serde_json::to_vec(&frame).expect("frame");
        let mut line = line;
        line.push(b'\n');
        assert_eq!(session.accept(&line).reason, expected);
    }
    let foreign = focus_line.replace("session-a", "session-foreign");
    assert_eq!(session.accept(foreign.as_bytes()).reason, "session_mismatch");
    assert!(session.pending_count() <= v2::SESSION_CAPACITY);
    session.reset("boot-b", "session-b").expect("fresh authority");
    assert_eq!(session.pending_count(), 0);
}

#[test]
fn projection_traces_match_python_observable_views() {
    let expected = fixture("projection-focus.json");
    let mut projection = InboxProjection::new("epoch-fixed").expect("projection");
    let full = projection
        .refresh(&[row("p3", "2", 1), row("p1", "0", 2), row("p2", "1", 3)], &[workspace()])
        .expect("full projection");
    assert_eq!(snapshot_view(&full), expected_case(&expected, "projection.order-full-and-empty-fill")["expected"]["full"]);
    let partial = projection.refresh(&[row("p1", "0", 2)], &[workspace()]).expect("partial projection");
    assert_eq!(snapshot_view(&partial), expected_case(&expected, "projection.order-full-and-empty-fill")["expected"]["partial"]);

    let mut tied = InboxProjection::new("epoch-fixed").expect("projection");
    let first = tied.refresh(&[row("old", "2", 4), row("new", "2", 9)], &[workspace()]).expect("rank tie");
    let reversed = tied.refresh(&[row("new", "2", 9), row("old", "2", 4)], &[workspace()]).expect("reversed tie");
    let expected = expected_case(&expected, "projection.rank-tie-state-sequence")["expected"].clone();
    assert_eq!(snapshot_view(&first), expected["first"]);
    assert_eq!(snapshot_view(&reversed), expected["reversed"]);
}

fn expected_case(root: &Value, name: &str) -> Value {
    root["cases"]
        .as_array()
        .expect("cases")
        .iter()
        .find(|case| case["name"] == name)
        .unwrap_or_else(|| panic!("missing fixture case {name}"))
        .clone()
}

#[test]
fn projection_fail_closed_and_invalidation_match_frozen_statuses() {
    let root = fixture("projection-focus.json");
    let mut projection = InboxProjection::new("epoch-fixed").expect("projection");
    let mut missing_rank = row("missing-rank", "2", 1);
    missing_rank["tokens"].as_object_mut().unwrap().remove("rank");
    assert!(projection.refresh(&[missing_rank], &[]).is_err());
    let mut missing_identity = row("missing-identity", "2", 1);
    missing_identity.as_object_mut().unwrap().remove("terminal_id");
    assert!(projection.refresh(&[missing_identity], &[]).is_err());

    let current = projection.refresh(&[row("p1", "2", 1)], &[workspace()]).expect("current");
    let stale = projection.invalidate("offline");
    let expected = expected_case(&root, "projection.invalidation-preserves-stale-identity")["expected"].clone();
    assert_eq!(snapshot_view(&current), expected["before"]);
    assert_eq!(snapshot_view(&stale), expected["after"]);
    assert!(!stale.actionable());
    assert!(projection.binding(0).is_none());
}

#[test]
fn bounded_payload_and_nesting_adversaries_fail_closed_without_panics() {
    let oversized = vec![b' '; v2::MAX_LINE_BYTES + 1];
    assert_eq!(v2::classify_line(&oversized).reason, "line_too_long");
    assert_eq!(v2::classify_line(b"{\"v\":2}\n").reason, "invalid_shape");
    let nested = format!("{}\n", "[".repeat(v2::MAX_JSON_NESTING + 3) + &"]".repeat(v2::MAX_JSON_NESTING + 3));
    assert!(matches!(v2::classify_line(nested.as_bytes()).reason, "invalid_json" | "nesting_too_deep"));
}

#[allow(dead_code)]
fn _repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}
