# plugin-audit

Source: [`../../skills/plugin-audit/SKILL.md`](../../skills/plugin-audit/SKILL.md)

## Purpose

Audits an existing plugin (Claude Code and/or Codex) and produces a scored health report
against a 100-point rubric — manifest integrity, skill quality, trigger precision, context
economy, hooks health, and distribution readiness — and saves a baseline for later passes.

## When it fires

When asked to audit, review, score, grade, or health-check a plugin, or before changing any
plugin. Not for creating plugins from scratch (`plugin-scaffold`) or inventory-wide
skill/plugin curation (`skill-curator`).

## References

- [`references/scoring-rubric.md`](../../skills/plugin-audit/references/scoring-rubric.md) — the 100-point rubric, including cross-harness parity credit within existing dimensions.
- [`references/report-style.md`](../../skills/plugin-audit/references/report-style.md) — how to structure the health report.
- [`references/presentation.md`](../../skills/plugin-audit/references/presentation.md) — presentation conventions for scores and findings.
