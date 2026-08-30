use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

const PLUGIN_ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/..");
const VERIFIER: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../release/verify_bundle.py");
const LIFECYCLE: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../LIFECYCLE.md");
const SCHEMA: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../bundle/manifest.schema.json");
const REVISION: &str = "0123456789abcdef0123456789abcdef01234567";
const ARCHIVE_A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const ARCHIVE_B: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const LOCK_HASH: &str = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";

struct BundleFixture {
    root: PathBuf,
    binary_hash: String,
    binary_size: u64,
}

impl BundleFixture {
    fn new() -> Self {
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("herdr-keypad-release-bundle-{id}"));
        fs::create_dir_all(root.join("bin")).expect("create bundle fixture");
        fs::copy("/bin/true", root.join("bin/herdr-keypad")).expect("copy native test executable");
        fs::copy(
            Path::new(PLUGIN_ROOT).join("herdr-plugin.toml"),
            root.join("herdr-plugin.toml"),
        )
        .expect("copy plugin manifest");
        fs::copy(LIFECYCLE, root.join("LIFECYCLE.md")).expect("copy lifecycle document");
        let binary_hash = sha256(&root.join("bin/herdr-keypad"));
        let binary_size = fs::metadata(root.join("bin/herdr-keypad"))
            .expect("binary metadata")
            .len();
        let lifecycle_hash = sha256(&root.join("LIFECYCLE.md"));
        fs::write(
            root.join("release-manifest.json"),
            release_manifest(&binary_hash, binary_size, &lifecycle_hash),
        )
        .expect("write release manifest");
        Self {
            root,
            binary_hash,
            binary_size,
        }
    }

    fn verify(&self, target: &str) -> std::process::Output {
        Command::new("python3")
            .args([VERIFIER, "--bundle"])
            .arg(&self.root)
            .args(["--target", target, "--schema", SCHEMA])
            .output()
            .expect("run bundle verifier")
    }
}

impl Drop for BundleFixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn sha256(path: &Path) -> String {
    let output = Command::new("sha256sum")
        .arg(path)
        .output()
        .expect("sha256sum available for release tests");
    assert!(output.status.success());
    String::from_utf8(output.stdout)
        .expect("sha256sum output")
        .split_whitespace()
        .next()
        .expect("sha256sum digest")
        .to_owned()
}

fn release_manifest(binary_hash: &str, binary_size: u64, lifecycle_hash: &str) -> String {
    format!(
        r#"{{ 
  "schema_version": 1,
  "plugin": {{"id": "herdr-keypad", "version": "0.1.0"}},
  "bridge": {{"version": "0.1.0"}},
  "target": {{"triple": "x86_64-unknown-linux-gnu", "os": "linux", "arch": "x86_64"}},
  "compiler": {{"toolchain": "1.98.0", "rustc": "rustc 1.98.0", "cargo": "cargo 1.98.0"}},
  "source": {{
    "revision": "{REVISION}",
    "archives": [
      {{"root": "source-a", "sha256": "{ARCHIVE_A}"}},
      {{"root": "source-b", "sha256": "{ARCHIVE_B}"}}
    ]
  }},
  "cargo_lock": {{"sha256": "{LOCK_HASH}"}},
  "lifecycle": {{"path": "LIFECYCLE.md", "sha256": "{lifecycle_hash}"}},
  "binary": {{"path": "bin/herdr-keypad", "sha256": "{binary_hash}", "size": {binary_size}}},
  "reproducibility": {{"status": "passed", "hash_a": "{binary_hash}", "hash_b": "{binary_hash}", "equal": true}},
  "dependencies": {{"tool": "ldd", "status": "passed", "libraries": ["libc.so.6", "ld-linux-x86-64.so.2"]}},
  "tests": {{"status": "passed", "command": "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test release_bundle"}},
  "signing": {{"status": "not-run", "reason": "Unsigned CI artifact"}},
  "notarization": {{"status": "not-run", "reason": "Unsigned CI artifact"}}
}}"#
    )
}

fn assert_rejected(output: std::process::Output, expected: &str) {
    assert!(!output.status.success(), "verifier unexpectedly accepted bundle");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains(expected),
        "expected {expected:?} in verifier stderr, got {stderr}"
    );
}

