#[path = "../src/core/model.rs"]
mod model;
#[path = "../src/core/projection.rs"]
mod projection;
#[path = "../src/core/focus.rs"]
mod focus;

#[path = "../src/ports/herdr.rs"]
mod herdr;

use focus::{FocusError, FocusExecutor, HerdrPort as FocusHerdrPort};
use herdr::{HerdrClient, HerdrErrorCode, HerdrEventStream, HerdrStreamMode, MAX_LINE_BYTES};
use herdr_keypad_native::BridgeEvent;
use model::{FocusIntent, FocusResult, FocusStatus};
use projection::InboxProjection;
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};

fn socket_path(label: &str) -> PathBuf {
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("herdr-parity-{label}-{}-{suffix}.sock", std::process::id()))
}

async fn accept_request(listener: &UnixListener) -> (UnixStream, Value) {
    let (stream, _) = listener.accept().await.expect("request connection");
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).await.expect("request line");
    (reader.into_inner(), serde_json::from_str(&line).expect("request JSON"))
}

fn structured_agent(session_agent: &str) -> Value {
    json!({
        "agent": "omp",
        "agent_session": {
            "source": "herdr:omp",
            "agent": session_agent,
            "kind": "path",
            "value": "/redacted/session.jsonl"
        },
        "agent_status": "working",
        "cwd": "repo",
        "focused": true,
        "pane_id": "pane-1",
        "revision": 7,
        "state_change_seq": 3,
        "tab_id": "workspace-1:tab-1",
        "terminal_id": "terminal-1",
        "title": "Focused agent",
        "tokens": {"rank": "0", "title": "Focused agent"},
        "workspace_id": "workspace-1"
    })
}

struct ClientFocusPort<'a> {
    client: &'a mut HerdrClient,
}

impl FocusHerdrPort for ClientFocusPort<'_> {
    fn complete_read(&mut self) -> Result<Vec<Value>, FocusError> {
        tokio::runtime::Handle::current()
            .block_on(self.client.agent_list())
            .map_err(|error| FocusError::failed(error.code()))
    }

    fn focus(&mut self, pane_id: &str) -> Result<Value, FocusError> {
        tokio::runtime::Handle::current()
            .block_on(self.client.focus_pane(pane_id.to_owned()))
            .map(|ack| {
                json!({
                    "pane_id": ack.pane_id,
                    "terminal_id": ack.terminal_id,
                    "agent_session": ack.agent_session,
                    "focused": ack.focused,
                })
            })
            .map_err(|error| FocusError::failed(error.code()))
    }
}

async fn serve_focus_authorization(
    listener: UnixListener,
    listed_agent: Value,
    focused_agent: Value,
) {
    for expected_method in ["agent.list", "agent.focus"] {
        let (mut stream, request) = accept_request(&listener).await;
        assert_eq!(request["method"], expected_method);
        let id = request["id"].clone();
        let result = match expected_method {
            "agent.list" => json!({"agents": [listed_agent.clone()]}),
            "agent.focus" => json!({"agent": focused_agent.clone()}),
            _ => unreachable!(),
        };
        let mut bytes = serde_json::to_vec(&json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": result,
        }))
        .expect("response JSON");
        bytes.push(b'\n');
        stream.write_all(&bytes).await.expect("response write");
    }
}

async fn authorize_focus(label: &str, listed_agent: Value, focused_agent: Value) -> FocusResult {
    let path = socket_path(label);
    let listener = UnixListener::bind(&path).expect("bind Herdr socket");
    let server = tokio::spawn(serve_focus_authorization(
        listener,
        listed_agent.clone(),
        focused_agent,
    ));

    let mut projection = InboxProjection::new("epoch").expect("projection");
    let acknowledged = projection
        .refresh(
            std::slice::from_ref(&listed_agent),
            &[json!({"workspace_id": "workspace-1", "label": "repo"})],
        )
        .expect("current projection");
    let mut binding = projection.binding(0).expect("focused binding");
    binding.identity.workspace_id.clear();
    binding.identity.tab_id.clear();
    let intent = FocusIntent::new("action-already-focused", binding);
    let mut client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");

    let outcome = tokio::task::block_in_place(|| {
        let mut port = ClientFocusPort { client: &mut client };
        FocusExecutor::new().execute(&projection, &acknowledged, &intent, &mut port)
    });
    let result = FocusExecutor::new().result(intent, &outcome);
    server.await.expect("server task");
    let _ = std::fs::remove_file(path);
    result
}

