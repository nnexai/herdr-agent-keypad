use herdr_keypad_native::{
    BridgeEvent, BridgeEffect, BridgeError, BridgeOutcome, Coordinator, DeviceFrame, FocusIntent,
    HerdrRequest, SnapshotAck, SourceStatus,
};
use serde_json::json;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixListener;
use tokio::sync::mpsc;

/// The tracer deliberately speaks the production line-oriented boundaries instead of
/// invoking projection, focus, or framing helpers directly.  It is the first red
/// test for the migration seam and remains the narrow end-to-end contract test.
#[tokio::test]
async fn tracer_authoritative_snapshot_ack_then_exact_focus() -> Result<(), BridgeError> {
    let socket_path = std::env::temp_dir().join(format!(
        "herdr-keypad-tracer-{}-{}.sock",
        std::process::id(),
        uuid_suffix()
    ));
    let listener = UnixListener::bind(&socket_path).map_err(BridgeError::io)?;
    let (herdr_events_tx, herdr_events_rx) = mpsc::channel(8);
    let (device_tx, device_rx) = mpsc::channel(8);
    let (effects_tx, mut effects_rx) = mpsc::channel(8);
    let authority = Arc::new(tokio::sync::Notify::new());
    let authority_for_server = Arc::clone(&authority);
    let server = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.map_err(BridgeError::io)?;
        let (read_half, mut write_half) = stream.into_split();
        let mut lines = BufReader::new(read_half).lines();
        while let Some(line) = lines.next_line().await.map_err(BridgeError::io)? {
            let request: serde_json::Value = serde_json::from_str(&line)
                .map_err(|error| BridgeError::protocol(error.to_string()))?;
            match request.get("method").and_then(serde_json::Value::as_str) {
                Some("session.snapshot") => {
                    write_json(&mut write_half, json!({"id": request["id"], "result": {"session": "tracer"}})).await?;
                }
                Some("agent.list") => {
                    write_json(&mut write_half, json!({"id": request["id"], "result": {"agents": [{
                        "pane_id": "pane-a", "terminal_id": "term-a", "workspace_id": "workspace-a",
                        "tab_id": "tab-a", "agent_status": "working", "focused": false, "revision": 7,
                        "state_change_seq": 2, "agent_session": "agent-session-a",
                        "tokens": {"rank": "0", "title": "Agent A", "since": "NOW", "age": "0M"}
                    }]}})).await?;
                }
                Some("workspace.list") => {
                    write_json(&mut write_half, json!({"id": request["id"], "result": {"workspaces": [{
                        "workspace_id": "workspace-a", "label": "repo"
                    }]}})).await?;
                }
                Some("agent.focus") => {
                    assert_eq!(request["params"]["target"], "pane-a");
                    write_json(&mut write_half, json!({"id": request["id"], "result": {
                        "type": "agent_info", "agent": {
                            "pane_id": "pane-a", "terminal_id": "term-a", "workspace_id": "workspace-a",
                            "tab_id": "tab-a", "agent_session": "agent-session-a", "focused": true
                        }
                    }})).await?;
                    authority_for_server.notify_one();
                }
                _ => return Err(BridgeError::protocol("unexpected Herdr method")),
            }
        }
        Ok::<(), BridgeError>(())
    });

    // The test endpoint is a real local socket/PTY adapter pair.  The coordinator
    // consumes only boundary events and emits only typed effects.
    let coordinator = Coordinator::new(
        HerdrRequest::unix_socket(socket_path.clone()),
        herdr_events_rx,
        device_rx,
        effects_tx,
    )?;
    let run = tokio::spawn(coordinator.run());
    herdr_events_tx
        .send(BridgeEvent::HerdrInvalidated)
        .await
        .map_err(|_| BridgeError::channel("Herdr event channel closed"))?;

    let snapshot_effect = next_snapshot(&mut effects_rx).await?;
    let snapshot = match snapshot_effect {
        BridgeEffect::PublishSnapshot(snapshot) => snapshot,
        other => return Err(BridgeError::protocol(format!("expected snapshot, got {other:?}"))),
    };
    assert_eq!(snapshot.agents.len(), 3);
    assert_eq!(snapshot.source_status, SourceStatus::Current);

    device_tx
        .send(DeviceFrame::SnapshotAck(SnapshotAck::accepted(&snapshot)))
        .await
        .map_err(|_| BridgeError::channel("device channel closed"))?;
    device_tx
        .send(DeviceFrame::FocusIntent(FocusIntent::from_agent(
            "action-a",
            &snapshot.agents[0],
            &snapshot,
        )))
        .await
        .map_err(|_| BridgeError::channel("device channel closed"))?;

    let focus = next_focus(&mut effects_rx).await?;
    assert_eq!(focus.outcome, BridgeOutcome::Accepted);
    assert_eq!(focus.action_id, "action-a");
    assert_eq!(focus.host_epoch, snapshot.host_epoch);
    assert_eq!(focus.snapshot_revision, snapshot.snapshot_revision);
    assert_eq!(focus.slot, 0);
    assert_eq!(focus.entry_id, "pane-a");
    assert_eq!(focus.identity.pane_id, "pane-a");
    assert_eq!(focus.identity.source_revision, 7);
    assert_eq!(focus.boot_id, snapshot.boot_id);
    assert_eq!(focus.session_id, snapshot.session_id);
    assert!(tokio::time::timeout(std::time::Duration::from_secs(1), authority.notified())
        .await
        .is_ok());

    run.abort();
    let _ = run.await;
    let server_result = tokio::time::timeout(std::time::Duration::from_secs(1), server)
        .await
        .map_err(|_| BridgeError::protocol("Herdr server did not stop"))?
        .map_err(|error| BridgeError::protocol(format!("Herdr server failed: {error}")))?;
    server_result?;
    let _ = std::fs::remove_file(socket_path);
    Ok(())
}
#[tokio::test]
async fn tracer_herdr_authority_cancellation_clears_pending_work() -> Result<(), BridgeError> {
    let (events_tx, events_rx) = mpsc::channel(8);
    let (_device_tx, device_rx) = mpsc::channel(8);
    let (effects_tx, mut effects_rx) = mpsc::channel(8);
    let coordinator = Coordinator::new(
        HerdrRequest::unix_socket(std::env::temp_dir().join("herdr-keypad-no-authority.sock")),
        events_rx,
        device_rx,
        effects_tx,
    )?;
    let run = tokio::spawn(coordinator.run());
    events_tx
        .send(BridgeEvent::AuthorityCancelled)
        .await
        .map_err(|_| BridgeError::channel("cancellation channel closed"))?;
    let result = tokio::time::timeout(std::time::Duration::from_secs(1), run)
        .await
        .map_err(|_| BridgeError::protocol("coordinator did not exit"))?
        .map_err(|error| BridgeError::protocol(format!("coordinator failed: {error}")))?;
    result?;
    assert_eq!(effects_rx.recv().await, Some(BridgeEffect::AuthorityEnded));
    Ok(())
}

