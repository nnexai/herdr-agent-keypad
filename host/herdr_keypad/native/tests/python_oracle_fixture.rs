use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const FILES: [(&str, &str); 4] = [
    ("protocol.json", "protocol"),
    ("projection-focus.json", "projection-focus"),
    ("codex.json", "codex"),
    ("lifecycle.json", "lifecycle"),
];
const SOURCE_PATHS: [&str; 11] = [
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
    "protocol/fixtures/v2-golden.json",
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
    let digest = hasher.finalize();
    let mut encoded = String::with_capacity(64);
    for byte in digest.iter() {
        write!(&mut encoded, "{byte:02x}").expect("write SHA-256 hex");
    }
    encoded
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

const MAX_FILE_BYTES: usize = 1_048_576;
const MAX_CASES: usize = 256;
const MAX_SOURCES: usize = 32;
const MAX_CASE_BYTES: usize = 131_072;
const MAX_NAME_BYTES: usize = 128;
const MAX_SOURCE_PATH_BYTES: usize = 256;

fn validation_error(message: impl Into<String>) -> Result<(), String> {
    Err(message.into())
}

fn object<'a>(value: &'a Value, context: &str) -> Result<&'a Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| format!("{context} must be an object"))
}

fn exact_keys(
    value: &Map<String, Value>,
    expected: &[&str],
    context: &str,
) -> Result<(), String> {
    let actual: BTreeSet<&str> = value.keys().map(String::as_str).collect();
    let required: BTreeSet<&str> = expected.iter().copied().collect();
    if actual != required {
        return validation_error(format!("{context} has unknown or missing fields"));
    }
    Ok(())
}

fn bounded_string<'a>(
    value: &'a Value,
    maximum: usize,
    context: &str,
) -> Result<&'a str, String> {
    let text = value
        .as_str()
        .ok_or_else(|| format!("{context} must be a string"))?;
    if text.is_empty() || text.len() > maximum || !text.is_ascii() {
        return Err(format!("{context} is out of bounds"));
    }
    Ok(text)
}

fn hex_sha256<'a>(value: &'a Value, context: &str) -> Result<&'a str, String> {
    let text = bounded_string(value, 64, context)?;
    if text.len() != 64 || !text.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return Err(format!("{context} is not lowercase SHA-256"));
    }
    Ok(text)
}

fn path_shaped(text: &str) -> bool {
    text.starts_with('/')
        || text.starts_with('\\')
        || text.starts_with("~/")
        || text.starts_with("~\\")
        || text.starts_with("file://")
        || (text.len() >= 3
            && text.as_bytes()[0].is_ascii_alphabetic()
            && text.as_bytes()[1] == b':'
            && matches!(text.as_bytes()[2], b'/' | b'\\'))
}

fn sensitive_key(key: &str) -> bool {
    let lower = key.to_ascii_lowercase();
    [
        "token", "secret", "password", "email", "codexhome", "path", "prompt", "transcript",
        "stderr", "stdout",
    ]
    .iter()
    .any(|word| lower.contains(word))
}

fn validate_private_value(value: &Value, context: &str) -> Result<(), String> {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                if sensitive_key(key) {
                    return validation_error(format!("{context} contains sensitive key"));
                }
                validate_private_value(child, context)?;
            }
        }
        Value::Array(values) => {
            for child in values {
                validate_private_value(child, context)?;
            }
        }
        Value::String(text) if path_shaped(text) => {
            return validation_error(format!("{context} contains an absolute-path value"));
        }
        _ => {}
    }
    Ok(())
}