async fn serve_complete(path: PathBuf, requests: Arc<Mutex<Vec<Value>>>) {
    let listener = UnixListener::bind(&path).expect("bind Herdr socket");
    for _ in 0..4 {
        let (mut stream, request) = accept_request(&listener).await;
        requests.lock().expect("request lock").push(request.clone());
        let id = request["id"].clone();
        let response = match request["method"].as_str().expect("method") {
            "session.snapshot" => json!({"id":id, "result":{"snapshot":{"version":"0.8.2"}}}),
            "agent.list" => json!({"id":id, "result":{"agents":[{"pane_id":"pane-1"}]}}),
            "workspace.list" => json!({"id":id, "result":{"workspaces":[{"workspace_id":"workspace-1"}]}}),
            "agent.focus" => json!({"id":id, "result":{"agent":{"focused":true,"terminal_id":"terminal-1","agent_session":"session-1"}}}),
            method => panic!("unexpected Herdr method: {method}"),
        };
        let mut bytes = serde_json::to_vec(&response).expect("response JSON");
        bytes.push(b'\n');
        stream.write_all(&bytes).await.expect("response write");
    }
}

#[tokio::test]
async fn complete_reads_correlate_ids_and_focus_is_the_only_write() {
    let path = socket_path("complete");
    let requests = Arc::new(Mutex::new(Vec::new()));
    let server = tokio::spawn(serve_complete(path.clone(), requests.clone()));
    tokio::task::yield_now().await;
    let mut client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");

    let complete = client.read_complete().await.expect("complete read");
    assert_eq!(complete.agents.len(), 1);
    assert_eq!(complete.workspaces.len(), 1);
    let focus = client.focus_pane("pane-1").await.expect("focus");
    assert!(focus.focused);
    assert_eq!(focus.pane_id, "pane-1");

    server.await.expect("server task");
    let requests = requests.lock().expect("request lock");
    assert_eq!(
        requests
            .iter()
            .map(|request| request["method"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["session.snapshot", "agent.list", "workspace.list", "agent.focus"]
    );
    assert_eq!(requests[3]["params"], json!({"target":"pane-1"}));
    assert!(requests.iter().all(|request| request["id"].is_string()));
    assert!(requests.windows(2).all(|pair| pair[0]["id"] != pair[1]["id"]));
    let _ = std::fs::remove_file(path);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn already_focused_structured_session_is_authorized() {
    let agent = structured_agent("omp");
    let result = authorize_focus("already-focused", agent.clone(), agent).await;

    assert_eq!(result.outcome, FocusStatus::Accepted);
    assert!(result.focused);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn different_structured_session_remains_rejected() {
    let result = authorize_focus(
        "different-session",
        structured_agent("omp"),
        structured_agent("different-agent"),
    )
    .await;

    assert_eq!(result.outcome, FocusStatus::SessionChanged);
    assert!(!result.focused);
}

#[tokio::test]
async fn malformed_unrelated_and_oversized_lines_fail_before_unbounded_growth() {
    let path = socket_path("malformed");
    let listener = UnixListener::bind(&path).expect("bind socket");
    let malformed = tokio::spawn(async move {
        let (mut stream, _) = accept_request(&listener).await;
        stream
            .write_all(b"{\"jsonrpc\":\"2.0\",\"id\":999,\"result\":{}}\n")
            .await
            .expect("write response");
        let (mut stream, _) = accept_request(&listener).await;
        stream.write_all(b"x\n").await.expect("write malformed");
        let (mut stream, _) = accept_request(&listener).await;
        let chunk = vec![b'x'; MAX_LINE_BYTES + 1];
        stream.write_all(&chunk).await.expect("write oversized");
        stream.write_all(b"\n").await.expect("write newline");
    });
    let mut client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");
    let error = client.session_snapshot().await.expect_err("unrelated response");
    assert_eq!(error.kind(), HerdrErrorCode::Unrelated);
    let error = client.session_snapshot().await.expect_err("malformed response");
    assert_eq!(error.kind(), HerdrErrorCode::Malformed);
    let error = client.session_snapshot().await.expect_err("oversized response");
    assert_eq!(error.kind(), HerdrErrorCode::LineTooLong);
    malformed.await.expect("server task");
    let _ = std::fs::remove_file(path);
}

#[tokio::test]
async fn correlated_subscribe_ack_admits_only_typed_invalidation_events() {
    let path = socket_path("events");
    let listener = UnixListener::bind(&path).expect("bind socket");
    let server = tokio::spawn(async move {
        let (mut stream, request) = accept_request(&listener).await;
        assert_eq!(request["method"], "events.subscribe");
        let id = request["id"].clone();
        assert!(request["id"].is_string());
        let ack = json!({"id":id,"result":{"subscribed":true}});
        let mut bytes = serde_json::to_vec(&ack).expect("ack JSON");
        bytes.push(b'\n');
        bytes.extend_from_slice(b"{\"event\":\"pane.updated\",\"data\":{\"pane_id\":\"private\"}}\n");
        stream.write_all(&bytes).await.expect("event stream");
    });
    let client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");
    let mut stream = HerdrEventStream::new(client);
    stream.connect(Duration::from_secs(1)).await.expect("subscribe");
    assert_eq!(stream.mode(), HerdrStreamMode::Push);
    assert!(stream.active());
    assert_eq!(
        stream.next_event(Duration::from_secs(1)).await.expect("event"),
        Some(BridgeEvent::HerdrInvalidated)
    );
    server.await.expect("server task");
    stream.close();
    assert_eq!(stream.mode(), HerdrStreamMode::Closed);
    let _ = std::fs::remove_file(path);
}

#[tokio::test]
async fn healthy_push_idle_is_not_fallback_but_eof_is_recoverable() {
    let path = socket_path("idle");
    let listener = UnixListener::bind(&path).expect("bind socket");
    let server = tokio::spawn(async move {
        let (mut stream, request) = accept_request(&listener).await;
        let ack = json!({"jsonrpc":"2.0","id":request["id"],"result":{"subscribed":true}});
        let mut bytes = serde_json::to_vec(&ack).expect("ack JSON");
        bytes.push(b'\n');
        stream.write_all(&bytes).await.expect("ack");
        stream.flush().await.expect("flush ack");
        tokio::time::sleep(Duration::from_millis(100)).await;
    });
    let client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");
    let mut stream = HerdrEventStream::new(client);
    stream.connect(Duration::from_secs(1)).await.expect("subscribe");
    assert_eq!(stream.next_event(Duration::from_millis(10)).await.expect("idle"), None);
    assert_eq!(stream.mode(), HerdrStreamMode::Push);
    assert!(stream.active());
    stream.close();
    server.abort();
    let _ = server.await;
    let _ = std::fs::remove_file(path);

    let path = socket_path("eof");
    let listener = UnixListener::bind(&path).expect("bind socket");
    let server = tokio::spawn(async move {
        let (mut stream, request) = accept_request(&listener).await;
        let ack = json!({"jsonrpc":"2.0","id":request["id"],"result":{"subscribed":true}});
        let mut bytes = serde_json::to_vec(&ack).expect("ack JSON");
        bytes.push(b'\n');
        stream.write_all(&bytes).await.expect("ack");
        stream.flush().await.expect("flush ack");
    });
    let client = HerdrClient::new(&path, Duration::from_secs(1)).expect("client");
    let mut stream = HerdrEventStream::new(client);
    stream.connect(Duration::from_secs(1)).await.expect("subscribe");
    let error = stream.next_event(Duration::from_secs(1)).await.expect_err("EOF");
    assert_eq!(error.kind(), HerdrErrorCode::EndOfStream);
    assert_eq!(stream.mode(), HerdrStreamMode::Fallback);
    assert!(stream.fallback_eligible());
    server.await.expect("server task");
    let _ = std::fs::remove_file(path);
}
