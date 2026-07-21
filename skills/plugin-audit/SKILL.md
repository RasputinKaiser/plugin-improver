---
name: plugin-audit
description: Audit an existing Codex plugin and produce a scored health report. Use when asked to audit, review, score, grade, or health-check a plugin, or before changing any plugin. Scores manifest integrity, skill quality, trigger precision, context economy, hooks health, and distribution readiness. Not for creating plugins from scratch or inventory-wide skill/plugin curation (use skill-curator).
---

Audit the target plugin and deliver a scored, evidence-backed health report.

## 1. Locate and inventory

1. Find the plugin root: the directory containing `.codex-plugin/plugin.json`. If the user gave no path, search the current repo, then `~/.codex/plugins/`, then map registered sources: `grep -A3 '\[marketplaces' ~/.codex/config.toml` (never audit the read-only copies under `~/.codex/plugins/cache/`).
2. If only `.claude-plugin/plugin.json` exists, note it as a legacy Claude Code plugin and flag migration as a finding — then audit it anyway.
3. Inventory every component: manifest fields, `skills/*/SKILL.md`, `hooks/hooks.json` (or manifest `hooks` entries), `.mcp.json`, `.app.json`, `assets/`, README.

## 2. Validate mechanics

Check each item and record pass/fail with file paths as evidence:

- `plugin.json` parses as JSON; `name` present, kebab-case; `version` is semver.
- All manifest paths (`skills`, `hooks`, `mcpServers`, `apps`, asset paths) start with `./`, resolve relative to the plugin root, and stay inside it.
- Only `plugin.json` lives in `.codex-plugin/`; `skills/`, `hooks/`, `assets/` are at the plugin root.
- Every skill directory contains a `SKILL.md` with `name` and `description` frontmatter; `name` matches its directory.
- `hooks.json` (if present) parses and uses known events: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop.
- Hook commands use `${PLUGIN_ROOT}` instead of absolute or bare relative paths.
- `.mcp.json` (if present) is a direct server map or a `mcp_servers`-wrapped map.

## 3. Score

Read `references/scoring-rubric.md` and score all six dimensions (100 points total). For distribution readiness, also run the visual-presentation checks in `references/presentation.md` (interface metadata, icons, starter prompts, per-skill openai.yaml). Every deduction needs a concrete evidence line (file, and line number where useful).

## 4. Report

Format the report per `references/report-style.md` (scorecard bars, severity-tagged findings, verdict first). Produce it in this order:

1. Scorecard table: dimension, points earned/possible, one-line reason.
2. Findings, sorted by severity, each with evidence and a concrete fix.
3. Prioritized fix list split into quick wins (low effort, high impact) and larger work.
4. Context-cost summary: per-skill description length and SKILL.md body word count, flagged against the rubric's budgets.

## 5. Baseline for regression tracking

Offer to save the audit as a baseline at `<plugin-root>/.plugin-improver/baseline.json` containing: date, total and per-dimension scores, file inventory with word counts, and all skill descriptions verbatim. `$plugin-improve` compares against this to prove later passes did not regress.

End by suggesting `$plugin-improve` to act on the findings.
