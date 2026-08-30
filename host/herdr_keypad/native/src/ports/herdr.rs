//! Bounded event-driven adapter for Herdr's public Unix socket API.
//!
//! The adapter deliberately does not project agent rows or derive ordering.  It
//! transports complete public reads to the core, and converts every push event
//! into an invalidation.  `agent.focus` is the only write represented here.

use herdr_keypad_native::{BridgeError, BridgeEvent, HerdrFocusAck, HerdrPort, HerdrSnapshot};
use serde_json::{json, Map, Value};
use std::fmt;
use std::future::Future;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::time::Duration;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWriteExt};
use tokio::net::unix::{OwnedReadHalf, OwnedWriteHalf};
use tokio::net::UnixStream;

pub const MAX_LINE_BYTES: usize = 65_536;
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(2);
pub const DEFAULT_SUBSCRIBE_DEADLINE: Duration = Duration::from_secs(5);

const DEFAULT_EVENTS: [&str; 9] = [
    "pane.created",
    "pane.updated",
    "pane.closed",
    "pane.focused",
    "pane.moved",
    "pane.exited",
    "pane.agent_detected",
    "workspace.closed",
    "tab.closed",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HerdrErrorCode {
    InvalidInput,
    Unavailable,
    Timeout,
    EndOfStream,
    LineTooLong,
    Malformed,
    Unrelated,
    Upstream,
    MissingResult,
    InvalidShape,
}

impl HerdrErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidInput => "invalid_input",
            Self::Unavailable => "unavailable",
            Self::Timeout => "timeout",
            Self::EndOfStream => "eof",
            Self::LineTooLong => "line_too_long",
            Self::Malformed => "malformed",
            Self::Unrelated => "unrelated",
            Self::Upstream => "upstream_error",
            Self::MissingResult => "missing_result",
            Self::InvalidShape => "invalid_shape",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HerdrError {
    code: HerdrErrorCode,
}

impl HerdrError {
    pub const fn new(code: HerdrErrorCode) -> Self {
        Self { code }
    }

    pub const fn code(&self) -> &'static str {
        self.code.as_str()
    }

    pub const fn kind(&self) -> HerdrErrorCode {
        self.code
    }

    fn bridge(&self) -> BridgeError {
        BridgeError::protocol(format!("herdr {}", self.code()))
    }
}

impl fmt::Display for HerdrError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "herdr {}", self.code())
    }
}

impl std::error::Error for HerdrError {}

impl From<HerdrError> for BridgeError {
    fn from(error: HerdrError) -> Self {
        error.bridge()
    }
}

#[derive(Debug, Clone)]
pub struct HerdrClient {
    socket_path: PathBuf,
    timeout: Duration,
    next_id: u64,
}

impl HerdrClient {
    pub fn new(path: impl Into<PathBuf>, timeout: Duration) -> Result<Self, HerdrError> {
        if timeout.is_zero() || timeout > Duration::from_secs(120) {
            return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
        }
        let path = path.into();
        if path.as_os_str().is_empty() {
            return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
        }
        Ok(Self {
            socket_path: path,
            timeout,
            next_id: 0,
        })
    }

    pub fn default_socket(timeout: Duration) -> Result<Self, HerdrError> {
        Self::new("/home/nnex/.config/herdr/herdr.sock", timeout)
    }

    pub fn socket_path(&self) -> &Path {
        &self.socket_path
    }

    pub fn timeout(&self) -> Duration {
        self.timeout
    }

    fn validate_method(method: &str) -> Result<(), HerdrError> {
        if method.is_empty()
            || method.bytes().any(|byte| byte < 0x21 || byte == b'\r' || byte == b'\n')
        {
            return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
        }
        Ok(())
    }

    fn request_id(&mut self) -> u64 {
        self.next_id = self.next_id.saturating_add(1).max(1);
        self.next_id
    }

