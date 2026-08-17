from __future__ import annotations

import unittest

from herdr_keypad.projection import InboxProjection, ProjectionUnavailable


def row(pane: str, rank: str, seq: int, *, workspace: str = "w1", title: str | None = "Title", cwd: str = "/repo"):
    return {
        "pane_id": pane, "terminal_id": f"term-{pane}", "workspace_id": workspace,
        "tab_id": f"{workspace}:t1", "agent_status": "working", "focused": False,
        "revision": 1, "state_change_seq": seq, "cwd": cwd,
        "title": title, "tokens": {"rank": rank, "title": "Plugin title"}, "agent": "agent",
    }


class ProjectionTests(unittest.TestCase):
    def test_fixed_positions_and_installed_order(self):
        projection = InboxProjection(host_epoch="epoch")
        snapshot = projection.refresh([row("p3", "2", 1), row("p1", "0", 2), row("p2", "1", 3)])
        self.assertEqual([entry.identity.pane_id if entry.identity else None for entry in snapshot.entries], ["p1", "p2", "p3"])
        self.assertEqual([entry.state for entry in snapshot.entries], ["blocked", "finished", "working"])
        empty = projection.refresh([row("p1", "0", 2)])
        self.assertEqual(empty.entries[0].identity.pane_id, "p1")
        self.assertEqual(empty.entries[1].state, "empty")
        self.assertEqual(empty.entries[2].title, "NO AGENT")

    def test_equal_rank_uses_newest_sequence_and_source_array_is_irrelevant(self):
        projection = InboxProjection()
        rows = [row("old", "2", 4), row("new", "2", 9)]
        first = projection.refresh(rows)
        second = projection.refresh(list(reversed(rows)))
        self.assertEqual(first.entries[0].identity.pane_id, "new")
        self.assertEqual(second.entries[0].identity.pane_id, "new")

    def test_rank_and_identity_are_fail_closed(self):
        projection = InboxProjection()
        missing_rank = row("p1", "2", 1)
        del missing_rank["tokens"]["rank"]
        with self.assertRaises(ProjectionUnavailable):
            projection.refresh([missing_rank])
        missing_identity = row("p1", "2", 1)
        del missing_identity["terminal_id"]
        with self.assertRaises(ProjectionUnavailable):
            projection.refresh([missing_identity])

    def test_title_and_discriminator_are_bounded_and_non_path(self):
        projection = InboxProjection()
        snapshot = projection.refresh([row("p1", "2", 1, title=None, cwd="/home/me/repository")], [{"workspace_id": "w1", "label": "Workspace"}])
        self.assertEqual(snapshot.entries[0].title, "Plugin title")
        self.assertEqual(snapshot.entries[0].discriminator, "Workspace")
        self.assertNotIn("/", snapshot.entries[0].discriminator)

    def test_invalidation_freezes_identity_and_disables_action(self):
        projection = InboxProjection()
        current = projection.refresh([row("p1", "2", 1)])
        stale = projection.invalidate("offline")
        self.assertEqual(stale.entries[0].identity, current.entries[0].identity)
        self.assertEqual(stale.entries[0].state, "offline")
        self.assertFalse(stale.actionable)
        self.assertIsNone(projection.binding(0))
        fresh = projection.refresh([row("p2", "2", 2)])
        self.assertEqual(fresh.entries[0].identity.pane_id, "p2")
        self.assertIsNotNone(projection.binding(0))

    def test_equal_normalized_refresh_reuses_revision(self):
        projection = InboxProjection(host_epoch="epoch")
        rows = [row("p1", "0", 1)]
        first = projection.refresh(rows)
        second = projection.refresh(list(rows))
        self.assertIs(first, second)
        self.assertEqual(first.snapshot_revision, 1)


if __name__ == "__main__":
    unittest.main()
