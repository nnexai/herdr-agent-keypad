---
quick_id: 260822-abq
slug: align-omp-agents-markdown-definitions-wi
type: quick
status: executing
created: 2026-08-22T05:26:05.575Z
files_modified:
  - .omp/agents/*.md
---

# Align OMP agent routing with Codex definitions

## Objective

Copy each `.codex/agents/*.toml` model and `model_reasoning_effort` assignment into the corresponding OMP-discovered `.omp/agents/*.md` frontmatter using OMP's `model` and `thinking-level` keys.

## Tasks

1. Verify every Codex TOML has a matching OMP Markdown definition.
2. Add provider-qualified model selectors and matching thinking levels to all OMP Markdown definitions.
3. Verify all 34 normalized OMP routes match the Codex source definitions and run a native `gsd-executor` route probe.

## Constraints

- `.omp/agents/*.md` is authoritative for OMP task-agent discovery; `.omp/agents/*.toml` is not discovered.
- Preserve agent prompts and descriptions byte-for-byte outside frontmatter routing fields.
- Do not modify `.codex/agents`.
