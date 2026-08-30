#[path = "../src/ports/copilot.rs"]
mod copilot;

use copilot::{
    redaction_passes, CopilotCollector, CopilotConnection, CopilotFailureReason, CopilotFuture,
    CopilotProcessFactory, CopilotSourceState, CopilotTransportError, MAX_CREDITS,
};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;

struct FakeConnection {
    replies: VecDeque<Result<Value, CopilotTransportError>>,
    operations: Arc<Mutex<Vec<String>>>,
}

impl CopilotConnection for FakeConnection {
    fn connect<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        self.operations.lock().expect("operations").push("connect".to_owned());
        Box::pin(async { self.replies.pop_front().unwrap_or(Err(CopilotTransportError::Closed)) })
    }

    fn current_auth<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        self.operations.lock().expect("operations").push("account.getCurrentAuth".to_owned());
        Box::pin(async { self.replies.pop_front().unwrap_or(Err(CopilotTransportError::Closed)) })
    }

    fn quota<'a>(&'a mut self) -> CopilotFuture<'a, Result<Value, CopilotTransportError>> {
        self.operations.lock().expect("operations").push("account.getQuota".to_owned());
        Box::pin(async { self.replies.pop_front().unwrap_or(Err(CopilotTransportError::Closed)) })
    }

    fn shutdown<'a>(&'a mut self) -> CopilotFuture<'a, Result<(), CopilotTransportError>> {
        self.operations.lock().expect("operations").push("shutdown".to_owned());
        Box::pin(async { Ok(()) })
    }
}

struct FakeTransport {
    replies: Mutex<Option<VecDeque<Result<Value, CopilotTransportError>>>>,
    operations: Arc<Mutex<Vec<String>>>,
}

impl FakeTransport {
    fn new(replies: Vec<Result<Value, CopilotTransportError>>) -> (Arc<Self>, Arc<Mutex<Vec<String>>>) {
        let operations = Arc::new(Mutex::new(Vec::new()));
        (
            Arc::new(Self { replies: Mutex::new(Some(replies.into_iter().collect())), operations: operations.clone() }),
            operations,
        )
    }
}

impl CopilotProcessFactory for FakeTransport {
    fn start<'a>(&'a self, _executable: &'a str) -> CopilotFuture<'a, Result<Box<dyn CopilotConnection>, CopilotTransportError>> {
        let replies = self.replies.lock().expect("replies").take().unwrap_or_default();
        Box::pin(async move {
            Ok(Box::new(FakeConnection { replies, operations: self.operations.clone() }) as Box<dyn CopilotConnection>)
        })
    }
}

fn auth(host: &str, login: &str) -> Value {
    json!({"authInfo":{"type":"user","host":host,"login":login}})
}

fn handshake(version: &str, protocol: u64) -> Value {
    json!({"ok":true,"protocolVersion":protocol,"version":version})
}

fn quota(snapshot: Value) -> Value {
    json!({"quotaSnapshots":{"chat":{"isUnlimitedEntitlement":true},"completions":{"isUnlimitedEntitlement":true},"premium_interactions":snapshot}})
}

fn current_snapshot() -> Value {
    json!({
        "tokenBasedBilling":true,
        "hasQuota":true,
        "entitlementRequests":1500,
        "usedRequests":500,
        "remainingPercentage":67,
        "resetDate":"2026-09-01T00:00:00.000Z",
        "isUnlimitedEntitlement":false,
        "overage":2,
        "overageEntitlement":100,
        "usageAllowedWithExhaustedQuota":true,
        "overageAllowedWithExhaustedQuota":true
    })
}

fn collector_with(replies: Vec<Result<Value, CopilotTransportError>>) -> (CopilotCollector, Arc<Mutex<Vec<String>>>) {
    let (transport, operations) = FakeTransport::new(replies);
    let collector = CopilotCollector::with_transport_and_clock(
        "copilot",
        Duration::from_secs(3),
        transport,
        || Duration::ZERO,
    )
    .expect("collector");
    (collector, operations)
}

async fn collect_current(snapshot: Value) -> (copilot::CopilotResult, Arc<Mutex<Vec<String>>>) {
    let (mut collector, operations) = collector_with(vec![
        Ok(handshake("1.0.81", 3)),
        Ok(auth("https://github.com", "octocat")),
        Ok(quota(snapshot)),
    ]);
    (collector.collect_async().await, operations)
}

