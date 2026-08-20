from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from herdr_keypad.bridge import write_codex_tracer_evidence
from herdr_keypad.codex import (
    BucketManifest,
    ChildExit,
    CodexCollector,
    CodexView,
    normalize_rate_limits,
    redaction_passes,
)


class FakeProcess:
    def __init__(self, messages: list[object], *, returncode: int | None = None):
        self.stdin = io.BytesIO()
        encoded = []
        for message in messages:
            encoded.append(message if isinstance(message, bytes) else json.dumps(message, separators=(",", ":")).encode())
        self.stdout = io.BytesIO(b"\n".join(encoded) + (b"\n" if encoded else b""))
        self.stderr = io.BytesIO()
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class CodexCollectorTests(unittest.TestCase):
    def collect(self, messages: list[dict], *, returncode: int | None = None):
        process = FakeProcess(messages, returncode=returncode)
        collector = CodexCollector(
            executable="codex",
            deadline_ms=3000,
            process_factory=lambda *args, **kwargs: process,
        )
        result = collector.collect()
        return result, process

    @staticmethod
    def success_messages(rate_limits: object, account: object | None = None):
        return [
            {"id": 1, "result": {"ok": True}},
            {"id": 2, "result": {"account": account if account is not None else {"type": "chatgpt"}}},
            {"id": 3, "result": rate_limits},
        ]

    def test_success_preserves_zero_and_records_handshake_and_exit(self):
        result, process = self.collect(
            self.success_messages(
                {
                    "rateLimits": {
                        "primary": {"usedPercent": 0, "resetsAt": 4_102_444_800},
                        "secondary": {"usedPercent": 57},
                        "rateLimitReachedType": "primary",
                    }
                }
            )
        )
        self.assertEqual(result.view.source_state, "current")
        self.assertEqual(result.view.primary, 0)
        self.assertEqual(result.view.secondary, 57)
        self.assertTrue(result.view.reached_limit)
        self.assertEqual(result.handshake, ("initialize", "initialized", "account/read", "account/rateLimits/read"))
        self.assertEqual(result.child_exit, ChildExit("terminated", 0, None))
        self.assertLessEqual(result.elapsed_ms, result.deadline_ms)
        self.assertEqual(result.redaction.result, "pass")
        self.assertTrue(process.terminated)

    def test_auth_evidence_is_distinct_from_process_failure(self):
        result, _ = self.collect([
            {"id": 1, "result": {}},
            {"id": 2, "result": {"account": None, "requiresOpenaiAuth": True}},
        ])
        self.assertEqual(result.view.source_state, "auth_required")
        self.assertEqual(result.child_exit.state, "terminated")
        self.assertEqual(result.view.error_code, "")

    def test_timeout_exit_and_malformed_json_are_codex_offline(self):
        result, _ = self.collect([{ "id": 1, "result": {} }, { "id": 2, "result": {"account": {}}}])
        self.assertEqual(result.view.source_state, "codex_offline")
        self.assertEqual(result.view.error_code, "E-2403")
        self.assertLessEqual(result.elapsed_ms, result.deadline_ms)
        result, _ = self.collect([{ "id": 1, "result": {} }, b"bad"])
        self.assertEqual(result.view.source_state, "codex_offline")

    def test_top_level_map_shapes_and_explicit_null_presence(self):
        top_level = {"rateLimits": {"primary": {"usedPercent": 12}}}
        view, redaction = normalize_rate_limits(top_level)
        self.assertEqual(view.primary, 12)
        self.assertFalse(redaction.bucket_manifest.present)

        explicit_null = {"rateLimits": {"primary": {"usedPercent": 12}}, "rateLimitsByLimitId": None}
        _view, redaction = normalize_rate_limits(explicit_null)
        self.assertTrue(redaction.bucket_manifest.present)

        map_only = {"rateLimitsByLimitId": {"plan-a": {"primary": {"usedPercent": 99}}}}
        view, redaction = normalize_rate_limits(map_only)
        self.assertEqual(view.source_state, "unavailable")
        self.assertEqual(view.error_code, "E-2401")
        self.assertEqual(view.primary, None)
        self.assertIsNone(redaction.bucket_manifest.selected_key)

        both = {**top_level, "rateLimitsByLimitId": {"plan-a": {}}}
        view, _ = normalize_rate_limits(both)
        self.assertEqual(view.primary, 12)

        neither, _ = normalize_rate_limits({})
        self.assertEqual(neither.error_code, "E-2401")
        unusable, _ = normalize_rate_limits({"rateLimits": []})
        self.assertEqual(unusable.error_code, "E-2401")

    def test_structured_unauthorized_and_bounded_jsonl_failures(self):
        result, _ = self.collect([
            {"id": 1, "result": {}},
            {"id": 2, "error": {"code": "unauthorized"}},
        ])
        self.assertEqual(result.view.source_state, "auth_required")
        result, _ = self.collect([{"id": 1, "result": {}}, b"x" * 4097])
        self.assertEqual(result.view.source_state, "codex_offline")
        self.assertEqual(result.view.error_code, "E-2404")
        result, _ = self.collect([{"id": 99, "result": {}}])
        self.assertEqual(result.view.source_state, "codex_offline")
        self.assertEqual(result.view.error_code, "E-2403")
        self.assertLessEqual(result.elapsed_ms, result.deadline_ms)

    def test_child_exit_code_is_recorded_when_process_already_exited(self):
        result, _ = self.collect(self.success_messages({"rateLimits": {"primary": {"usedPercent": 1}}}), returncode=7)
        self.assertEqual(result.child_exit, ChildExit("exited", 7, None))
        self.assertEqual(result.redaction.result, "pass")

    def test_bucket_manifest_is_bounded_and_hash_only(self):
        keys = {f"bucket-{index}" : {} for index in range(12)}
        _view, redaction = normalize_rate_limits({"rateLimits": {}, "rateLimitsByLimitId": keys})
        manifest = redaction.bucket_manifest
        self.assertIsInstance(manifest, BucketManifest)
        self.assertEqual(manifest.observed_key_count, 12)
        self.assertEqual(len(manifest.key_prefixes), 8)
        self.assertTrue(manifest.truncated)
        self.assertTrue(all(len(prefix) == 12 for prefix in manifest.key_prefixes))
        self.assertIsNone(manifest.selected_key)
        self.assertNotIn("bucket-", json.dumps(manifest.as_dict()))

    def test_recursive_redaction_rejects_sensitive_shapes(self):
        self.assertTrue(redaction_passes({"codex": {"source_state": "current"}}))
        for key in ("email", "codexHome", "path", "prompt", "transcript", "stderr", "token", "secret"):
            self.assertFalse(redaction_passes({"nested": [{key: "redacted"}]}), key)

    def test_child_exit_shape_is_closed(self):
        self.assertEqual(ChildExit("not_started").as_dict(), {"state": "not_started", "code": None, "signal": None})
        with self.assertRaises(ValueError):
            ChildExit("done")
        with self.assertRaises(ValueError):
            ChildExit("exited", None, 9)


    def test_closed_installed_artifact_has_stable_exports_and_checksum(self):
        result, _ = self.collect([
            {"id": 1, "result": {}},
            {"id": 2, "result": {"account": None, "requiresOpenaiAuth": True}},
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "03-CODEX-TRACER.json"
            write_codex_tracer_evidence(
                path,
                result="fail",
                codex=result,
                hello={
                    "device_id": "0000fccb0deabf8c",
                    "firmware": "phase1-bringup",
                    "protocol": 1,
                    "boot_id": "0000fccb0deabf8c-boot",
                    "session_id": "session-1",
                },
                deployment={
                    "environment": "selected-usb",
                    "firmware_sha256": "a" * 64,
                    "upload": "pass",
                },
            )
            record = json.loads(path.read_text())
            self.assertEqual(record["source"]["live"], "installed")
            self.assertEqual(record["collector"]["child_exit"]["state"], "terminated")
            self.assertEqual(record["final_evidence_refs"]["elapsed_ms"], "/collector/elapsed_ms")
            self.assertEqual(record["final_evidence_refs"]["child_exit"], "/collector/child_exit")
            self.assertEqual(record["final_evidence_refs"]["redaction_result"], "/redaction/result")
            self.assertNotIn("email", json.dumps(record))
            self.assertNotIn("bucket-", json.dumps(record))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, Path(str(path) + ".sha256").read_text().split()[0])

if __name__ == "__main__":
    unittest.main()
