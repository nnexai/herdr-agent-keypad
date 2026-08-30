//! Startup-only configuration and frozen keypad binding.
//!
//! Herdr supplies the runtime directories.  This module deliberately has one
//! settings authority (`config.toml` below that directory) and does not inspect
//! environment variables, command-line arguments, or any other configuration
//! file.  Settings are read once; callers retain the resulting value for the
//! lifetime of a bridge process.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};

pub const SETTINGS_FILE_NAME: &str = "config.toml";
pub const MAX_CONFIG_BYTES: usize = 16 * 1024;
pub const CONFIG_IDENTITY_LENGTH: usize = 25;
pub const DEFAULT_RECONNECT_INITIAL_MS: u64 = 500;
pub const DEFAULT_RECONNECT_MAX_MS: u64 = 8_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigIssue {
    code: ConfigIssueCode,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConfigIssueCode {
    SettingsUnavailable,
    SettingsOversized,
    SettingsInvalid,
    BindingUnavailable,
    BindingInvalid,
    BindingIncompatible,
}

impl ConfigIssue {
    pub fn new(code: ConfigIssueCode) -> Self {
        Self { code }
    }

    pub fn code(&self) -> ConfigIssueCode {
        self.code
    }

    pub fn safe_code(&self) -> &'static str {
        match self.code {
            ConfigIssueCode::SettingsUnavailable => "settings_unavailable",
            ConfigIssueCode::SettingsOversized => "settings_oversized",
            ConfigIssueCode::SettingsInvalid => "settings_invalid",
            ConfigIssueCode::BindingUnavailable => "binding_unavailable",
            ConfigIssueCode::BindingInvalid => "binding_invalid",
            ConfigIssueCode::BindingIncompatible => "binding_incompatible",
        }
    }
}

/// Only fields in this closed file may alter runtime behavior.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct SettingsFile {
    #[serde(default)]
    logging_enabled: bool,
    #[serde(default = "default_reconnect_initial_ms")]
    reconnect_initial_ms: u64,
    #[serde(default = "default_reconnect_max_ms")]
    reconnect_max_ms: u64,
}

fn default_reconnect_initial_ms() -> u64 {
    DEFAULT_RECONNECT_INITIAL_MS
}

fn default_reconnect_max_ms() -> u64 {
    DEFAULT_RECONNECT_MAX_MS
}

/// Canonical, validated settings retained by a running process.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EffectiveConfig {
    pub logging_enabled: bool,
    pub reconnect_initial_ms: u64,
    pub reconnect_max_ms: u64,
}

impl Default for EffectiveConfig {
    fn default() -> Self {
        Self::from_values(false, DEFAULT_RECONNECT_INITIAL_MS, DEFAULT_RECONNECT_MAX_MS)
            .expect("platform defaults are valid")
    }
}

impl EffectiveConfig {
    fn from_values(logging_enabled: bool, reconnect_initial_ms: u64, reconnect_max_ms: u64) -> Result<Self, ConfigIssue> {
        if !(100..=DEFAULT_RECONNECT_MAX_MS).contains(&reconnect_initial_ms)
            || reconnect_initial_ms > reconnect_max_ms
            || reconnect_max_ms > DEFAULT_RECONNECT_MAX_MS
        {
            return Err(ConfigIssue::new(ConfigIssueCode::SettingsInvalid));
        }
        let value = Self {
            logging_enabled,
            reconnect_initial_ms,
            reconnect_max_ms,
        };
        Ok(value)
    }

    pub fn from_toml(contents: &str) -> Result<Self, ConfigIssue> {
        let parsed: SettingsFile = toml::from_str(contents)
            .map_err(|_| ConfigIssue::new(ConfigIssueCode::SettingsInvalid))?;
        Self::from_values(parsed.logging_enabled, parsed.reconnect_initial_ms, parsed.reconnect_max_ms)
    }

    pub fn identity(&self) -> String {
        self.compute_identity()
    }

    pub fn control_payload_limit(&self) -> usize {
        super::control::CONTROL_PAYLOAD_LIMIT
    }