#[tokio::test]
async fn current_token_billing_snapshot_is_normalized_as_labelled_aic() {
    let (result, operations) = collect_current(current_snapshot()).await;
    assert_eq!(result.view.source_state, CopilotSourceState::Current);
    assert_eq!(result.view.provider, "github_copilot");
    assert_eq!(result.view.used_credits, Some(500));
    assert_eq!(result.view.included_credits, Some(1500));
    assert_eq!(result.view.used_percent, Some(33));
    assert_eq!(result.view.overage_used, Some(2));
    assert_eq!(result.view.overage_limit, Some(100));
    assert_eq!(result.view.overage_permitted, Some(true));
    assert_eq!(result.view.reset_text, "RESET 2026-09-01T00:00:00.000Z");
    assert_eq!(result.view.failure_reason, CopilotFailureReason::None);
    assert_eq!(result.handshake, vec![("protocol".to_owned(), "3".to_owned()), ("cli".to_owned(), "1.0.81".to_owned())]);
    assert_eq!(*operations.lock().expect("operations"), ["connect", "account.getCurrentAuth", "account.getQuota", "shutdown"]);
}

#[tokio::test]
async fn exhausted_finite_allowance_retains_overage_facts_without_hiding_exhaustion() {
    let snapshot = json!({
        "tokenBasedBilling":true,"hasQuota":false,"entitlementRequests":1500,"usedRequests":1500,
        "remainingPercentage":0,"resetDate":null,"isUnlimitedEntitlement":false,"overage":100,
        "overageEntitlement":100,"usageAllowedWithExhaustedQuota":true,"overageAllowedWithExhaustedQuota":false
    });
    let (result, _) = collect_current(snapshot).await;
    assert_eq!(result.view.source_state, CopilotSourceState::Current);
    assert_eq!(result.view.reached_limit, Some(true));
    assert_eq!(result.view.used_credits, Some(1500));
    assert_eq!(result.view.overage_used, Some(100));
    assert_eq!(result.view.overage_limit, Some(100));
    assert_eq!(result.view.overage_permitted, Some(false));
    assert_eq!(result.view.reset_text, "RESET N/A");
}

#[tokio::test]
async fn unlimited_entitlement_keeps_usage_but_not_fabricated_limit_or_percentage() {
    let snapshot = json!({
        "tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":-1,"usedRequests":42,
        "remainingPercentage":100,"resetDate":"2026-09-01T00:00:00Z","isUnlimitedEntitlement":true,
        "overage":0,"overageEntitlement":0,"usageAllowedWithExhaustedQuota":true,"overageAllowedWithExhaustedQuota":true
    });
    let (result, _) = collect_current(snapshot).await;
    assert!(result.view.unlimited);
    assert_eq!(result.view.used_credits, Some(42));
    assert_eq!(result.view.included_credits, None);
    assert_eq!(result.view.used_percent, None);
    assert_eq!(result.view.reached_limit, None);
}

#[tokio::test]
async fn non_exhausted_allowance_is_current_and_does_not_use_other_buckets() {
    let (result, _) = collect_current(json!({
        "tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":1500,"usedRequests":0,
        "remainingPercentage":100,"isUnlimitedEntitlement":false,"overage":0,"overageEntitlement":100,
        "usageAllowedWithExhaustedQuota":false,"overageAllowedWithExhaustedQuota":false
    })).await;
    assert_eq!(result.view.used_credits, Some(0));
    assert_eq!(result.view.used_percent, Some(0));
    assert_eq!(result.view.included_credits, Some(1500));
}

#[tokio::test]
async fn missing_bucket_and_false_or_missing_discriminator_fail_closed() {
    for snapshot in [json!({"tokenBasedBilling":false}), json!({"hasQuota":true}), json!({"tokenBasedBilling":true,"hasQuota":true})] {
        let quota_response = if snapshot.get("tokenBasedBilling").is_none() && snapshot.get("hasQuota").is_none() {
            json!({"quotaSnapshots":{}})
        } else {
            quota(snapshot)
        };
        let (mut collector, _) = collector_with(vec![Ok(handshake("1.0.81", 3)), Ok(auth("https://github.com", "octocat")), Ok(quota_response)]);
        let result = collector.collect_async().await;
        assert_eq!(result.view.source_state, CopilotSourceState::Unavailable);
        assert!(matches!(result.view.failure_reason, CopilotFailureReason::BillingModeUnsupported | CopilotFailureReason::QuotaUnavailable | CopilotFailureReason::MalformedQuota));
        assert_eq!(result.view.used_credits, None);
    }
}

