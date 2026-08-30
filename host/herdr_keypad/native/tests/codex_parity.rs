#[path = "../src/ports/codex.rs"]
mod codex;

use codex::{
    normalize_rate_limits, redaction_passes, BucketManifest, ChildExit, CodexChildError,
    CodexCollector, CodexProcess, CodexProcessFactory, MAX_LINE_BYTES,
};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;

struct FakeProcess {
    lines: VecDeque<Result<Vec<u8>, CodexChildError>>,
    sent: Arc<Mutex<Vec<Vec<u8>>>>,
    initial_exit: Option<ChildExit>,
    final_exit: ChildExit,
    terminated: bool,
    killed: bool,
}

impl FakeProcess {
    fn from_values(values: Vec<Value>) -> Self {
        Self {
            lines: values
                .into_iter()
                .map(|value| Ok(serde_json::to_vec(&value).expect("JSON")))
                .collect(),
            sent: Arc::new(Mutex::new(Vec::new())),
            initial_exit: None,
            final_exit: ChildExit { state: "exited".to_owned(), code: Some(0), signal: None },
            terminated: false,
            killed: false,
        }
    }

    fn with_line(line: Vec<u8>) -> Self {
        Self {
            lines: VecDeque::from([Ok(line)]),
            sent: Arc::new(Mutex::new(Vec::new())),
            initial_exit: None,
            final_exit: ChildExit { state: "exited".to_owned(), code: Some(0), signal: None },
            terminated: false,
            killed: false,
        }
    }
}

impl CodexProcess for FakeProcess {
    fn send_line(&mut self, line: &[u8]) -> Result<(), CodexChildError> {
        self.sent.lock().expect("sent lock").push(line.to_vec());
        Ok(())
    }

    fn read_line(&mut self, _timeout: Duration) -> Result<Vec<u8>, CodexChildError> {
        self.lines
            .pop_front()
            .unwrap_or_else(|| Err(CodexChildError { code: "E-2403" }))
    }

    fn try_wait(&mut self) -> Result<Option<ChildExit>, CodexChildError> {
        if let Some(exit) = self.initial_exit.take() {
            return Ok(Some(exit));
        }
        if self.terminated || self.killed {
            return Ok(Some(self.final_exit.clone()));
        }
        Ok(None)
    }

    fn terminate(&mut self) -> Result<(), CodexChildError> {
        self.terminated = true;
        Ok(())
    }

    fn kill(&mut self) -> Result<(), CodexChildError> {
        self.killed = true;
        Ok(())
    }

    fn wait(&mut self, _timeout: Duration) -> Result<Option<ChildExit>, CodexChildError> {
        Ok(Some(self.final_exit.clone()))
    }
}

struct FakeFactory {
    process: Mutex<Option<FakeProcess>>,
    argv: Arc<Mutex<Vec<Vec<String>>>>,
}

impl FakeFactory {
    fn new(process: FakeProcess) -> Arc<Self> {
        Arc::new(Self { process: Mutex::new(Some(process)), argv: Arc::new(Mutex::new(Vec::new())) })
    }
}

impl CodexProcessFactory for FakeFactory {
    fn spawn(&self, argv: &[String]) -> Result<Box<dyn CodexProcess>, CodexChildError> {
        self.argv.lock().expect("argv lock").push(argv.to_vec());
        self.process
            .lock()
            .expect("process lock")
            .take()
            .map(|process| Box::new(process) as Box<dyn CodexProcess>)
            .ok_or(CodexChildError { code: "E-2409" })
    }
}

fn collector_with(process: FakeProcess) -> (CodexCollector, Arc<FakeFactory>) {
    let factory = FakeFactory::new(process);
    let collector = CodexCollector::with_factory("codex", Duration::from_secs(3), factory.clone())
        .expect("collector configuration");
    (collector, factory)
}