    fn compute_identity(&self) -> String {
        let canonical = format!(
            "logging_enabled={};reconnect_initial_ms={};reconnect_max_ms={}",
            self.logging_enabled, self.reconnect_initial_ms, self.reconnect_max_ms
        );
        let digest = Sha256::digest(canonical.as_bytes());
        let mut identity: String = digest
            .iter()
            .take(13)
            .map(|byte| format!("{byte:02x}"))
            .collect();
        identity.truncate(CONFIG_IDENTITY_LENGTH);
        identity
    }

    pub fn load(config_dir: &Path) -> Result<Self, ConfigIssue> {
        let path = settings_path(config_dir)?;
        let bytes = fs::read(path).map_err(|_| ConfigIssue::new(ConfigIssueCode::SettingsUnavailable))?;
        if bytes.len() > MAX_CONFIG_BYTES {
            return Err(ConfigIssue::new(ConfigIssueCode::SettingsOversized));
        }
        let text = std::str::from_utf8(&bytes)
            .map_err(|_| ConfigIssue::new(ConfigIssueCode::SettingsInvalid))?;
        Self::from_toml(text)
    }
}

pub fn settings_path(config_dir: &Path) -> Result<PathBuf, ConfigIssue> {
    if config_dir.as_os_str().is_empty() {
        return Err(ConfigIssue::new(ConfigIssueCode::SettingsUnavailable));
    }
    let path = config_dir.join(SETTINGS_FILE_NAME);
    if !is_descendant(config_dir, &path) {
        return Err(ConfigIssue::new(ConfigIssueCode::SettingsUnavailable));
    }
    Ok(path)
}

/// Frozen format carried over from phase-1 pairing.  This type is intentionally
/// independent from advanced settings and is never rewritten by the bridge.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PairingBinding {
    pub schema_version: u8,
    pub device_id: String,
    pub protocol: u8,
    pub firmware: String,
}

impl PairingBinding {
    pub fn validate(&self) -> Result<(), ConfigIssue> {
        if self.schema_version != 1
            || self.protocol != 1
            || self.device_id.is_empty()
            || self.device_id.len() > 64
            || self.device_id == "host"
            || !self
                .device_id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
        {
            return Err(ConfigIssue::new(ConfigIssueCode::BindingInvalid));
        }
        if self.firmware.is_empty() || self.firmware.len() > 128 || !self.firmware.is_ascii() {
            return Err(ConfigIssue::new(ConfigIssueCode::BindingIncompatible));
        }
        Ok(())
    }

    pub fn load(path: &Path) -> Result<Option<Self>, ConfigIssue> {
        let bytes = match fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(ConfigIssue::new(ConfigIssueCode::BindingUnavailable)),
        };
        if bytes.len() > MAX_CONFIG_BYTES {
            return Err(ConfigIssue::new(ConfigIssueCode::BindingInvalid));
        }
        let binding: Self = serde_json::from_slice(&bytes)
            .map_err(|_| ConfigIssue::new(ConfigIssueCode::BindingInvalid))?;
        binding.validate()?;
        Ok(Some(binding))
    }
}

/// Startup result: malformed state is retained as a safe issue while the host
/// process remains alive and reports an unavailable boundary.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StartupConfig {
    pub effective: EffectiveConfig,
    pub binding: Option<PairingBinding>,
    pub issue: Option<ConfigIssue>,
}

impl StartupConfig {
    pub fn load(config_dir: &Path, binding_path: &Path) -> Self {
        let mut issue = None;
        let effective = match EffectiveConfig::load(config_dir) {
            Ok(value) => value,
            Err(error) if error.code == ConfigIssueCode::SettingsUnavailable => EffectiveConfig::default(),
            Err(error) => {
                issue = Some(error);
                EffectiveConfig::default()
            }
        };
        let binding = match PairingBinding::load(binding_path) {
            Ok(binding) => binding,
            Err(error) => {
                if issue.is_none() {
                    issue = Some(error);
                }
                None
            }
        };
        Self { effective, binding, issue }
    }

    pub fn available(&self) -> bool {
        self.binding.is_some() && self.issue.is_none()
    }
}

fn is_descendant(root: &Path, child: &Path) -> bool {
    let mut root_components = root.components();
    let mut child_components = child.components();
    loop {
        match (root_components.next(), child_components.next()) {
            (None, _) => return true,
            (Some(root), Some(child)) if root == child => {}
            _ => return false,
        }
    }
}
