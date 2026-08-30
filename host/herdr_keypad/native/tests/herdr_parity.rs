#[path = "../src/ports/herdr.rs"]
mod herdr;

use herdr::{HerdrClient, HerdrErrorCode, HerdrEventStream, HerdrStreamMode, MAX_LINE_BYTES};
use herdr_keypad_native::BridgeEvent;
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

async fn serve_complete(path: PathBuf, requests: Arc<Mutex<Vec<Value>>>) {
    let listener = UnixListener::bind(&path).expect("bind Herdr socket");
    for _ in 0..4 {
        let (mut stream, request) = accept_request(&listener).await;
        requests.lock().expect("request lock").push(request.clone());
        let id = request["id"].clone();
        let response = match request["method"].as_str().expect("method") {
            "session.snapshot" => json!({"jsonrpc":"2.0", "id":id, "result":{"snapshot":{"version":"0.8.2"}}}),
            "agent.list" => json!({"jsonrpc":"2.0", "id":id, "result":{"agents":[{"pane_id":"pane-1"}]}}),
            "workspace.list" => json!({"jsonrpc":"2.0", "id":id, "result":{"workspaces":[{"workspace_id":"workspace-1"}]}}),
            "agent.focus" => json!({"jsonrpc":"2.0", "id":id, "result":{"agent":{"focused":true,"terminal_id":"terminal-1","agent_session":"session-1"}}}),
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
    assert!(requests.windows(2).all(|pair| pair[0]["id"] != pair[1]["id"]));
    let _ = std::fs::remove_file(path);
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
        let ack = json!({"jsonrpc":"2.0","id":id,"result":{"subscribed":true}});
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
