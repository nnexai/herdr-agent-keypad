use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const PLUGIN_MANIFEST: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../herdr-plugin.toml");

fn temp_root() -> PathBuf {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH).expect("clock").as_nanos();
    let root = std::env::temp_dir().join(format!("herdr-keypad-production-{}-{stamp}", std::process::id()));
    fs::create_dir_all(&root).expect("temporary root");
    root
}

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_herdr-keypad-native")
}

struct ChildGuard(Child);

impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn lifecycle_command(root: &Path, command: &str) -> Command {
    let mut invocation = Command::new(binary());
    invocation
        .env("PATH", "")
        .arg(command)
        .env("HOME", root.join("home"))
        .env("HERDR_PLUGIN_CONFIG_DIR", root.join("config"))
        .env("HERDR_PLUGIN_STATE_DIR", root.join("state"))
        .env("HERDR_SOCKET_PATH", root.join("herdr.sock"))
        .env("HERDR_BIN_PATH", "/bin/true")
        .env("HERDR_PID", "0");
    invocation
}

#[cfg(unix)]
fn install_codex_0151_fixture(root: &Path) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let bin = root.join("bin");
    fs::create_dir_all(&bin).expect("fixture bin");
    let codex = bin.join("codex");
    fs::write(
        &codex,
        r#"#!/bin/sh
while IFS= read -r line; do
    case "$line" in
        *'"method":"initialize"'*)
            printf '%s\n' '{"id":1,"result":{"serverInfo":{"name":"codex","version":"0.151.0"}}}'
            ;;
        *'"method":"account/read"'*)
            printf '%s\n' '{"method":"account/updated","params":{"authMode":"chatgpt"}}'
            printf '%s\n' '{"id":2,"result":{"account":{"type":"chatgpt"},"requiresOpenaiAuth":true}}'
            ;;
        *'"method":"account/rateLimits/read"'*)
            printf '%s\n' '{"id":3,"result":{"rateLimits":{"primary":{"usedPercent":15,"windowDurationMins":300,"resetsAt":null},"secondary":null,"credits":null,"individualLimit":null,"limitId":null,"limitName":null,"planType":null,"rateLimitReachedType":null,"spendControlReached":null},"rateLimitsByLimitId":{},"rateLimitResetCredits":null}}'
            ;;
    esac
done
"#,
    )
    .expect("fixture executable");
    let mut permissions = fs::metadata(&codex).expect("fixture metadata").permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&codex, permissions).expect("fixture permissions");
    bin
}

fn wait_until(timeout: Duration, mut condition: impl FnMut() -> bool) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if condition() {
            return true;
        }
        thread::sleep(Duration::from_millis(20));
    }
    condition()
}

#[test]
fn production_binary_start_status_stop_owns_control_socket_for_authority_lifetime() {
    let root = temp_root();
    fs::create_dir_all(root.join("config")).expect("config");
    fs::create_dir_all(root.join("state")).expect("state");
    fs::create_dir_all(root.join("home/.config/herdr")).expect("home config");
    fs::write(root.join("config/config.toml"), "logging_enabled = false\n").expect("settings");
    fs::write(
        root.join("home/.config/herdr/keypad-binding.json"),
        br#"{"schema_version":1,"device_id":"kbd-123","protocol":1,"firmware":"phase1-bringup"}"#,
    )
    .expect("binding");

    let start = lifecycle_command(&root, "start")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("start authority");
    let mut authority = ChildGuard(start);
    let socket = root.join("state/bridge.sock");
    assert!(
        wait_until(Duration::from_secs(5), || socket.exists()),
        "successful start never created bridge.sock"
    );
    assert!(authority.0.try_wait().expect("authority state").is_none(), "authority exited before stop");

    let status_output = lifecycle_command(&root, "status").output().expect("running status");
    assert!(status_output.status.success(), "status failed: {}", String::from_utf8_lossy(&status_output.stderr));
    assert!(status_output.stdout.len() <= 16 * 1024, "status exceeded the control payload bound");
    let status: Value = serde_json::from_slice(&status_output.stdout).expect("bounded JSON status");
    assert_eq!(status["reply"], "status");
    assert_eq!(status["state"], "running");
    let bounded_states = [
        "stopped",
        "running",
        "ready",
        "unavailable",
        "device_unavailable",
        "herdr_unavailable",
        "codex_unavailable",
        "stale",
    ];
    for field in ["device_state", "herdr_state", "codex_state"] {
        let value = status[field].as_str().expect("source state string");
        assert!(bounded_states.contains(&value), "unbounded {field}: {value}");
    }

    let stop_output = lifecycle_command(&root, "stop").output().expect("stop authority");
    assert!(stop_output.status.success(), "stop failed: {}", String::from_utf8_lossy(&stop_output.stderr));
    let stopped: Value = serde_json::from_slice(&stop_output.stdout).expect("stopped reply");
    assert_eq!(stopped["reply"], "stopped");
    assert!(
        wait_until(Duration::from_secs(5), || authority.0.try_wait().expect("authority state").is_some()),
        "authority did not exit after stop"
    );
    assert!(!socket.exists(), "control socket remained after authority exit");

    let final_output = lifecycle_command(&root, "status").output().expect("final status");
    assert!(final_output.status.success(), "final status failed: {}", String::from_utf8_lossy(&final_output.stderr));
    let final_status: Value = serde_json::from_slice(&final_output.stdout).expect("final stopped status");
    assert_eq!(final_status["reply"], "status");
    assert_eq!(final_status["state"], "stopped");

    fs::remove_dir_all(root).expect("cleanup");
}