fn validate_protocol_types(value: &Value, context: &str) -> Result<(), String> {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                if key == "type" {
                    let kind = child
                        .as_str()
                        .ok_or_else(|| format!("{context}.type must be a string"))?;
                    if !protocol_types().contains(kind) {
                        return validation_error(format!("{context} contains an unapproved protocol type"));
                    }
                }
                validate_protocol_types(child, context)?;
            }
        }
        Value::Array(values) => {
            for child in values {
                validate_protocol_types(child, context)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn expected_family(filename: &str) -> Option<&'static str> {
    FILES.iter().find_map(|(name, family)| (*name == filename).then_some(*family))
}

fn validate_sources(value: &Value) -> Result<(), String> {
    let sources = value
        .as_array()
        .ok_or_else(|| "sources must be an array".to_string())?;
    if sources.is_empty() || sources.len() > MAX_SOURCES || sources.len() != SOURCE_PATHS.len() {
        return validation_error("sources count is outside the fixed lineage".to_string());
    }
    let root = repo_root();
    let mut seen = BTreeSet::new();
    for source in sources {
        let source = object(source, "source")?;
        exact_keys(source, &["kind", "path", "sha256"], "source")?;
        if bounded_string(&source["kind"], 32, "source.kind")? != "oracle-source" {
            return validation_error("source kind is not oracle-source".to_string());
        }
        let path = bounded_string(&source["path"], MAX_SOURCE_PATH_BYTES, "source.path")?;
        if path.starts_with('/')
            || path.starts_with('\\')
            || path.contains("..")
            || !seen.insert(path)
            || !expected_source_paths().contains(path)
        {
            return validation_error("source path is not an allowed relative source".to_string());
        }
        let actual = fs::read(root.join(path))
            .map_err(|_| format!("recorded source is missing: {path}"))?;
        let expected = hex_sha256(&source["sha256"], "source.sha256")?;
        if sha256_bytes(&actual) != expected {
            return validation_error(format!("recorded source hash mismatch: {path}"));
        }
    }
    if seen != expected_source_paths() {
        return validation_error("source lineage is incomplete".to_string());
    }
    Ok(())
}

fn validate_case(case: &Value, family: &str, names: &mut BTreeSet<String>) -> Result<(), String> {
    let case = object(case, "case")?;
    exact_keys(case, &["name", "input", "expected", "sha256"], "case")?;
    let name = bounded_string(&case["name"], MAX_NAME_BYTES, "case.name")?;
    if !names.insert(name.to_string()) {
        return validation_error("duplicate case name".to_string());
    }
    let body = json!({
        "name": name,
        "input": case["input"].clone(),
        "expected": case["expected"].clone(),
    });
    let expected_hash = hex_sha256(&case["sha256"], "case.sha256")?;
    if sha256_bytes(&canonical_bytes(&body)) != expected_hash {
        return validation_error(format!("case hash mismatch in {family}: {name}"));
    }
    validate_private_value(&case["input"], "case.input")?;
    validate_private_value(&case["expected"], "case.expected")?;
    if family == "protocol" {
        validate_protocol_types(&case["input"], "case.input")?;
        validate_protocol_types(&case["expected"], "case.expected")?;
    }
    Ok(())
}

fn validate_fixture_file(path: &Path, family: &str, names: &mut BTreeSet<String>) -> Result<(), String> {
    let bytes = fs::read(path).map_err(|_| format!("missing fixture: {}", path.display()))?;
    if bytes.is_empty() || bytes.len() > MAX_FILE_BYTES {
        return validation_error(format!("fixture exceeds byte bound: {}", path.display()));
    }
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|_| format!("fixture is not valid JSON: {}", path.display()))?;
    let root = object(&value, "fixture")?;
    exact_keys(root, &["schema_version", "family", "sources", "cases", "fixture_sha256"], "fixture")?;
    if root["schema_version"].as_u64() != Some(1) {
        return validation_error("unsupported fixture schema version".to_string());
    }
    if bounded_string(&root["family"], 32, "fixture.family")? != family {
        return validation_error("fixture family does not match filename".to_string());
    }
    validate_sources(&root["sources"])?;
    let cases = root["cases"].as_array().ok_or_else(|| "cases must be an array".to_string())?;
    if cases.is_empty() || cases.len() > MAX_CASES {
        return validation_error("case count exceeds explicit bound".to_string());
    }
    for item in cases {
        if canonical_bytes(item).len() > MAX_CASE_BYTES {
            return validation_error("case exceeds explicit byte bound".to_string());
        }
        validate_case(item, family, names)?;
    }
    let mut without_digest = root.clone();
    without_digest.remove("fixture_sha256");
    let expected_digest = hex_sha256(&root["fixture_sha256"], "fixture_sha256")?;
    if sha256_bytes(&canonical_bytes(&Value::Object(without_digest))) != expected_digest {
        return validation_error("fixture hash mismatch".to_string());
    }
    Ok(())
}

fn validate_fixture_root(root: &Path) -> Result<(), String> {
    if !root.is_dir() {
        return validation_error("fixture root is not a directory".to_string());
    }
    let expected_files: BTreeSet<String> = FILES.iter().map(|(name, _)| (*name).to_string()).collect();
    let mut actual_files = BTreeSet::new();
    for entry in fs::read_dir(root).map_err(|_| "cannot read fixture root".to_string())? {
        let entry = entry.map_err(|_| "cannot inspect fixture root".to_string())?;
        let file_type = entry.file_type().map_err(|_| "cannot inspect fixture entry".to_string())?;
        if !file_type.is_file() {
            return validation_error("fixture root contains a non-file entry".to_string());
        }
        let name = entry.file_name().to_string_lossy().into_owned();
        if !actual_files.insert(name) {
            return validation_error("duplicate fixture filename".to_string());
        }
    }
    if actual_files != expected_files {
        return validation_error("fixture root file set is not exactly the closed four-file set".to_string());
    }
    let mut names = BTreeSet::new();
    for filename in expected_files {
        let family = expected_family(&filename).expect("closed fixture filename");
        validate_fixture_file(&root.join(filename), family, &mut names)?;
    }
    Ok(())
}

fn expected_source_paths() -> BTreeSet<&'static str> {
    SOURCE_PATHS.into_iter().collect()
}

fn protocol_types() -> BTreeSet<&'static str> {
    PROTOCOL_TYPES.into_iter().collect()
}
