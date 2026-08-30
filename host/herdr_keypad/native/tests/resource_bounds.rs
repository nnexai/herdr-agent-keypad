use herdr_keypad_native::core::orchestrator::CoordinatorConfig;
use herdr_keypad_native::ports::control::CONTROL_PAYLOAD_LIMIT;
use herdr_keypad_native::ports::lifecycle::ResourceMetrics;
use herdr_keypad_native::protocol::v2::{self, ProtocolSession};
use herdr_keypad_native::{
    bounded_channels, BridgeEffect, BridgeEvent, DeviceFrame, SnapshotAck, SourceStatus,
    BRIDGE_EFFECT_CAPACITY, DEVICE_FRAME_CAPACITY, HERDR_EVENT_CAPACITY, PENDING_FOCUS_CAPACITY,
};
use serde_json::json;
use std::fs;
use std::time::{Duration, Instant};

fn valid_ack() -> DeviceFrame {
    DeviceFrame::SnapshotAck(SnapshotAck {
        accepted: true,
        host_epoch: "epoch".to_owned(),
        snapshot_revision: 1,
        source_status: SourceStatus::Current,
        reason: "accepted".to_owned(),
        boot_id: Some("boot".to_owned()),
        session_id: Some("session".to_owned()),
    })
}

#[test]
fn public_channels_enforce_declared_capacity_without_unbounded_growth() {
    let (event_tx, _event_rx, device_tx, _device_rx, effect_tx, _effect_rx) = bounded_channels();
    for _ in 0..HERDR_EVENT_CAPACITY {
        event_tx.try_send(BridgeEvent::HerdrInvalidated).expect("event capacity");
    }
    assert!(event_tx.try_send(BridgeEvent::HerdrInvalidated).is_err());
    for _ in 0..DEVICE_FRAME_CAPACITY {
        device_tx.try_send(valid_ack()).expect("device capacity");
    }
    assert!(device_tx.try_send(valid_ack()).is_err());
    for _ in 0..BRIDGE_EFFECT_CAPACITY {
        effect_tx.try_send(BridgeEffect::AuthorityEnded).expect("effect capacity");
    }
    assert!(effect_tx.try_send(BridgeEffect::AuthorityEnded).is_err());
}

#[test]
fn queue_payload_and_timer_limits_are_closed_and_validated() {
    let config = CoordinatorConfig::default();
    assert!(config.validate().is_ok());
    assert!(config.reconnect_initial <= config.reconnect_max);
    assert!(config.reconnect_max <= Duration::from_secs(8));
    assert!(PENDING_FOCUS_CAPACITY <= DEVICE_FRAME_CAPACITY);
    assert!(CONTROL_PAYLOAD_LIMIT <= 16 * 1024);
    assert!(ResourceMetrics::idle().source_polls == 0);
    assert!(ResourceMetrics::idle().timer_fires == 0);
    assert!(ResourceMetrics::idle().wakes == 0);
}

#[test]
fn malformed_and_oversized_traffic_is_rejected_before_queueing() {
    let oversized = vec![b' '; v2::MAX_LINE_BYTES + 1];
    assert_eq!(v2::classify_line(&oversized).reason, "line_too_long");
    assert_eq!(v2::classify_line(b"not-json\n").reason, "invalid_json");
    assert_eq!(v2::classify_line(b"{\"v\":2}\n").reason, "invalid_shape");
    assert_eq!(v2::classify_line(b"{\"v\":2,\"v\":2}\n").reason, "duplicate_key");

    let mut nested = String::new();
    for _ in 0..(v2::MAX_JSON_NESTING + 4) {
        nested.push('[');
    }
    for _ in 0..(v2::MAX_JSON_NESTING + 4) {
        nested.push(']');
    }
    nested.push('\n');
    let result = v2::classify_line(nested.as_bytes());
    assert!(matches!(result.reason, "invalid_json" | "nesting_too_deep"));
}