fn success_messages(rate_limits: Value) -> Vec<Value> {
    vec![
        json!({"id":1,"result":{"ok":true}}),
        json!({"id":2,"result":{"account":{"type":"chatgpt"}}}),
        json!({"id":3,"result":rate_limits}),
    ]
}

#[test]
fn full_normalization_preserves_zero_and_top_level_authority() {
    let (view, redaction) = normalize_rate_limits(&json!({
        "rateLimits": {
            "primary": {"usedPercent": 0},
            "secondary": {"usedPercent": 57},
        }
    }));
    assert_eq!(view.source_state, "current");
    assert_eq!(view.primary, Some(0));
    assert_eq!(view.secondary, Some(57));
    assert!(!redaction.bucket_manifest.present);

    let (view, redaction) = normalize_rate_limits(&json!({
        "rateLimits": {"primary": {"usedPercent": 12}},
        "rateLimitsByLimitId": {"plan-a": {"primary": {"usedPercent": 99}}},
    }));
    assert_eq!(view.primary, Some(12));
    assert!(redaction.bucket_manifest.present);
    assert_eq!(redaction.bucket_manifest.observed_key_count, 1);
    assert_eq!(redaction.bucket_manifest.key_prefixes[0].len(), 12);
    assert!(redaction.bucket_manifest.selected_key.is_none());
}

#[test]
fn duration_mapping_and_invalid_duration_fail_closed() {
    let (weekly, _) = normalize_rate_limits(&json!({
        "rateLimits": {
            "primary": {"usedPercent": 40, "windowDurationMins": 10080},
            "secondary": null,
        }
    }));
    assert_eq!(weekly.primary, None);
    assert_eq!(weekly.secondary, Some(40));

    let (invalid, _) = normalize_rate_limits(&json!({
        "rateLimits": {"primary": {"usedPercent": 40, "windowDurationMins": 1440}}
    }));
    assert_eq!(invalid.source_state, "unavailable");
    assert_eq!(invalid.error_code, "E-2401");
    assert_eq!(invalid.primary, None);
    assert_eq!(invalid.secondary, None);

    let (conflicting, _) = normalize_rate_limits(&json!({
        "rateLimits": {
            "primary": {"usedPercent": 40, "windowDurationMins": 300},
            "secondary": {"usedPercent": 41, "windowDurationMins": 300},
        }
    }));
    assert_eq!(conflicting.source_state, "unavailable");
    assert_eq!(conflicting.error_code, "E-2401");
}

#[test]
fn sparse_updates_require_baseline_preserve_omissions_and_coalesce_refetch() {
    let clock = Arc::new(Mutex::new(Duration::ZERO));
    let now = {
        let clock = clock.clone();
        move || *clock.lock().expect("clock lock")
    };
    let mut collector = CodexCollector::with_factory_and_clock(
        "codex",
        Duration::from_secs(3),
        FakeFactory::new(FakeProcess::from_values(Vec::new())),
        Arc::new(now),
    )
    .expect("collector");

    assert!(!collector.apply_sparse_update(&json!({"rateLimits":{"primary":{"usedPercent":99}}})));
    assert!(collector.refetch_pending());
    assert_eq!(collector.view().primary, None);
    assert_eq!(collector.view().observation_age, "AGE N/A");

    collector.apply_full_response(&json!({
        "rateLimits": {
            "primary": {"usedPercent": 10},
            "secondary": {"usedPercent": 20},
            "rateLimitReachedType": "primary",
            "planType": "pro",
        }
    }));
    assert!(collector.apply_sparse_update(&json!({
        "method":"account/rateLimits/updated",
        "params":{"rateLimits":{"primary":{"usedPercent":0},"secondary":null,"rateLimitReachedType":null}}
    })));
    assert_eq!(collector.view().primary, Some(0));
    assert_eq!(collector.view().secondary, None);
    assert_eq!(collector.view().reached_limit, Some(true));
    assert!(collector.refetch_pending());
    assert!(collector.consume_refetch());
    assert!(!collector.consume_refetch());
}