    async fn request_value(&mut self, method: &str, params: Value) -> Result<Value, HerdrError> {
        Self::validate_method(method)?;
        let id = self.request_id().to_string();
        let mut request = serde_json::to_vec(&json!({
            "jsonrpc": "2.0",
            "id": id.clone(),
            "method": method,
            "params": params,
        }))
        .map_err(|_| HerdrError::new(HerdrErrorCode::Malformed))?;
        request.push(b'\n');
        if request.len() > MAX_LINE_BYTES {
            return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
        }

        let path = self.socket_path.clone();
        let timeout = self.timeout;
        let response_line = tokio::time::timeout(timeout, async move {
            let stream = UnixStream::connect(path)
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            let (mut reader, mut writer) = stream.into_split();
            writer
                .write_all(&request)
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            writer
                .flush()
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            read_bounded_line(&mut reader, MAX_LINE_BYTES).await
        })
        .await
        .map_err(|_| HerdrError::new(HerdrErrorCode::Timeout))??;

        let response: Value = serde_json::from_slice(&response_line)
            .map_err(|_| HerdrError::new(HerdrErrorCode::Malformed))?;
        let object = response
            .as_object()
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
        if object
            .get("jsonrpc")
            .is_some_and(|version| version.as_str() != Some("2.0"))
        {
            return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
        }
        if object.get("id").and_then(Value::as_str) != Some(id.as_str()) {
            return Err(HerdrError::new(HerdrErrorCode::Unrelated));
        }
        if object.contains_key("result") && object.contains_key("error") {
            return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
        }
        if object.contains_key("error") {
            if !object.get("error").is_some_and(Value::is_object) {
                return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
            }
            return Err(HerdrError::new(HerdrErrorCode::Upstream));
        }
        object
            .get("result")
            .cloned()
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::MissingResult))
    }

    pub async fn session_snapshot(&mut self) -> Result<Value, HerdrError> {
        let result = self.request_value("session.snapshot", json!({})).await?;
        let object = result
            .get("snapshot")
            .filter(|value| value.is_object())
            .unwrap_or(&result);
        if !object.is_object() {
            return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
        }
        Ok(object.clone())
    }

    pub async fn agent_list(&mut self) -> Result<Vec<Value>, HerdrError> {
        let result = self.request_value("agent.list", json!({})).await?;
        let rows = result
            .get("agents")
            .and_then(Value::as_array)
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
        Ok(rows.iter().filter(|row| row.is_object()).cloned().collect())
    }

    pub async fn workspace_list(&mut self) -> Result<Vec<Value>, HerdrError> {
        let result = self.request_value("workspace.list", json!({})).await?;
        let rows = result
            .get("workspaces")
            .and_then(Value::as_array)
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
        Ok(rows.iter().filter(|row| row.is_object()).cloned().collect())
    }

    pub async fn subscribe(
        &mut self,
        subscriptions: &[Value],
    ) -> Result<Value, HerdrError> {
        let subscriptions = validate_subscriptions(subscriptions)?;
        self.request_value("events.subscribe", json!({"subscriptions": subscriptions}))
            .await
    }

    pub async fn focus_pane(&mut self, pane_id: impl Into<String>) -> Result<HerdrFocusAck, HerdrError> {
        let pane_id = pane_id.into();
        validate_identifier(&pane_id)?;
        let result = self
            .request_value("agent.focus", json!({"target": pane_id}))
            .await?;
        let object = result
            .get("agent")
            .filter(|value| value.is_object())
            .and_then(Value::as_object)
            .or_else(|| result.as_object())
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
        let focused = object
            .get("focused")
            .and_then(Value::as_bool)
            .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
        let terminal_id = object
            .get("terminal_id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned();
        let agent_session = object
            .get("agent_session")
            .and_then(Value::as_str)
            .map(str::to_owned);
        Ok(HerdrFocusAck {
            pane_id,
            terminal_id,
            agent_session,
            focused,
        })
    }

    pub async fn read_complete(&mut self) -> Result<HerdrSnapshot, HerdrError> {
        let _snapshot = self.session_snapshot().await?;
        let agents = self.agent_list().await?;
        let workspaces = self.workspace_list().await?;
        Ok(HerdrSnapshot { agents, workspaces })
    }
}

impl HerdrPort for HerdrClient {
    fn read_complete(
        &mut self,
    ) -> Pin<Box<dyn Future<Output = Result<HerdrSnapshot, BridgeError>> + Send + '_>> {
        Box::pin(async move { HerdrClient::read_complete(self).await.map_err(Into::into) })
    }

    fn focus(
        &mut self,
        pane_id: String,
    ) -> Pin<Box<dyn Future<Output = Result<HerdrFocusAck, BridgeError>> + Send + '_>> {
        Box::pin(async move { self.focus_pane(pane_id).await.map_err(Into::into) })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HerdrStreamMode {
    Unclassified,
    Push,
    Fallback,
    Closed,
}

#[derive(Debug)]
pub struct HerdrEventStream {
    client: HerdrClient,
    subscriptions: Vec<Value>,
    reader: Option<OwnedReadHalf>,
    writer: Option<OwnedWriteHalf>,
    read_buffer: Vec<u8>,
    next_id: u64,
    request_id: Option<String>,
    mode: HerdrStreamMode,
    reason: Option<HerdrErrorCode>,
}

impl HerdrEventStream {
    pub fn new(client: HerdrClient) -> Self {
        let subscriptions = DEFAULT_EVENTS
            .iter()
            .map(|event| json!({"type": event}))
            .collect();
        Self {
            client,
            subscriptions,
            reader: None,
            writer: None,
            read_buffer: Vec::new(),
            next_id: 0,
            request_id: None,
            mode: HerdrStreamMode::Unclassified,
            reason: None,
        }
    }