#[cfg(unix)]
#[test]
fn production_status_reports_ready_after_codex_0151_collection() {
    let root = temp_root();
    fs::create_dir_all(root.join("config")).expect("config");
    fs::create_dir_all(root.join("state")).expect("state");
    fs::create_dir_all(root.join("home/.config/herdr")).expect("home config");
    fs::write(root.join("config/config.toml"), "logging_enabled = false\n").expect("settings");
    fs::write(
        root.join("home/.config/herdr/keypad-binding.json"),
        br#"{"schema_version":1,"device_id":"kbd-123","protocol":1,"firmware":"phase1-bringup"}"#,
    )
    .expect("binding");
    let fixture_path = install_codex_0151_fixture(&root);

    let start = lifecycle_command(&root, "start")
        .env("PATH", &fixture_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("start authority");
    let mut authority = ChildGuard(start);
    let socket = root.join("state/bridge.sock");
    assert!(
        wait_until(Duration::from_secs(5), || socket.exists()),
        "successful start never created bridge.sock"
    );
    assert!(
        wait_until(Duration::from_secs(12), || {
            let output = lifecycle_command(&root, "status").env("PATH", &fixture_path).output();
            let Ok(output) = output else { return false };
            if !output.status.success() {
                return false;
            }
            serde_json::from_slice::<Value>(&output.stdout)
                .ok()
                .and_then(|status| status["codex_state"].as_str().map(str::to_owned))
                .as_deref()
                == Some("ready")
        }),
        "status never reflected the successful Codex collection"
    );

    let stop = lifecycle_command(&root, "stop")
        .env("PATH", &fixture_path)
        .output()
        .expect("stop authority");
    assert!(stop.status.success());
    assert!(
        wait_until(Duration::from_secs(5), || authority.0.try_wait().expect("authority state").is_some()),
        "authority did not exit after stop"
    );
    fs::remove_dir_all(root).expect("cleanup");
}
#[cfg(unix)]
fn socket_marker(path: &Path) -> (u64, u64) {
    use std::os::unix::fs::MetadataExt;
    let metadata = fs::metadata(path).expect("control socket metadata");
    (metadata.dev(), metadata.ino())
}

#[test]
fn production_binary_restart_replaces_pid_reloads_config_and_reopens_socket() {
    let root = temp_root();
    fs::create_dir_all(root.join("config")).expect("config");
    fs::create_dir_all(root.join("state")).expect("state");
    fs::create_dir_all(root.join("home/.config/herdr")).expect("home config");
    fs::write(root.join("config/config.toml"), "logging_enabled = false\n").expect("settings");
    fs::write(
        root.join("home/.config/herdr/keypad-binding.json"),
        br#"{"schema_version":1,"device_id":"kbd-123","protocol":1,"firmware":"phase1-bringup"}"#,
    )
    .expect("binding");

    let start = lifecycle_command(&root, "start")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("start authority");
    let mut authority = ChildGuard(start);
    let socket = root.join("state/bridge.sock");
    assert!(wait_until(Duration::from_secs(5), || socket.exists()), "start never created bridge.sock");
    let initial_pid = authority.0.id();
    let initial_socket = socket_marker(&socket);
    let initial_status = lifecycle_command(&root, "status").output().expect("initial status");
    let initial_status: Value = serde_json::from_slice(&initial_status.stdout).expect("initial status JSON");
    let initial_identity = initial_status["config_identity"].as_str().expect("initial config identity").to_owned();

    fs::write(root.join("config/config.toml"), "logging_enabled = true\n").expect("changed settings");
    let restart = lifecycle_command(&root, "restart")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("restart authority");
    let mut restarted = ChildGuard(restart);
    assert_ne!(restarted.0.id(), initial_pid, "restart reused the original process");
    assert!(
        wait_until(Duration::from_secs(5), || authority.0.try_wait().expect("old authority state").is_some()),
        "old authority remained alive after restart"
    );
    assert!(wait_until(Duration::from_secs(5), || socket.exists()), "restart never recreated bridge.sock");
    assert_ne!(socket_marker(&socket), initial_socket, "restart did not recreate bridge.sock");
    assert!(
        restarted.0.try_wait().expect("restarted authority state").is_none(),
        "replacement authority exited before serving"
    );
    let changed_status = lifecycle_command(&root, "status").output().expect("changed status");
    assert!(changed_status.status.success(), "changed status failed: {}", String::from_utf8_lossy(&changed_status.stderr));
    let changed_status: Value = serde_json::from_slice(&changed_status.stdout).expect("changed status JSON");
    assert_ne!(
        changed_status["config_identity"].as_str().expect("changed config identity"),
        initial_identity,
        "restart did not reload changed StartupConfig"
    );

    let same_config_socket = socket_marker(&socket);
    let second_restart = lifecycle_command(&root, "restart")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("same-config restart authority");
    let mut same_config = ChildGuard(second_restart);
    assert_ne!(same_config.0.id(), restarted.0.id(), "same-config restart reused the previous process");
    assert!(
        wait_until(Duration::from_secs(5), || restarted.0.try_wait().expect("previous authority state").is_some()),
        "previous authority remained alive after same-config restart"
    );
    assert!(wait_until(Duration::from_secs(5), || socket.exists()), "same-config restart removed bridge.sock");
    assert_ne!(socket_marker(&socket), same_config_socket, "same-config restart did not recreate bridge.sock");
    let same_config_status = lifecycle_command(&root, "status").output().expect("same-config status");
    assert!(same_config_status.status.success(), "same-config status failed: {}", String::from_utf8_lossy(&same_config_status.stderr));
    let same_config_status: Value = serde_json::from_slice(&same_config_status.stdout).expect("same-config status JSON");
    assert_eq!(
        same_config_status["config_identity"].as_str(),
        changed_status["config_identity"].as_str(),
        "same-config restart changed effective configuration"
    );

    let stop_output = lifecycle_command(&root, "stop").output().expect("stop replacement");
    assert!(stop_output.status.success(), "stop failed: {}", String::from_utf8_lossy(&stop_output.stderr));
    assert!(
        wait_until(Duration::from_secs(5), || same_config.0.try_wait().expect("replacement state").is_some()),
        "replacement authority did not exit after stop"
    );
    assert!(!socket.exists(), "control socket remained after replacement stop");
    fs::remove_dir_all(root).expect("cleanup");
}


#[test]
fn plugin_manifest_is_cross_platform_direct_argv_and_has_no_developer_runtime() {
    let manifest = fs::read_to_string(PLUGIN_MANIFEST).expect("plugin manifest");
    let parsed: toml::Value = toml::from_str(&manifest).expect("valid plugin TOML");
    assert_eq!(parsed["platforms"].as_array().map(|items| items.len()), Some(2));
    assert!(manifest.contains("platforms = [\"linux\", \"macos\"]"));
    assert!(manifest.contains("command = [\"bin/herdr-keypad\", \"startup\"]"));

    let forbidden = [
        "python", "PYTHONPATH", "venv", "pip", "npm", "node", "tracer", "fixture", "evidence", "shell",
        "ensure-bridge.sh", "state.json", "history.jsonl", "flock", "/proc/",
    ];
    for word in forbidden {
        assert!(!manifest.to_ascii_lowercase().contains(&word.to_ascii_lowercase()), "manifest contains forbidden {word}");
    }

    let startup = parsed["startup"].as_array().expect("startup array");
    assert_eq!(startup.len(), 1);
    assert_eq!(startup[0]["command"], toml::Value::Array(vec!["bin/herdr-keypad".into(), "startup".into()]));
    let actions = parsed["actions"].as_array().expect("action array");
    assert_eq!(actions.len(), 6);
    for action in actions {
        let command = action["command"].as_array().expect("direct action command");
        assert_eq!(command.len(), 2);
        assert_eq!(command[0].as_str(), Some("bin/herdr-keypad"));
        assert!(matches!(command[1].as_str(), Some("start" | "stop" | "restart" | "status" | "repair" | "re-pair")));
    }
}

#[test]
fn production_binary_status_works_with_python_removed_from_path() {
    let root = temp_root();
    let config = root.join("config");
    let state = root.join("state");
    let home = root.join("home");
    fs::create_dir_all(&config).expect("config");
    fs::create_dir_all(&state).expect("state");
    fs::create_dir_all(home.join(".config/herdr")).expect("home config");
    fs::write(config.join("config.toml"), "logging_enabled = false\n").expect("settings");

    let output = Command::new(binary())
        .arg("status")
        .env("PATH", "")
        .env("HOME", &home)
        .env("HERDR_PLUGIN_CONFIG_DIR", &config)
        .env("HERDR_PLUGIN_STATE_DIR", &state)
        .env("HERDR_SOCKET_PATH", root.join("herdr.sock"))
        .env("HERDR_BIN_PATH", "/bin/true")
        .env("HERDR_PID", "0")
        .output()
        .expect("native production binary");
    assert!(output.status.success(), "status failed: {}", String::from_utf8_lossy(&output.stderr));
    let status: Value = serde_json::from_slice(&output.stdout).expect("bounded JSON status");
    assert_eq!(status["reply"], "status");
    assert_eq!(status["state"], "stopped");
    let combined = format!("{}{}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr)).to_ascii_lowercase();
    for forbidden in ["python", "prompt", "transcript", "secret", "/home/", "path"] {
        assert!(!combined.contains(forbidden), "production output leaked {forbidden}");
    }
    assert!(fs::read_dir(&state).expect("state directory").next().is_none(), "read-only status created state");
    fs::remove_dir_all(root).expect("cleanup");
}

#[test]
fn developer_and_generic_commands_are_not_in_production_surface() {
    for command in ["--help", "tracer", "fixture", "evidence", "doctor", "shell", "run-tests"] {
        let output = Command::new(binary()).arg(command).output().expect("binary invocation");
        assert!(!output.status.success(), "forbidden command accepted: {command}");
        let error = String::from_utf8_lossy(&output.stderr).to_ascii_lowercase();
        assert!(!error.contains("python"));
        assert!(!error.contains("prompt"));
        assert!(!error.contains("transcript"));
    }
}

#[test]
fn binary_source_and_environment_boundary_exclude_private_developer_surfaces() {
    let source = fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("src/main.rs")).expect("entrypoint source");
    for forbidden in ["PYTHONPATH", "python", "venv", "fixture", "tracer", "state.json", "history.jsonl", "/proc/"] {
        assert!(!source.to_ascii_lowercase().contains(&forbidden.to_ascii_lowercase()), "entrypoint contains {forbidden}");
    }
    let bytes = fs::read(binary()).expect("built production binary");
    let text = String::from_utf8_lossy(&bytes).to_ascii_lowercase();
    for forbidden in ["pythonpath", "history.jsonl", "state.json", "run-tests", "tracer"] {
        assert!(!text.contains(forbidden), "binary contains forbidden developer marker {forbidden}");
    }
}