#[test]
fn sparse_invalid_shapes_are_transactional_and_account_reset_discards_cache() {
    let mut collector = CodexCollector::new();
    collector.apply_full_response(&json!({"rateLimits":{"primary":{"usedPercent":12},"secondary":{"usedPercent":34}}}));
    let before = collector.view();
    let before_observed = collector.last_observed_at();
    assert!(!collector.apply_sparse_update(&json!({
        "rateLimits":{"primary":{"resetsAt":4102444800u64},"secondary":{},"rateLimitReachedType":null}
    })));
    assert_eq!(collector.view(), before);
    assert_eq!(collector.last_observed_at(), before_observed);
    assert!(!collector.apply_sparse_update(&json!({"rateLimits":{"primary":{"usedPercent":77},"secondary":{"usedPercent":"bad"}}})));
    assert_eq!(collector.view(), before);

    collector.account_changed(true);
    assert_eq!(collector.view().source_state, "auth_required");
    assert_eq!(collector.view().primary, None);
    assert_eq!(collector.view().secondary, None);
    assert!(format!("{collector:?}").find("email").is_none());
}

#[test]
fn freshness_marks_current_baseline_stale_only_after_explicit_deadline() {
    let clock = Arc::new(Mutex::new(Duration::ZERO));
    let now = {
        let clock = clock.clone();
        move || *clock.lock().expect("clock lock")
    };
    let mut collector = CodexCollector::with_clock("codex", Duration::from_secs(3), now)
        .expect("collector");
    collector.apply_full_response(&json!({"rateLimits":{"primary":{"usedPercent":12}}}));
    assert_eq!(collector.view().source_state, "current");
    *clock.lock().expect("clock lock") = Duration::from_secs(899);
    assert_eq!(collector.view().source_state, "current");
    *clock.lock().expect("clock lock") = Duration::from_secs(901);
    assert_eq!(collector.view().source_state, "stale");
}

#[test]
fn collect_handshake_is_exact_bounded_and_raw_child_data_is_absent() {
    let process = FakeProcess::from_values(success_messages(json!({
        "rateLimits":{"primary":{"usedPercent":0},"secondary":{"usedPercent":57},"rateLimitReachedType":"primary"}
    })));
    let (mut collector, factory) = collector_with(process);
    let result = collector.collect();
    assert_eq!(result.view.source_state, "current");
    assert_eq!(result.view.primary, Some(0));
    assert_eq!(result.view.secondary, Some(57));
    assert_eq!(result.handshake, vec!["initialize", "initialized", "account/read", "account/rateLimits/read"]);
    assert_eq!(result.child_exit.state, "terminated");
    assert_eq!(result.child_exit.code, Some(0));
    assert_eq!(result.redaction.result, "pass");
    assert_eq!(factory.argv.lock().expect("argv lock")[0], vec!["codex", "app-server", "--stdio"]);
    assert!(format!("{result:?}").find("chatgpt").is_none());
}

#[test]
fn collect_accepts_codex_0151_account_shape_and_interleaved_notification() {
    let process = FakeProcess::from_values(vec![
        json!({"id":1,"result":{"serverInfo":{"name":"codex","version":"0.151.0"}}}),
        json!({"method":"account/updated","params":{"authMode":"chatgpt"}}),
        json!({
            "id":2,
            "result":{
                "account":{"type":"chatgpt"},
                "requiresOpenaiAuth":true
            }
        }),
        json!({
            "id":3,
            "result":{
                "rateLimits":{
                    "primary":{"usedPercent":15,"windowDurationMins":300,"resetsAt":null},
                    "secondary":null,
                    "credits":null,
                    "individualLimit":null,
                    "limitId":null,
                    "limitName":null,
                    "planType":null,
                    "rateLimitReachedType":null,
                    "spendControlReached":null
                },
                "rateLimitsByLimitId":{},
                "rateLimitResetCredits":null
            }
        }),
    ]);
    let (mut collector, _) = collector_with(process);
    let result = collector.collect();

    assert_eq!(result.view.source_state, "current");
    assert_eq!(result.view.primary, Some(15));
    assert_eq!(result.view.secondary, None);
    assert_eq!(
        result.handshake,
        vec!["initialize", "initialized", "account/read", "account/rateLimits/read"]
    );
    assert!(result.account_observed);
    assert!(result.rate_limits_observed);
    assert!(redaction_passes(&result.as_evidence()));
}

