from __future__ import annotations

import unittest

from herdr_keypad.bridge import FocusIntent
from herdr_keypad.focus import FocusExecutor
from herdr_keypad.herdr import HerdrError
from herdr_keypad.projection import InboxProjection


def row(pane="p1", terminal="term-p1", revision=1):
    return {"pane_id": pane, "terminal_id": terminal, "workspace_id": "w1", "tab_id": "w1:t1",
            "agent_status": "working", "focused": False, "revision": revision, "state_change_seq": 4,
            "cwd": "/repo", "title": "Agent", "tokens": {"rank": "2"}}


class SpyClient:
    def __init__(self, rows=None, result=None, error=None):
        self.rows = rows if rows is not None else [row()]
        self.result = result if result is not None else {"type": "agent_info", "agent": {**row(), "focused": True}}
        self.error = error
        self.calls = []

    def agent_list(self):
        self.calls.append(("agent.list", {}))
        if self.error:
            raise self.error
        return self.rows

    def focus(self, pane_id):
        self.calls.append(("agent.focus", {"target": pane_id}))
        if self.error:
            raise self.error
        return self.result


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.projection = InboxProjection(host_epoch="epoch")
        self.projection.refresh([row()])
        self.intent = FocusIntent("a1", self.projection.binding(0))

    def test_valid_focus_revalidates_then_emits_only_agent_focus(self):
        client = SpyClient()
        outcome = FocusExecutor(client, self.projection).execute(self.intent)
        self.assertTrue(outcome.success)
        self.assertEqual([call[0] for call in client.calls], ["agent.list", "agent.focus"])
        self.assertEqual(client.calls[-1][1], {"target": "p1"})

    def test_focus_retries_transient_unfocused_ack(self):
        class RetryClient(SpyClient):
            def __init__(self):
                super().__init__(result=None)
                self.results = [
                    {"type": "agent_info", "agent": {**row(), "focused": False}},
                    {"type": "agent_info", "agent": {**row(), "focused": True}},
                ]

            def focus(self, pane_id):
                self.calls.append(("agent.focus", {"target": pane_id}))
                return self.results.pop(0)

        client = RetryClient()
        outcome = FocusExecutor(client, self.projection).execute(self.intent)
        self.assertTrue(outcome.success)
        self.assertEqual([call[0] for call in client.calls], ["agent.list", "agent.focus", "agent.focus"])

    def test_raw_revision_churn_focuses_but_material_projection_change_is_stale(self):
        revision_only = row(revision=99)
        focused = {**revision_only, "focused": True, "revision": 100}
        client = SpyClient(rows=[revision_only], result={"type": "agent_info", "agent": focused})
        outcome = FocusExecutor(client, self.projection).execute(self.intent)
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual([call[0] for call in client.calls], ["agent.list", "agent.focus"])

        changed = {**revision_only, "state_change_seq": 5}
        stale = SpyClient(rows=[changed])
        outcome = FocusExecutor(stale, self.projection).execute(self.intent)
        self.assertEqual(outcome.status, "source_revision_changed")
        self.assertEqual([call[0] for call in stale.calls], ["agent.list"])

    def test_stale_and_wrong_generation_are_rejected_before_io(self):
        client = SpyClient()
        self.projection.invalidate("stale")
        outcome = FocusExecutor(client, self.projection).execute(self.intent)
        self.assertEqual(outcome.status, "stale")
        self.assertEqual(client.calls, [])
        self.projection.refresh([row("p2")])
        outcome = FocusExecutor(client, self.projection).execute(self.intent)
        self.assertIn(outcome.status, {"wrong_revision", "pane_reused"})
        self.assertEqual(client.calls, [])

    def test_identity_mismatch_and_bad_response_never_succeed(self):
        wrong = SpyClient(result={"type": "agent_info", "agent": {**row(terminal="other"), "focused": True}})
        self.assertEqual(FocusExecutor(wrong, self.projection).execute(self.intent).status, "pane_reused")
        self.assertEqual([call[0] for call in wrong.calls], ["agent.list", "agent.focus"])
        malformed = SpyClient(result={"type": "error"})
        self.assertEqual(FocusExecutor(malformed, self.projection).execute(self.intent).status, "rejected")

    def test_vanished_timeout_and_empty_are_distinct(self):
        vanished = SpyClient(rows=[])
        self.assertEqual(FocusExecutor(vanished, self.projection).execute(self.intent).status, "vanished")
        timeout = SpyClient(error=HerdrError("timeout"))
        self.assertEqual(FocusExecutor(timeout, self.projection).execute(self.intent).status, "uncertain")
        self.projection.refresh([])
        self.assertEqual(FocusExecutor(SpyClient(), self.projection).execute(self.intent).status, "wrong_revision")


if __name__ == "__main__":
    unittest.main()