#[test]
fn valid_linux_bundle_passes_closed_policy() {
    let fixture = BundleFixture::new();
    let output = fixture.verify("x86_64-unknown-linux-gnu");
    assert!(
        output.status.success(),
        "valid bundle rejected: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("verified"));
}

#[test]
fn wrong_target_is_rejected_before_archive_acceptance() {
    let fixture = BundleFixture::new();
    assert_rejected(fixture.verify("aarch64-apple-darwin"), "target");
}

#[test]
fn extra_runtime_source_fixture_or_evidence_file_is_rejected() {
    let fixture = BundleFixture::new();
    for (name, expected) in [
        ("python-runtime", "forbidden"),
        ("src/main.rs", "forbidden"),
        ("fixtures/input.json", "forbidden"),
        ("evidence/provenance.json", "forbidden"),
    ] {
        let path = fixture.root.join(name);
        fs::create_dir_all(path.parent().unwrap()).expect("create forbidden path parent");
        fs::write(&path, b"not part of a production plugin").expect("write forbidden path");
        assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), expected);
        if name.contains('/') {
            fs::remove_dir_all(path.parent().unwrap()).expect("remove forbidden path parent");
        } else {
            fs::remove_file(fixture.root.join(name)).expect("remove forbidden path");
        }
    }
}

#[test]
fn unresolved_manifest_argv_is_rejected() {
    let fixture = BundleFixture::new();
    let manifest = fs::read_to_string(fixture.root.join("herdr-plugin.toml")).expect("manifest");
    fs::write(
        fixture.root.join("herdr-plugin.toml"),
        manifest.replace("bin/herdr-keypad", "bin/missing-keypad"),
    )
    .expect("replace argv");
    assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), "argv");
}

#[test]
fn binary_hash_and_metadata_must_match() {
    let fixture = BundleFixture::new();
    let manifest_path = fixture.root.join("release-manifest.json");
    let manifest = fs::read_to_string(&manifest_path).expect("manifest");
    fs::write(
        &manifest_path,
        manifest
            .replace(&fixture.binary_hash, &"d".repeat(64))
            .replace(&fixture.binary_size.to_string(), "1"),
    )
    .expect("corrupt manifest evidence");
    assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), "hash");
}

#[test]
fn signing_and_notarization_must_not_claim_unrun_operations() {
    let fixture = BundleFixture::new();
    let manifest_path = fixture.root.join("release-manifest.json");
    let manifest = fs::read_to_string(&manifest_path).expect("manifest");
    fs::write(
        &manifest_path,
        manifest.replace("\"status\": \"not-run\"", "\"status\": \"passed\""),
    )
    .expect("claim signing evidence");
    assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), "signing");
}

#[test]
fn unknown_manifest_fields_are_rejected_by_closed_schema() {
    let fixture = BundleFixture::new();
    let manifest_path = fixture.root.join("release-manifest.json");
    let manifest = fs::read_to_string(&manifest_path).expect("manifest");
    fs::write(
        &manifest_path,
        manifest.replacen("\"schema_version\"", "\"unexpected\": true,\n  \"schema_version\"", 1),
    )
    .expect("add unknown field");
    assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), "schema");
}

#[test]
fn lifecycle_document_is_reopened_and_privacy_checked() {
    let fixture = BundleFixture::new();
    let lifecycle_path = fixture.root.join("LIFECYCLE.md");
    let lifecycle = fs::read_to_string(&lifecycle_path).expect("lifecycle");
    fs::write(&lifecycle_path, lifecycle.replace("HERDR_PLUGIN_ROOT", "/home/secret"))
        .expect("corrupt lifecycle");
    assert_rejected(fixture.verify("x86_64-unknown-linux-gnu"), "lifecycle");
}

#[test]
fn schema_file_is_present_and_bundle_manifest_is_closed() {
    assert!(Path::new(SCHEMA).is_file(), "manifest schema must be shipped");
    let schema = fs::read_to_string(SCHEMA).expect("manifest schema");
    assert!(schema.contains("additionalProperties"));
    assert!(schema.contains("not-run"));
}
