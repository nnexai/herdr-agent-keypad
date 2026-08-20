---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-08-20T15:45:42.342Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 02.2 | unmet-truth | .planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-DEVICE-EVIDENCE.json |  | Phase 02.2 exact physical fallback check remains unrun and deferred: perform a fresh erase or inject invalid/missing stored settings, verify Signal Edge + Rail Echo fallback, and verify no write-back on the physical device. | open |  | 2026-08-20T15:45:42.342Z |  |

````json
[
  {
    "id": 1,
    "kind": "unmet-truth",
    "phase": "02.2",
    "file": ".planning/phases/02.2-firmware-themes-led-bars-and-device-selection-menu/02.2-DEVICE-EVIDENCE.json",
    "line": null,
    "description": "Phase 02.2 exact physical fallback check remains unrun and deferred: perform a fresh erase or inject invalid/missing stored settings, verify Signal Edge + Rail Echo fallback, and verify no write-back on the physical device.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-20T15:45:42.342Z",
    "resolved_at": null
  }
]
````