    pub fn with_subscriptions(
        client: HerdrClient,
        subscriptions: Vec<Value>,
    ) -> Result<Self, HerdrError> {
        let subscriptions = validate_subscriptions(&subscriptions)?;
        let mut stream = Self::new(client);
        stream.subscriptions = subscriptions;
        Ok(stream)
    }

    pub fn mode(&self) -> HerdrStreamMode {
        self.mode
    }

    pub fn active(&self) -> bool {
        self.mode == HerdrStreamMode::Push && self.reader.is_some() && self.writer.is_some()
    }

    pub fn fallback_eligible(&self) -> bool {
        matches!(self.mode, HerdrStreamMode::Fallback | HerdrStreamMode::Unclassified)
    }

    pub fn reason(&self) -> Option<&'static str> {
        self.reason.map(HerdrErrorCode::as_str)
    }

    fn next_request_id(&mut self) -> String {
        self.next_id = self.next_id.saturating_add(1).max(1);
        self.next_id.to_string()
    }

    fn fallback(&mut self, reason: HerdrErrorCode) {
        self.reader = None;
        self.read_buffer.clear();
        self.writer = None;
        self.mode = HerdrStreamMode::Fallback;
        self.reason = Some(reason);
        self.request_id = None;
    }

    pub fn close(&mut self) {
        self.reader = None;
        self.read_buffer.clear();
        self.writer = None;
        self.request_id = None;
        self.mode = HerdrStreamMode::Closed;
    }

    pub async fn connect(&mut self, deadline: Duration) -> Result<(), HerdrError> {
        if deadline.is_zero() || deadline > Duration::from_secs(120) {
            self.fallback(HerdrErrorCode::InvalidInput);
            return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
        }
        self.reader = None;
        self.read_buffer.clear();
        self.writer = None;
        self.request_id = None;
        self.mode = HerdrStreamMode::Unclassified;
        self.reason = None;
        let path = self.client.socket_path.clone();
        let request_id = self.next_request_id();
        let wire_request_id = request_id.clone();
        let subscriptions = self.subscriptions.clone();
        let result = tokio::time::timeout(deadline, async move {
            let stream = UnixStream::connect(path)
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            let (mut reader, mut writer) = stream.into_split();
            let mut request = serde_json::to_vec(&json!({
                "jsonrpc": "2.0",
                "id": wire_request_id,
                "method": "events.subscribe",
                "params": {"subscriptions": subscriptions},
            }))
            .map_err(|_| HerdrError::new(HerdrErrorCode::Malformed))?;
            request.push(b'\n');
            if request.len() > MAX_LINE_BYTES {
                return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
            }
            writer
                .write_all(&request)
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            writer
                .flush()
                .await
                .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
            let mut read_buffer = Vec::new();
            let ack = read_buffered_line(&mut reader, &mut read_buffer, MAX_LINE_BYTES).await?;
            Ok::<_, HerdrError>((reader, writer, read_buffer, ack))
        })
        .await
        .map_err(|_| HerdrError::new(HerdrErrorCode::Timeout))?;

        let (reader, writer, read_buffer, ack) = match result {
            Ok(value) => value,
            Err(error) => {
                self.fallback(error.kind());
                return Err(error);
            }
        };
        let response: Value = match serde_json::from_slice(&ack) {
            Ok(value) => value,
            Err(_) => {
                self.fallback(HerdrErrorCode::Malformed);
                return Err(HerdrError::new(HerdrErrorCode::Malformed));
            }
        };
        let object = match response.as_object() {
            Some(object) => object,
            None => {
                self.fallback(HerdrErrorCode::InvalidShape);
                return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
            }
        };
        if object
            .get("jsonrpc")
            .is_some_and(|version| version.as_str() != Some("2.0"))
            || object.get("id").and_then(Value::as_str) != Some(request_id.as_str())
        {
            self.fallback(HerdrErrorCode::Unrelated);
            return Err(HerdrError::new(HerdrErrorCode::Unrelated));
        }
        if object.contains_key("error") || !object.contains_key("result") {
            let error = if object.contains_key("error") {
                HerdrErrorCode::Upstream
            } else {
                HerdrErrorCode::MissingResult
            };
            self.fallback(error);
            return Err(HerdrError::new(error));
        }
        self.reader = Some(reader);
        self.writer = Some(writer);
        self.read_buffer = read_buffer;
        self.request_id = Some(request_id);
        self.mode = HerdrStreamMode::Push;
        self.reason = None;
        Ok(())
    }

    pub async fn next_event(&mut self, deadline: Duration) -> Result<Option<BridgeEvent>, HerdrError> {
        if !self.active() {
            return Ok(None);
        }
        if deadline.is_zero() {
            return Ok(None);
        }
        let result = {
            let reader = self.reader.as_mut().expect("active stream has reader");
            tokio::time::timeout(deadline, read_buffered_line(reader, &mut self.read_buffer, MAX_LINE_BYTES)).await
        };
        let line = match result {
            Err(_) => return Ok(None),
            Ok(Err(error)) => {
                self.fallback(error.kind());
                return Err(error);
            }
            Ok(Ok(line)) => line,
        };
        let value: Value = match serde_json::from_slice(&line) {
            Ok(value) => value,
            Err(_) => {
                self.fallback(HerdrErrorCode::Malformed);
                return Err(HerdrError::new(HerdrErrorCode::Malformed));
            }
        };
        if typed_event(&value).is_none() {
            self.fallback(HerdrErrorCode::InvalidShape);
            return Err(HerdrError::new(HerdrErrorCode::InvalidShape));
        }
        Ok(Some(BridgeEvent::HerdrInvalidated))
    }

    pub async fn rebuild(&mut self, deadline: Duration) -> Result<(), HerdrError> {
        self.connect(deadline).await
    }
}