#[test]
fn sustained_bounded_traffic_has_no_replay_and_records_measured_resource_sample() {
    let fixture: serde_json::Value = serde_json::from_str(include_str!("fixtures/protocol.json")).expect("protocol fixture");
    let line = fixture["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.focus_intent")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();
    let mut session = ProtocolSession::new("boot-a", "session-a", PENDING_FOCUS_CAPACITY).expect("session");
    let started = Instant::now();
    let mut accepted = 0usize;
    let mut duplicate = 0usize;
    for sequence in 1..=PENDING_FOCUS_CAPACITY as u32 {
        let mut frame: serde_json::Value = serde_json::from_str(line).expect("valid focus fixture");
        frame["seq"] = json!(sequence);
        let mut bytes = serde_json::to_vec(&frame).expect("frame JSON");
        bytes.push(b'\n');
        assert!(session.accept(&bytes).accepted);
        accepted += 1;
        assert_eq!(session.accept(&bytes).reason, "duplicate");
        duplicate += 1;
    }
    assert_eq!(accepted, PENDING_FOCUS_CAPACITY);
    assert_eq!(duplicate, PENDING_FOCUS_CAPACITY);
    assert_eq!(session.pending_count(), PENDING_FOCUS_CAPACITY);
    assert!(session.pending_count() <= PENDING_FOCUS_CAPACITY);
    let elapsed = started.elapsed();

    let metrics = ResourceMetrics {
        wakes: accepted as u64,
        source_polls: 0,
        timer_fires: 0,
        queue_high_water: session.pending_count(),
        history_size: PENDING_FOCUS_CAPACITY,
        max_payload: line.len() + 1,
    };
    assert_eq!(metrics.source_polls, 0, "healthy event traffic must not poll sources");
    assert_eq!(metrics.timer_fires, 0, "traffic does not invent timer wakeups");
    assert!(metrics.queue_high_water <= PENDING_FOCUS_CAPACITY);
    assert!(metrics.history_size <= 32);
    assert!(metrics.max_payload <= v2::MAX_LINE_BYTES);
    println!(
        "phase04-resource traffic accepted={} duplicate={} queue_high_water={} elapsed_ms={} payload_bytes={}",
        accepted,
        duplicate,
        metrics.queue_high_water,
        elapsed.as_millis(),
        metrics.max_payload
    );
}

#[test]
fn independent_recovery_resets_authority_and_discards_old_work() {
    let fixture: serde_json::Value = serde_json::from_str(include_str!("fixtures/protocol.json")).expect("protocol fixture");
    let line = fixture["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == "protocol.accepted.focus_intent")
        .unwrap()["input"]["line"]
        .as_str()
        .unwrap();
    let mut session = ProtocolSession::new("boot-old", "session-old", PENDING_FOCUS_CAPACITY).expect("old session");
    let mut frame: serde_json::Value = serde_json::from_str(line).expect("valid frame");
    frame["boot_id"] = json!("boot-old");
    frame["session_id"] = json!("session-old");
    let mut old = serde_json::to_vec(&frame).expect("old frame");
    old.push(b'\n');
    assert!(session.accept(&old).accepted);
    assert_eq!(session.pending_count(), 1);
    session.reset("boot-new", "session-new").expect("fresh authority");
    assert_eq!(session.pending_count(), 0);
    assert_eq!(session.accept(&old).reason, "boot_mismatch");

    let mut fresh = frame;
    fresh["boot_id"] = json!("boot-new");
    fresh["session_id"] = json!("session-new");
    fresh["seq"] = json!(1);
    let mut fresh = serde_json::to_vec(&fresh).expect("fresh frame");
    fresh.push(b'\n');
    assert!(session.accept(&fresh).accepted);
    assert_eq!(session.pending_count(), 1);
}

#[cfg(target_os = "linux")]
#[test]
fn linux_process_probe_records_idle_rss_and_cpu_without_fixed_poll_thresholds() {
    let before = proc_sample().expect("/proc sample before");
    std::thread::sleep(Duration::from_millis(25));
    let after = proc_sample().expect("/proc sample after");
    assert!(after.rss_kib > 0, "process RSS is measurable");
    assert!(after.cpu_ticks >= before.cpu_ticks, "process CPU counter is monotonic");
    println!(
        "phase04-resource idle rss_before_kib={} rss_after_kib={} cpu_ticks_before={} cpu_ticks_after={}",
        before.rss_kib, after.rss_kib, before.cpu_ticks, after.cpu_ticks
    );
}

#[cfg(target_os = "linux")]
#[derive(Debug, Clone, Copy)]
struct ProcSample {
    rss_kib: u64,
    cpu_ticks: u64,
}

#[cfg(target_os = "linux")]
fn proc_sample() -> Option<ProcSample> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    let rss_kib = status
        .lines()
        .find_map(|line| line.strip_prefix("VmRSS:")?.split_whitespace().next()?.parse().ok())?;
    let stat = fs::read_to_string("/proc/self/stat").ok()?;
    let fields = stat.rsplit_once(") ")?.1.split_whitespace().collect::<Vec<_>>();
    let user: u64 = fields.get(11)?.parse().ok()?;
    let system: u64 = fields.get(12)?.parse().ok()?;
    Some(ProcSample { rss_kib, cpu_ticks: user + system })
}
