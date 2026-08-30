//! Closed production entrypoint.
//!
//! Herdr supplies runtime paths through its invocation environment.  The
//! executable accepts no settings, developer, evidence, shell, or HID
//! arguments; advanced settings are read only from `config.toml` below
//! `HERDR_PLUGIN_CONFIG_DIR` by the native runtime.

use herdr_keypad_native::core::RuntimeCoordinator;
use herdr_keypad_native::ports::config::StartupConfig;
use herdr_keypad_native::ports::control::{
    AuthorityLock, ControlReply, ControlRequest, CONTROL_PAYLOAD_LIMIT, CONTROL_SOCKET_NAME,
};
use herdr_keypad_native::ports::lifecycle::RuntimePaths;
use herdr_keypad_native::ports::status::StatusSnapshot;
use herdr_keypad_native::ports::usb::PlatformSerial;
use herdr_keypad_native::BridgeError;
use std::path::PathBuf;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use tokio::time::{sleep, Instant};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProductionCommand {
    Startup,
    Start,
    Stop,
    Restart,
    Status,
    Repair,
    RepairPair,
}

fn parse_command(args: &[String]) -> Result<ProductionCommand, String> {
    match args {
        [] => Ok(ProductionCommand::Startup),
        [command] => match command.as_str() {
            "startup" | "run" => Ok(ProductionCommand::Startup),
            "start" => Ok(ProductionCommand::Start),
            "stop" => Ok(ProductionCommand::Stop),
            "restart" => Ok(ProductionCommand::Restart),
            "status" => Ok(ProductionCommand::Status),
            "repair" => Ok(ProductionCommand::Repair),
            "re-pair" => Ok(ProductionCommand::RepairPair),
            _ => Err(format!("unsupported production command: {command}")),
        },
        _ => Err("exactly one production command is allowed".to_owned()),
    }
}

