use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const FILES: [(&str, &str); 4] = [
    ("protocol.json", "protocol"),
    ("projection-focus.json", "projection-focus"),
    ("codex.json", "codex"),
    ("lifecycle.json", "lifecycle"),
];
const SOURCE_PATHS: [&str; 10] = [
    "host/herdr_keypad/src/herdr_keypad/bridge.py",
    "host/herdr_keypad/src/herdr_keypad/projection.py",
    "host/herdr_keypad/src/herdr_keypad/focus.py",
    "host/herdr_keypad/src/herdr_keypad/codex.py",
    "host/herdr_keypad/tests/test_protocol.py",
    "host/herdr_keypad/tests/test_projection.py",
    "host/herdr_keypad/tests/test_focus.py",
    "host/herdr_keypad/tests/test_codex.py",
    "host/herdr_keypad/tests/test_integration.py",
    "protocol/schema/v2.json",
];
const PROTOCOL_TYPES: [&str; 4] = [
    "agent_snapshot",
    "snapshot_ack",
    "focus_intent",
    "focus_result",
];

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn canonical(value: &Value) -> Value {
    match value {
        Value::Object(object) => {
            let sorted: BTreeMap<String, Value> = object
                .iter()
                .map(|(key, child)| (key.clone(), canonical(child)))
                .collect();
            Value::Object(sorted.into_iter().collect())
        }
        Value::Array(values) => Value::Array(values.iter().map(canonical).collect()),
        _ => value.clone(),
    }
}

fn canonical_bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(&canonical(value)).expect("canonical JSON")
}

fn source_records() -> Vec<Value> {
    let root = repo_root();
    SOURCE_PATHS
        .iter()
        .map(|path| {
            let bytes = fs::read(root.join(path)).expect("source fixture input");
            json!({
                "kind": "oracle-source",
                "path": path,
                "sha256": sha256_bytes(&bytes),
            })
        })
        .collect()
}

fn case(name: &str, input: Value, expected: Value) -> Value {
    let body = json!({"name": name, "input": input, "expected": expected});
    let mut record = body.as_object().expect("case object").clone();
    record.insert("sha256".into(), Value::String(sha256_bytes(&canonical_bytes(&body))));
    Value::Object(record)
}

fn corpus(family: &str) -> Value {
    let input = json!({"kind": "synthetic", "type": "agent_snapshot"});
    let expected = json!({"accepted": true, "reason": "ok"});
    let cases = match family {
        "protocol" => vec![case("protocol.synthetic", input, expected)],
        _ => vec![case(
            &format!("{family}.synthetic"),
            json!({"kind": "synthetic"}),
            json!({"status": "ok"}),
        )],
    };
    let mut root = json!({
        "schema_version": 1,
        "family": family,
        "sources": source_records(),
        "cases": cases,
    });
    let digest = sha256_bytes(&canonical_bytes(&root));
    root.as_object_mut()
        .expect("corpus object")
        .insert("fixture_sha256".into(), Value::String(digest));
    root
}

fn unique_temp_root(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let root = env::temp_dir().join(format!("herdr-oracle-{label}-{}-{nanos}", std::process::id()));
    fs::create_dir_all(&root).expect("temporary fixture root");
    root
}

fn write_root(root: &Path) {
    for (filename, family) in FILES {
        let bytes = serde_json::to_vec_pretty(&corpus(family)).expect("synthetic corpus JSON");
        fs::write(root.join(filename), bytes).expect("synthetic corpus file");
    }
}

fn remove_root(root: &Path) {
    let _ = fs::remove_dir_all(root);
}

#[test]
fn synthetic_valid_corpus_passes() {
    let root = unique_temp_root("valid");
    write_root(&root);
    assert!(validate_fixture_root(&root).is_ok());
    remove_root(&root);
}

#[test]
fn synthetic_environment_root_passes() {
    let Some(root) = env::var_os("HERDR_ORACLE_FIXTURE_ROOT") else {
        return;
    };
    validate_fixture_root(Path::new(&root)).expect("exported oracle corpus");
}

#[test]
fn synthetic_tampered_corpora_fail_closed() {
    let mutations: [(&str, fn(&mut PathBuf)); 7] = [
        ("duplicate case names", tamper_duplicate_case_names),
        ("unknown field", tamper_unknown_field),
        ("oversized records", tamper_oversized_records),
        ("sensitive key", tamper_sensitive_key),
        ("absolute path", tamper_absolute_path),
        ("missing parity family", tamper_missing_family),
        ("fifth protocol type", tamper_protocol_expansion),
    ];
    for (label, mutate) in mutations {
        let root = unique_temp_root("tampered");
        write_root(&root);
        mutate(&mut root.clone());
        // Mutators currently write directly through their path argument.
        assert!(validate_fixture_root(&root).is_err(), "{label}");
        remove_root(&root);
    }
}

fn rewrite(root: &Path, filename: &str, mut edit: impl FnMut(&mut Value)) {
    let path = root.join(filename);
    let mut value: Value = serde_json::from_slice(&fs::read(&path).expect("fixture"))
        .expect("fixture JSON");
    edit(&mut value);
    fs::write(path, serde_json::to_vec_pretty(&value).expect("fixture JSON")).expect("rewrite fixture");
}

fn tamper_duplicate_case_names(root: &mut PathBuf) {
    rewrite(root, "protocol.json", |value| {
        let cases = value["cases"].as_array_mut().expect("cases");
        let duplicate = cases[0].clone();
        cases.push(duplicate);
    });
}

fn tamper_unknown_field(root: &mut PathBuf) {
    rewrite(root, "codex.json", |value| {
        value.as_object_mut().expect("root").insert("extra".into(), json!(true));
    });
}

fn tamper_oversized_records(root: &mut PathBuf) {
    rewrite(root, "lifecycle.json", |value| {
        let cases = value["cases"].as_array_mut().expect("cases");
        for index in 0..257 {
            cases.push(case(
                &format!("oversized-{index}"),
                json!({"kind": "synthetic"}),
                json!({"status": "ok"}),
            ));
        }
    });
}

fn tamper_sensitive_key(root: &mut PathBuf) {
    rewrite(root, "projection-focus.json", |value| {
        value["cases"][0]["input"] = json!({"nested": {"token": "secret"}});
    });
}

fn tamper_absolute_path(root: &mut PathBuf) {
    rewrite(root, "projection-focus.json", |value| {
        value["cases"][0]["input"] = json!({"cwd": "/home/private/repo"});
    });
}

fn tamper_missing_family(root: &mut PathBuf) {
    fs::remove_file(root.join("codex.json")).expect("remove fixture");
}

fn tamper_protocol_expansion(root: &mut PathBuf) {
    rewrite(root, "protocol.json", |value| {
        value["cases"][0]["input"]["type"] = json!("hold_intent");
    });
}

// Implemented in the GREEN step below. Keeping the validator behind this
// function makes the synthetic corpus tests independent from the exporter.
fn validate_fixture_root(_root: &Path) -> Result<(), String> {
    Err("validator not implemented".into())
}

#[allow(dead_code)]
fn expected_source_paths() -> BTreeSet<&'static str> {
    SOURCE_PATHS.into_iter().collect()
}

#[allow(dead_code)]
fn protocol_types() -> BTreeSet<&'static str> {
    PROTOCOL_TYPES.into_iter().collect()
}

#[allow(dead_code)]
fn _keep_map_import() -> Map<String, Value> {
    Map::new()
}
