#![allow(dead_code)]

#[path = "../src/ports/config.rs"]
mod config;
#[path = "../src/ports/status.rs"]
mod status;
#[path = "../src/ports/logging.rs"]
mod logging;
#[path = "../src/ports/lifecycle.rs"]
mod lifecycle;
#[path = "../src/ports/control.rs"]
mod control;

use config::StartupConfig;
use control::{AuthorityLock, ControlReply, ControlRequest, CONTROL_PAYLOAD_LIMIT};
use lifecycle::{LifecycleCommand, LifecycleOwner, RuntimePaths};
use logging::{SafeLogger, TraceConfig};
use status::{BridgeStatus, SafeCode, StatusSnapshot, TransitionRing, STATUS_PAYLOAD_LIMIT};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

fn temp_dir(label: &str) -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let path = std::env::temp_dir().join(format!("herdr-keypad-{label}-{}-{stamp}", std::process::id()));
    fs::create_dir_all(&path).expect("temp dir");
    path
}

fn binding_file(root: &Path) -> PathBuf {
    let path = root.join("keypad-binding.json");
    fs::write(
        &path,
        br#"{"schema_version":1,"device_id":"kbd-123","protocol":1,"firmware":"phase1-bringup"}"#,
    )
    .expect("binding");
    path
}