fn required_path(name: &str) -> Result<PathBuf, BridgeError> {
    std::env::var_os(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or_else(|| BridgeError::invalid_input(format!("Herdr did not provide {name}")))
}

fn runtime_paths() -> Result<RuntimePaths, BridgeError> {
    let config_dir = required_path("HERDR_PLUGIN_CONFIG_DIR")?;
    let state_dir = required_path("HERDR_PLUGIN_STATE_DIR")?;
    let herdr_socket = required_path("HERDR_SOCKET_PATH")?;
    let herdr_binary = required_path("HERDR_BIN_PATH")?;
    let herdr_pid = std::env::var("HERDR_PID")
        .ok()
        .map(|value| value.parse::<u32>().map_err(|_| BridgeError::invalid_input("HERDR_PID is invalid")))
        .transpose()?
        .unwrap_or(0);
    Ok(RuntimePaths::new(config_dir, state_dir, herdr_socket, herdr_binary, herdr_pid))
}

fn binding_path() -> Result<PathBuf, BridgeError> {
    let home = std::env::var_os("HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or_else(|| BridgeError::invalid_input("HOME is unavailable for the frozen pairing binding"))?;
    Ok(home.join(".config").join("herdr").join("keypad-binding.json"))
}

fn platform() -> Result<Box<dyn PlatformSerial>, BridgeError> {
    #[cfg(target_os = "linux")]
    {
        return Ok(Box::new(herdr_keypad_native::platform::linux::LinuxPlatform::new()));
    }
    #[cfg(target_os = "macos")]
    {
        return Ok(Box::new(herdr_keypad_native::platform::macos::MacOsPlatform::new()));
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        Err(BridgeError::invalid_input("unsupported native production target"))
    }
}
const RESTART_HANDOFF_TIMEOUT: Duration = Duration::from_secs(5);
const RESTART_HANDOFF_POLL: Duration = Duration::from_millis(20);

async fn wait_for_authority_release(paths: &RuntimePaths) -> Result<(), BridgeError> {
    let deadline = Instant::now() + RESTART_HANDOFF_TIMEOUT;
    loop {
        match AuthorityLock::acquire(paths.state_dir()) {
            Ok(authority) => {
                drop(authority);
                return Ok(());
            }
            Err(error) if error.safe_code() == "already_owned" => {}
            Err(_) => return Err(BridgeError::protocol("restart handoff failed")),
        }
        if Instant::now() >= deadline {
            return Err(BridgeError::protocol("restart handoff timed out"));
        }
        sleep(RESTART_HANDOFF_POLL).await;
    }
}

async fn run_runtime() -> Result<(), BridgeError> {
    let paths = runtime_paths()?;
    let binding = binding_path()?;
    let startup = StartupConfig::load(&paths.config_dir, &binding);
    let coordinator = RuntimeCoordinator::new(paths, startup, binding, platform()?)?;
    coordinator.run().await
}

async fn request_control(paths: &RuntimePaths, request: ControlRequest) -> Result<ControlReply, BridgeError> {
    let socket_path = paths.state_dir().join(CONTROL_SOCKET_NAME);
    let mut stream = UnixStream::connect(socket_path).await.map_err(BridgeError::io)?;
    let encoded = request
        .encode()
        .map_err(|error| BridgeError::protocol(format!("control request: {error:?}")))?;
    stream.write_all(&encoded).await.map_err(BridgeError::io)?;
    stream.flush().await.map_err(BridgeError::io)?;
    let mut reader = BufReader::new(stream).take((CONTROL_PAYLOAD_LIMIT + 1) as u64);
    let mut line = Vec::new();
    reader.read_until(b'\n', &mut line).await.map_err(BridgeError::io)?;
    if line.is_empty() || line.len() > CONTROL_PAYLOAD_LIMIT {
        return Err(BridgeError::protocol("control reply is unavailable or oversized"));
    }
    ControlReply::decode(&line).map_err(|error| BridgeError::protocol(format!("control reply: {error:?}")))
}

fn print_reply(reply: &ControlReply) -> Result<(), BridgeError> {
    let bytes = serde_json::to_vec(reply).map_err(|error| BridgeError::protocol(error.to_string()))?;
    println!("{}", String::from_utf8(bytes).map_err(|_| BridgeError::protocol("control reply is not UTF-8"))?);
    Ok(())
}

async fn invoke(command: ProductionCommand) -> Result<(), BridgeError> {
    let paths = runtime_paths()?;
    let binding = binding_path()?;
    let startup = StartupConfig::load(&paths.config_dir, &binding);
    let identity = startup.effective.identity();
    let request = match command {
        ProductionCommand::Start => ControlRequest::start(identity.clone()),
        ProductionCommand::Stop => ControlRequest::stop(),
        ProductionCommand::Restart => ControlRequest::restart(identity.clone()),
        ProductionCommand::Status => ControlRequest::status(),
        ProductionCommand::Repair => ControlRequest::repair(),
        ProductionCommand::RepairPair => ControlRequest::repair_pair(),
        ProductionCommand::Startup => return run_runtime().await,
    };
    match request_control(&paths, request).await {
        Ok(reply @ ControlReply::Restarted { .. }) if command == ProductionCommand::Restart => {
            print_reply(&reply)?;
            wait_for_authority_release(&paths).await?;
            run_runtime().await
        }
        Ok(reply) => print_reply(&reply),
        Err(_) if matches!(command, ProductionCommand::Start | ProductionCommand::Restart) => run_runtime().await,
        Err(_) if command == ProductionCommand::Status => {
            print_reply(&ControlReply::Status(StatusSnapshot::stopped(identity)))
        }
        Err(_) if command == ProductionCommand::Stop => print_reply(&ControlReply::Stopped),
        Err(_) => print_reply(&ControlReply::Rejected { code: "not_running".to_owned() }),
    }
}

#[tokio::main]
async fn main() -> Result<(), BridgeError> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let command = parse_command(&args).map_err(BridgeError::invalid_input)?;
    invoke(command).await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn parser_accepts_only_closed_production_modes() {
        assert_eq!(parse_command(&args(&[])), Ok(ProductionCommand::Startup));
        assert_eq!(parse_command(&args(&["run"])), Ok(ProductionCommand::Startup));
        assert_eq!(parse_command(&args(&["start"])), Ok(ProductionCommand::Start));
        assert_eq!(parse_command(&args(&["stop"])), Ok(ProductionCommand::Stop));
        assert_eq!(parse_command(&args(&["restart"])), Ok(ProductionCommand::Restart));
        assert_eq!(parse_command(&args(&["status"])), Ok(ProductionCommand::Status));
        assert_eq!(parse_command(&args(&["repair"])), Ok(ProductionCommand::Repair));
        assert_eq!(parse_command(&args(&["re-pair"])), Ok(ProductionCommand::RepairPair));
    }

    #[test]
    fn parser_rejects_developer_and_generic_modes() {
        for value in ["--inspect", "--smoke", "--run-bridge", "evidence", "focus", "provider", "--herdr-socket"] {
            assert!(parse_command(&args(&[value])).is_err(), "accepted {value}");
        }
        assert!(parse_command(&args(&["status", "--config"])).is_err());
    }
}