async fn read_buffered_line<R: AsyncRead + Unpin>(
    reader: &mut R,
    buffer: &mut Vec<u8>,
    limit: usize,
) -> Result<Vec<u8>, HerdrError> {
    loop {
        if let Some(newline) = buffer.iter().position(|byte| *byte == b'\n') {
            if newline > limit {
                return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
            }
            let line = buffer[..newline].to_vec();
            buffer.drain(..=newline);
            return Ok(line);
        }
        if buffer.len() > limit {
            return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
        }
        let mut chunk = [0_u8; 4096];
        let read = reader
            .read(&mut chunk)
            .await
            .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
        if read == 0 {
            return Err(HerdrError::new(if buffer.is_empty() {
                HerdrErrorCode::EndOfStream
            } else {
                HerdrErrorCode::Malformed
            }));
        }
        if let Some(newline) = chunk[..read].iter().position(|byte| *byte == b'\n') {
            if buffer.len().saturating_add(newline) > limit {
                return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
            }
            buffer.extend_from_slice(&chunk[..read]);
        } else {
            if buffer.len().saturating_add(read) > limit {
                return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
            }
            buffer.extend_from_slice(&chunk[..read]);
        }
    }
}

async fn read_bounded_line<R: AsyncRead + Unpin>(reader: &mut R, limit: usize) -> Result<Vec<u8>, HerdrError> {
    let mut line = Vec::with_capacity(limit.min(4096));
    let mut chunk = [0_u8; 4096];
    loop {
        let read = reader
            .read(&mut chunk)
            .await
            .map_err(|_| HerdrError::new(HerdrErrorCode::Unavailable))?;
        if read == 0 {
            return Err(HerdrError::new(if line.is_empty() {
                HerdrErrorCode::EndOfStream
            } else {
                HerdrErrorCode::Malformed
            }));
        }
        let newline = chunk[..read].iter().position(|byte| *byte == b'\n');
        let count = newline.unwrap_or(read);
        if line.len().saturating_add(count) > limit {
            return Err(HerdrError::new(HerdrErrorCode::LineTooLong));
        }
        line.extend_from_slice(&chunk[..count]);
        if newline.is_some() {
            return Ok(line);
        }
    }
}

fn validate_identifier(value: &str) -> Result<(), HerdrError> {
    if value.is_empty() || value.len() > 64 || !value.bytes().all(|byte| (0x21..=0x7e).contains(&byte)) {
        return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
    }
    Ok(())
}

fn validate_subscriptions(values: &[Value]) -> Result<Vec<Value>, HerdrError> {
    if values.is_empty() {
        return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
    }
    values
        .iter()
        .map(|value| {
            let object = value
                .as_object()
                .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
            let event = object
                .get("type")
                .and_then(Value::as_str)
                .ok_or_else(|| HerdrError::new(HerdrErrorCode::InvalidShape))?;
            validate_identifier(event)?;
            if event == "*" {
                return Err(HerdrError::new(HerdrErrorCode::InvalidInput));
            }
            Ok(Value::Object(object.clone()))
        })
        .collect()
}

fn typed_event(value: &Value) -> Option<(&str, &Map<String, Value>)> {
    let object = value.as_object()?;
    let event = object.get("event")?.as_str()?;
    let data = object.get("data")?.as_object()?;
    if event.is_empty() || event.bytes().any(|byte| byte < 0x21 || byte == b'\r' || byte == b'\n') {
        return None;
    }
    Some((event, data))
}