#[test]
fn lifecycle_control_matching_start_is_idempotent_and_changed_config_requires_restart() {
    let root = temp_dir("lifecycle");
    let config_dir = root.join("config");
    let state_dir = root.join("state");
    fs::create_dir_all(&config_dir).expect("config");
    let binding = binding_file(&root);
    fs::write(config_dir.join("config.toml"), "logging_enabled = false\n").expect("settings");
    let startup = StartupConfig::load(&config_dir, &binding);
    assert!(startup.binding.is_some(), "valid binding remains available");
    let paths = RuntimePaths::new(&config_dir, &state_dir, "/tmp/herdr.sock", "/bin/herdr", 77);
    let mut owner = LifecycleOwner::new(paths, startup.effective.clone()).expect("owner");

    assert_eq!(owner.handle(LifecycleCommand::Start), ControlReply::Active {
        version: env!("CARGO_PKG_VERSION").to_owned(),
        config_identity: startup.effective.identity().to_owned(),
    });
    assert_eq!(owner.start_with_config(startup.effective.clone()), ControlReply::Active {
        version: env!("CARGO_PKG_VERSION").to_owned(),
        config_identity: startup.effective.identity().to_owned(),
    });

    let mut changed = startup.effective.clone();
    changed.logging_enabled = true;
    assert_eq!(owner.start_with_config(changed), ControlReply::RestartRequired {
        active_config_identity: startup.effective.identity().to_owned(),
        requested_config_identity: owner.requested_identity_for_test(true),
    });
    let changed_identity = owner.requested_identity_for_test(true);
    assert_eq!(owner.handle(LifecycleCommand::Restart), ControlReply::Restarted {
        version: env!("CARGO_PKG_VERSION").to_owned(),
        config_identity: changed_identity,
    });

    owner.handle(LifecycleCommand::Stop);
    assert_eq!(owner.status().state, BridgeStatus::Stopped);
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn lifecycle_exits_on_herdr_boundary_and_never_restarts_after_crash() {
    let root = temp_dir("exit");
    let binding = binding_file(&root);
    let config_dir = root.join("config");
    let state_dir = root.join("state");
    fs::create_dir_all(&config_dir).expect("config");
    let startup = StartupConfig::load(&config_dir, &binding);
    let paths = RuntimePaths::new(&config_dir, &state_dir, "/tmp/herdr.sock", "/bin/herdr", 7);
    let mut owner = LifecycleOwner::new(paths, startup.effective).expect("owner");
    assert_eq!(owner.handle(LifecycleCommand::Start).state(), BridgeStatus::Running);
    owner.on_herdr_exit();
    assert_eq!(owner.status().state, BridgeStatus::Stopped);
    assert!(!owner.automatic_recovery(), "Herdr v0.8.2 supplies no supervisor");
    owner.on_process_crash();
    assert_eq!(owner.status().state, BridgeStatus::Stopped);
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn lifecycle_suspend_invalidates_sessions_until_fresh_resume() {
    let root = temp_dir("suspend");
    let binding = binding_file(&root);
    let config_dir = root.join("config");
    let state_dir = root.join("state");
    let startup = StartupConfig::load(&config_dir, &binding);
    let paths = RuntimePaths::new(&config_dir, &state_dir, "/tmp/herdr.sock", "/bin/herdr", 7);
    let mut owner = LifecycleOwner::new(paths, startup.effective).expect("owner");
    owner.handle(LifecycleCommand::Start);
    let before = owner.session_epoch();
    owner.on_suspend();
    assert!(!owner.sessions_valid());
    owner.on_resume();
    assert!(owner.sessions_valid());
    assert!(owner.session_epoch() > before);
    fs::remove_dir_all(root).expect("cleanup");
}

#[tokio::test]
async fn lifecycle_control_lock_cleans_stale_endpoint_only_after_authority_is_owned() {
    let root = temp_dir("lock");
    let state = root.join("state");
    fs::create_dir_all(&state).expect("state");
    let socket = state.join("bridge.sock");
    fs::write(&socket, b"stale").expect("stale endpoint");
    let authority = AuthorityLock::acquire(&state).expect("authority");
    assert!(!socket.exists(), "stale endpoint is removed after lock acquisition");
    assert!(AuthorityLock::acquire(&state).is_err(), "lock, not endpoint, proves authority");
    let endpoint = authority.bind_control().await.expect("control endpoint");
    assert_eq!(endpoint.path(), socket);
    assert!(socket.exists(), "authority binds its control endpoint");
    drop(authority);
    assert!(!socket.exists(), "authority drop invalidates its control endpoint");
    drop(endpoint);
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn lifecycle_control_protocol_is_versioned_bounded_and_rejects_oversize_before_parse() {
    let request = ControlRequest::status();
    let bytes = request.encode().expect("encode");
    assert!(bytes.len() <= CONTROL_PAYLOAD_LIMIT);
    assert_eq!(ControlRequest::decode(&bytes).expect("decode"), request);
    let oversized = vec![b' '; CONTROL_PAYLOAD_LIMIT + 1];
    assert!(ControlRequest::decode(&oversized).is_err());
    assert!(ControlReply::active("v", "cfg").encode().expect("reply").len() <= CONTROL_PAYLOAD_LIMIT);
    assert!(ControlRequest::decode(br#"{"request":"status","version":1,"version":1}"#).is_err());
}

#[test]
fn lifecycle_config_malformed_settings_and_binding_fail_closed_without_rewriting_files() {
    let root = temp_dir("invalid");
    let config_dir = root.join("config");
    fs::create_dir_all(&config_dir).expect("config");
    let binding = binding_file(&root);
    fs::write(config_dir.join("config.toml"), "unknown = true\n").expect("settings");
    let before_settings = fs::read(config_dir.join("config.toml")).expect("read settings");
    let mut bad_binding = fs::read(&binding).expect("read binding");
    bad_binding[0] = b'!';
    fs::write(&binding, &bad_binding).expect("bad binding");
    let before_binding = fs::read(&binding).expect("read binding");
    let startup = StartupConfig::load(&config_dir, &binding);
    assert!(startup.issue.is_some());
    assert_eq!(fs::read(config_dir.join("config.toml")).expect("settings unchanged"), before_settings);
    assert_eq!(fs::read(&binding).expect("binding unchanged"), before_binding);
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn status_logging_resource_status_is_read_only_bounded_and_has_at_most_32_safe_transitions() {
    let mut ring = TransitionRing::default();
    for index in 0..80 {
        ring.push(SafeCode::ReconnectAttempt, index);
    }
    assert_eq!(ring.len(), 32);
    let snapshot = StatusSnapshot::stopped("cfg123").with_transitions(ring.clone());
    let bytes = snapshot.encode().expect("status encode");
    assert!(bytes.len() <= STATUS_PAYLOAD_LIMIT);
    let decoded = StatusSnapshot::decode(&bytes).expect("status decode");
    assert_eq!(decoded.state, BridgeStatus::Stopped);
    assert_eq!(decoded.transitions.len(), 32);
    assert!(!decoded.has_mutating_fields());
}

#[test]
fn status_logging_resource_status_serialization_allows_only_safe_codes_and_no_private_values() {
    let mut snapshot = StatusSnapshot::stopped("cfg123");
    snapshot.last_error = Some(SafeCode::HerdrUnavailable);
    snapshot.transitions.push(status::Transition::new(SafeCode::ConfigInvalid, 4));
    let encoded = snapshot.encode().expect("encode");
    for forbidden in ["/home/", "token", "prompt", "transcript", "account@example", "raw upstream"] {
        assert!(!encoded.windows(forbidden.len()).any(|window| window == forbidden.as_bytes()));
    }
    let mut tampered = encoded.clone();
    tampered.extend_from_slice(br#"{"path":"/home/private"}"#);
    assert!(StatusSnapshot::decode(&tampered).is_err());
}

#[test]
fn status_logging_resource_logging_is_default_off_and_enabled_logging_is_structured_safe_stderr_only() {
    let disabled = SafeLogger::new(TraceConfig::default());
    assert!(!disabled.enabled());
    assert!(disabled.serialize(SafeCode::BridgeStarted, 10).is_none());

    let enabled = SafeLogger::new(TraceConfig { enabled: true });
    assert!(enabled.enabled());
    let line = enabled.serialize(SafeCode::BridgeStarted, 10).expect("safe event");
    assert!(line.len() <= STATUS_PAYLOAD_LIMIT);
    assert!(line.contains("bridge_started"));
    for forbidden in ["/home/", "account", "prompt", "transcript", "developer", "secret"] {
        assert!(!line.contains(forbidden));
    }
}

#[test]
fn status_logging_resource_healthy_idle_metrics_have_no_source_polling_or_fixed_rate_wakeup() {
    let metrics = lifecycle::ResourceMetrics::idle();
    assert_eq!(metrics.source_polls, 0);
    assert_eq!(metrics.timer_fires, 0);
    assert_eq!(metrics.wakes, 0);
    assert!(metrics.queue_high_water <= 16);
    assert!(metrics.history_size <= 32);
    assert!(metrics.max_payload <= CONTROL_PAYLOAD_LIMIT);
}
