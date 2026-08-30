#[path = "../src/protocol/v2.rs"]
mod v2;

use serde_json::Value;

fn fixture(name: &str) -> Value {
    let root: Value = serde_json::from_str(include_str!("fixtures/protocol.json")).unwrap();
    root["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == name)
        .unwrap_or_else(|| panic!("missing fixture {name}"))
        .clone()
}

fn classify_case(case: &Value) -> v2::ProtocolResult {
    let input = &case["input"];
    if let Some(line_bytes) = input.get("line_bytes").and_then(Value::as_u64) {
        return v2::classify_line(&vec![b'x'; line_bytes as usize]);
    }
    let line = input["line"].as_str().expect("line fixture");
    v2::classify_line(line.as_bytes())
}

#[test]
fn committed_protocol_corpus_matches_rust_admission() {
    let root: Value = serde_json::from_str(include_str!("fixtures/protocol.json")).unwrap();
    for case in root["cases"].as_array().unwrap() {
        if case["input"]["kind"] != "classify" {
            continue;
        }
        let result = classify_case(case);
        let expected = &case["expected"];
        assert_eq!(result.accepted, expected["accepted"], "{}", case["name"]);
        assert_eq!(result.reason, expected["reason"].as_str().unwrap(), "{}", case["name"]);
        assert_eq!(result.dispatched, expected["dispatch"], "{}", case["name"]);
    }
}

#[test]
fn canonical_root_golden_vectors_remain_accepted_or_rejected_identically() {
    let root: Value = serde_json::from_str(include_str!("../../../../../protocol/fixtures/v2-golden.json")).unwrap();
    assert_eq!(root["schema_version"], 2);
    for vector in root["vectors"].as_array().unwrap() {
        let result = v2::classify_line(vector["line"].as_str().unwrap().as_bytes());
        let expected = &vector["expected"];
        assert_eq!(result.accepted, expected["schema"] == "valid", "{}", vector["id"]);
        assert_eq!(result.reason, expected["reason"].as_str().unwrap(), "{}", vector["id"]);
        assert_eq!(result.dispatched, expected["dispatch"], "{}", vector["id"]);
    }
}

#[test]
fn session_rejects_stale_duplicate_and_queue_overflow_then_resets_authority() {
    let committed: Value = serde_json::from_str(include_str!("fixtures/protocol.json")).unwrap();
    let snapshot = committed["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.agent_snapshot")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();
    let ack = committed["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.snapshot_ack")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();

    let mut session = v2::ProtocolSession::new("boot-a", "session-a", 16).unwrap();
    assert_eq!(session.accept(snapshot.as_bytes()).reason, "ok");
    assert_eq!(session.accept(snapshot.as_bytes()).reason, "duplicate");
    assert_eq!(session.accept(ack.as_bytes()).reason, "ok");
    assert_eq!(session.accept(snapshot.as_bytes()).reason, "duplicate");
    assert_eq!(session.pending_count(), 2);

    let wrong_session = snapshot.replace("session-a", "other-session");
    assert_eq!(session.accept(wrong_session.as_bytes()).reason, "session_mismatch");

    session.reset("boot-b", "session-b").unwrap();
    assert_eq!(session.pending_count(), 0);
    assert_eq!(session.accept(snapshot.as_bytes()).reason, "boot_mismatch");

    let mut fresh = serde_json::from_str::<Value>(snapshot).unwrap();
    fresh["boot_id"] = Value::String("boot-b".into());
    fresh["session_id"] = Value::String("session-b".into());
    for sequence in 1..=16u64 {
        fresh["seq"] = Value::Number(sequence.into());
        let line = serde_json::to_string(&fresh).unwrap() + "\n";
        assert_eq!(session.accept(line.as_bytes()).reason, "ok", "seq {sequence}");
    }
    fresh["seq"] = Value::Number(17.into());
    let overflow = serde_json::to_string(&fresh).unwrap() + "\n";
    assert_eq!(session.accept(overflow.as_bytes()).reason, "queue_full");
    assert_eq!(session.pending_count(), 16);
    assert!(session.complete());
    assert_eq!(session.pending_count(), 15);
    session.discard_pending();
    assert_eq!(session.pending_count(), 0);
}

#[test]
fn typed_codec_preserves_nullability_and_canonical_digest() {
    let committed: Value = serde_json::from_str(include_str!("fixtures/protocol.json")).unwrap();
    let line = committed["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.null-versus-zero")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();
    let frame = v2::ProtocolFrame::decode_line(line.as_bytes()).unwrap();
    let encoded = frame.encode_line().unwrap();
    assert_eq!(encoded, line.as_bytes());
    let snapshot = frame.as_agent_snapshot().unwrap();
    assert_eq!(snapshot.codex.primary, Some(0));
    assert_eq!(snapshot.codex.secondary, Some(0));
    assert_eq!(snapshot.codex.reached_limit, Some(false));
}