#[test]
fn collect_distinguishes_auth_malformed_line_bound_and_already_exited() {
    let auth = FakeProcess::from_values(vec![
        json!({"id":1,"result":{}}),
        json!({"id":2,"result":{"account":null,"requiresOpenaiAuth":true}}),
    ]);
    let (mut collector, _) = collector_with(auth);
    let result = collector.collect();
    assert_eq!(result.view.source_state, "auth_required");
    assert!(result.account_observed);
    assert!(!result.rate_limits_observed);

    let malformed = FakeProcess::from_values(vec![json!({"id":1,"result":{}}), Value::String("not-json".to_owned()), json!({"id":3,"result":{}})]);
    let (mut collector, _) = collector_with(malformed);
    let result = collector.collect();
    assert_eq!(result.view.source_state, "codex_offline");
    assert_eq!(result.view.error_code, "E-2405");

    let oversized = FakeProcess::with_line(vec![b'x'; MAX_LINE_BYTES + 1]);
    let (mut collector, _) = collector_with(oversized);
    let result = collector.collect();
    assert_eq!(result.view.source_state, "codex_offline");
    assert_eq!(result.view.error_code, "E-2404");

    let mut exited = FakeProcess::from_values(success_messages(json!({"rateLimits":{"primary":{"usedPercent":1}}})));
    exited.initial_exit = Some(ChildExit { state: "exited".to_owned(), code: Some(7), signal: None });
    let (mut collector, _) = collector_with(exited);
    let result = collector.collect();
    assert_eq!(result.view.source_state, "current");
    assert_eq!(result.child_exit.state, "exited");
    assert_eq!(result.child_exit.code, Some(7));
}

#[test]
fn redaction_and_child_exit_shapes_are_closed() {
    assert!(redaction_passes(&json!({"codex":{"source_state":"current"}})));
    for key in ["email", "codexHome", "path", "prompt", "transcript", "stderr", "token", "secret"] {
        assert!(!redaction_passes(&json!({"nested":[{key:"redacted"}]})), "{key}");
    }
    assert_eq!(
        ChildExit::new("not_started", None, None).expect("valid shape"),
        ChildExit { state:"not_started".to_owned(), code:None, signal:None }
    );
    assert!(ChildExit::new("exited", None, Some(9)).is_none());
    let manifest = BucketManifest::default();
    assert!(!manifest.present);
}

#[test]
#[ignore = "requires an installed authenticated Codex app-server"]
fn live_installed_codex_reports_only_safe_normalized_state() {
    let executable = std::env::var("CODEX_LIVE_EXECUTABLE").unwrap_or_else(|_| "codex".to_owned());
    let mut collector =
        CodexCollector::try_new(executable, Duration::from_secs(15)).expect("live collector");
    let result = collector.collect();
    let safe = json!({
        "view": result.view.as_payload(),
        "evidence": result.as_evidence(),
    });

    assert!(redaction_passes(&safe));
    println!("{}", serde_json::to_string(&safe).expect("safe diagnostic JSON"));
    assert_eq!(result.view.source_state, "current");
    assert!(
        result.view.primary.is_some() || result.view.secondary.is_some(),
        "authenticated rate-limit response supplied no normalized window"
    );
    assert_eq!(
        result.handshake,
        vec!["initialize", "initialized", "account/read", "account/rateLimits/read"]
    );
}