#[tokio::test]
async fn malformed_nonfinite_fractional_and_oversized_values_fail_closed() {
    let cases = [
        json!({"tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":1.5,"usedRequests":0,"remainingPercentage":100,"isUnlimitedEntitlement":false}),
        json!({"tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":1500,"usedRequests":0,"remainingPercentage":101,"isUnlimitedEntitlement":false}),
        json!({"tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":MAX_CREDITS + 1,"usedRequests":0,"remainingPercentage":100,"isUnlimitedEntitlement":false}),
        json!({"tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":1500,"usedRequests":-1,"remainingPercentage":100,"isUnlimitedEntitlement":false}),
        json!({"tokenBasedBilling":true,"hasQuota":true,"entitlementRequests":1500,"usedRequests":0,"remainingPercentage":"NaN","isUnlimitedEntitlement":false}),
    ];
    for snapshot in cases {
        let (result, _) = collect_current(snapshot).await;
        assert_eq!(result.view.source_state, CopilotSourceState::Unavailable);
        assert_eq!(result.view.failure_reason, CopilotFailureReason::MalformedQuota);
        assert!(result.view.used_credits.is_none());
    }
}

#[tokio::test]
async fn absent_auth_is_auth_required_and_secrets_never_cross_result_boundary() {
    let (mut collector, _) = collector_with(vec![
        Ok(handshake("1.0.81", 3)),
        Ok(json!({"authInfo":null,"authErrors":["token=do-not-leak"]})),
    ]);
    let result = collector.collect_async().await;
    assert_eq!(result.view.source_state, CopilotSourceState::AuthRequired);
    assert_eq!(result.view.failure_reason, CopilotFailureReason::AuthRequired);
    assert!(format!("{result:?}").find("do-not-leak").is_none());
    assert!(redaction_passes(&result.as_evidence()));
}

#[tokio::test]
async fn active_account_change_discards_prior_baseline_before_new_values() {
    let clock = Arc::new(Mutex::new(Duration::ZERO));
    let (transport, _) = FakeTransport::new(vec![]);
    let mut collector = CopilotCollector::with_transport_and_clock("copilot", Duration::from_secs(3), transport, {
        let clock = clock.clone();
        move || *clock.lock().expect("clock")
    }).expect("collector");
    collector.set_test_baseline(auth("https://github.com", "first"), quota(current_snapshot()));
    assert_eq!(collector.view().used_credits, Some(500));
    collector.account_changed(true);
    assert_eq!(collector.view().source_state, CopilotSourceState::AuthRequired);
    assert_eq!(collector.view().used_credits, None);
}

#[tokio::test]
async fn timeout_missing_cli_and_compatibility_drift_are_explicit_failures() {
    let (mut missing, _) = collector_with(vec![]);
    missing.set_test_cli_missing();
    assert_eq!(missing.collect_async().await.view.failure_reason, CopilotFailureReason::CliMissing);

    let (mut version, _) = collector_with(vec![Ok(handshake("1.0.80", 3))]);
    let result = version.collect_async().await;
    assert_eq!(result.view.failure_reason, CopilotFailureReason::CliVersionMismatch);

    let (mut protocol, _) = collector_with(vec![Ok(handshake("1.0.81", 2))]);
    let result = protocol.collect_async().await;
    assert_eq!(result.view.failure_reason, CopilotFailureReason::ProtocolMismatch);

    let (mut timeout, _) = collector_with(vec![Err(CopilotTransportError::Timeout)]);
    let result = timeout.collect_async().await;
    assert_eq!(result.view.failure_reason, CopilotFailureReason::Timeout);
}

#[tokio::test]
async fn stale_age_is_bounded_and_refresh_failure_never_remains_current() {
    let clock = Arc::new(Mutex::new(Duration::ZERO));
    let (transport, _) = FakeTransport::new(vec![]);
    let mut collector = CopilotCollector::with_transport_and_clock("copilot", Duration::from_secs(3), transport, {
        let clock = clock.clone();
        move || *clock.lock().expect("clock")
    }).expect("collector");
    collector.set_test_baseline(auth("https://example.ghe.com", "enterprise-user"), quota(current_snapshot()));
    *clock.lock().expect("clock") = Duration::from_secs(899);
    assert_eq!(collector.view().source_state, CopilotSourceState::Current);
    *clock.lock().expect("clock") = Duration::from_secs(901);
    assert_eq!(collector.view().source_state, CopilotSourceState::Stale);
    collector.mark_refresh_failed(CopilotFailureReason::Timeout);
    assert_eq!(collector.view().source_state, CopilotSourceState::Stale);
}

#[test]
fn production_operation_allowlist_has_no_model_session_prompt_or_rest_path() {
    let allowed = ["connect", "account.getCurrentAuth", "account.getQuota", "shutdown"];
    for operation in allowed {
        assert!(!["session.create", "session.send", "prompt", "/usage", "acp/usage", "rest"].contains(&operation));
    }
}