async fn next_snapshot(
    effects: &mut mpsc::Receiver<BridgeEffect>,
) -> Result<BridgeEffect, BridgeError> {
    tokio::time::timeout(std::time::Duration::from_secs(1), effects.recv())
        .await
        .map_err(|_| BridgeError::protocol("snapshot effect timeout"))?
        .ok_or_else(|| BridgeError::channel("effect channel closed"))
}

async fn next_focus(
    effects: &mut mpsc::Receiver<BridgeEffect>,
) -> Result<herdr_keypad_native::FocusResult, BridgeError> {
    loop {
        match next_snapshot(effects).await? {
            BridgeEffect::FocusResult(result) => return Ok(result),
            BridgeEffect::PublishSnapshot(_) => continue,
            other => return Err(BridgeError::protocol(format!("unexpected effect {other:?}"))),
        }
    }
}

async fn write_json(
    stream: &mut tokio::net::unix::OwnedWriteHalf,
    value: serde_json::Value,
) -> Result<(), BridgeError> {
    let mut line = serde_json::to_vec(&value).map_err(|error| BridgeError::protocol(error.to_string()))?;
    line.push(b'\n');
    stream.write_all(&line).await.map_err(BridgeError::io)
}

fn uuid_suffix() -> String {
    format!("{}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos())
}
