---
name: plugin-audit
description: Audit an existing plugin (Claude Code and/or Codex) and produce a scored health report. Use when asked to audit, review, score, grade, or health-check a plugin, or before changing any plugin. Scores manifest, skill, trigger, context, hooks, and distribution health. Not for creating plugins from scratch or inventory-wide skill/plugin curation (use skill-curator).
---

Audit the target plugin and deliver a scored, evidence-backed health report.

## 1. Locate and inventory

1. Find the plugin root: the directory containing `.claude-plugin/plugin.json` **or** `.codex-plugin/plugin.json` (a dual-harness plugin has both). If the user gave no path, search the current repo, then the harness plugin dir (`~/.claude/plugins/` or `~/.codex/plugins/`); on Codex also map registered sources: `grep -A3 '\[marketplaces' ~/.codex/config.toml`. Never audit the read-only installed copies under `~/.claude/plugins/cache/` or `~/.codex/plugins/cache/`.
2. Determine which harnesses the plugin targets (manifests present, README claims). If it claims dual-harness support but ships only one manifest, flag the missing manifest as a parity finding — then audit it anyway.
3. Inventory every component: manifest fields (both manifests when present), `skills/*/SKILL.md`, `hooks/hooks.json` (or manifest `hooks` entries), `.mcp.json`, `.app.json`, `assets/`, README.

## 2. Validate mechanics

Check each item and record pass/fail with file paths as evidence:

- Each present `plugin.json` parses as JSON; `name` present, kebab-case; `version` is semver.
- Parity: if both manifests exist, `name` is identical and `version` agrees (ignoring any Codex `+build` suffix) — drift is a finding.
- All manifest paths (`skills`, `hooks`, `mcpServers`, `apps`, asset paths) start with `./`, resolve relative to the plugin root, and stay inside it.
- Each manifest dir holds only its own `plugin.json` (plus `marketplace.json`); `skills/`, `hooks/`, `assets/` are at the plugin root.
- Every skill directory contains a `SKILL.md` with `name` and `description` frontmatter; `name` matches its directory.
- `hooks.json` (if present) parses and uses known events: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop.
- Hook commands use `${CLAUDE_PLUGIN_ROOT}` (portable; Codex also accepts `${PLUGIN_ROOT}`) instead of absolute or bare relative paths.
- `.mcp.json` (if present) is a direct server map or a `mcp_servers`-wrapped map.

## 3. Score

Read `references/scoring-rubric.md` and score all six dimensions (100 points total); it awards cross-harness parity credit inside Manifest integrity and Distribution readiness. For distribution readiness, also run the visual-presentation checks in `references/presentation.md` (interface metadata, icons, starter prompts, and the Codex-only per-skill openai.yaml). Every deduction needs a concrete evidence line (file, and line number where useful).

## 4. Report

Format the report per `references/report-style.md` (scorecard bars, severity-tagged findings, verdict first). Produce it in this order:

1. Scorecard table: dimension, points earned/possible, one-line reason.
2. Findings, sorted by severity, each with evidence and a concrete fix.
3. Prioritized fix list split into quick wins (low effort, high impact) and larger work.
4. Context-cost summary: per-skill description length and SKILL.md body word count, flagged against the rubric's budgets.

## 5. Baseline for regression tracking

Offer to save the audit as a baseline at `<plugin-root>/.plugin-improver/baseline.json` containing: date, total and per-dimension scores, file inventory with word counts, and all skill descriptions verbatim. `plugin-improve` compares against this to prove later passes did not regress.

End by suggesting `plugin-improve` to act on the findings.
