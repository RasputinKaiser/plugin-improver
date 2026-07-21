---
name: plugin-audit
description: Audit an existing plugin (Claude Code and/or Codex) and produce a scored health report. Use when asked to audit, review, score, grade, or health-check a plugin, or before changing any plugin. Scores manifest, skill, trigger, context, hooks, and distribution health. Not for creating plugins from scratch or inventory-wide skill/plugin curation (use skill-curator).
---

Audit the target plugin and deliver a scored, evidence-backed health report.

## 1. Locate and inventory

1. Find the plugin root: the directory containing `.claude-plugin/plugin.json` **or** `.codex-plugin/plugin.json` (a dual-harness plugin has both). If the user gave no path, search the current repo, then the harness plugin dir (`~/.claude/plugins/` or `~/.codex/plugins/`); on Codex also map registered sources: `grep -A3 '\[marketplaces' ~/.codex/config.toml`. Never audit the read-only installed copies under `~/.claude/plugins/cache/` or `~/.codex/plugins/cache/`.
2. Determine which harnesses the plugin targets. If it claims dual-harness support but ships one manifest, flag the missing manifest as a parity finding, then audit anyway.
3. Inventory every component: manifest fields (both manifests when present), `skills/*/SKILL.md`, `hooks/hooks.json` (or manifest `hooks` entries), `.mcp.json`, `.app.json`, `assets/`, README.

## 2. Validate mechanics

Check each item and record pass/fail with file paths as evidence:

- Each present `plugin.json` parses as JSON; `name` present, kebab-case; `version` is semver.
- Parity: if both manifests exist, `name` is identical and `version` agrees (ignoring any Codex `+build` suffix) — drift is a finding.
- All manifest paths (`skills`, `hooks`, `mcpServers`, `apps`, asset paths) start with `./` and stay inside the plugin root.
- Each manifest dir holds only its own `plugin.json` (plus `marketplace.json`); `skills/`, `hooks/`, `assets/` are at the plugin root.
- Every skill directory contains a `SKILL.md` with `name` and `description` frontmatter; `name` matches its directory.
- `hooks.json` (if present) parses and uses known events: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop.
- Hook commands use `${CLAUDE_PLUGIN_ROOT}` (portable; Codex also accepts `${PLUGIN_ROOT}`) instead of absolute or bare relative paths.
- `.mcp.json` (if present) is a direct server map or a `mcp_servers`-wrapped map.

## 3. Diagnostics (machine floor + runtime signal)

Run three stdlib scripts before scoring; their output is evidence, not verdicts.

```
python3 scripts/score.py <plugin-root> --json      # deterministic machine floor
python3 scripts/tokens.py <plugin-root>            # token & budget report
python3 scripts/errscan.py <plugin-root>           # runtime errors from session logs
```

- `score.py` emits `{dimension:{auto,max,needs_judgment}}` — the machine FLOOR, now higher for carrying graduated `skill_quality` signal: take each `auto` as fixed, score only `needs_judgment`. Mapping in `references/deterministic-scoring.md`.
- `tokens.py` gives the session-tax headline, budget headroom, and baseline delta → feeds Context economy.
- `errscan.py` aggregates runtime errors per plugin/skill → feeds Hooks health (hooks that throw lose points even when `hooks.json` shape is valid).

If a script is missing, inspect manually and note it.

## 4. Score

Read `references/scoring-rubric.md` and score each applicable dimension on the `score.py` floor, mapping the total to the frozen 5-band scale there. An N/A dimension (e.g. no hooks) is dropped, its weight redistributed — never a free max. For distribution readiness, run the visual-presentation checks in `references/presentation.md` (interface metadata, icons, starter prompts, Codex-only per-skill openai.yaml). Every deduction needs a concrete evidence line (file, line number where useful), citing script output where it drives one.

## 5. Report

Format the report per `references/report-style.md` (scorecard bars, severity-tagged findings, Diagnostics block, verdict first). Produce it in this order:

1. Scorecard table: dimension, points earned/possible, one-line reason.
2. Diagnostics block: floor vs judgment split, token/session-tax and runtime-error lines.
3. Findings, sorted by severity, each with evidence and a concrete fix.
4. Prioritized fix list: quick wins (low effort, high impact) and larger work.
5. Context-cost summary: per-skill description length and SKILL.md body word count, flagged against the rubric's budgets.

## 6. Baseline for regression tracking

Offer to save the audit as a baseline at `<plugin-root>/.plugin-improver/baseline.json` containing: date, total and per-dimension scores (including the `score.py` deterministic floor), file inventory with word counts, and all skill descriptions verbatim. `plugin-improve` compares against this to prove later passes did not regress.

End by suggesting `plugin-improve` to act on the findings.
