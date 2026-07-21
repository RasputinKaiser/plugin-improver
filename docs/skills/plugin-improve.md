# plugin-improve

Source: [`../../skills/plugin-improve/SKILL.md`](../../skills/plugin-improve/SKILL.md)

## Purpose

Runs a disciplined improvement pass on an existing plugin: audit → apply the ≤3
highest-leverage fixes → verify nothing regressed → re-score → version bump → ledger. Reports
"stable" instead of churning when there is nothing high-leverage left to change.

## When it fires

When asked to improve, polish, upgrade, evolve, iterate on, or "make better" a plugin,
including recurring maintenance passes. Not for first-time plugin creation
(`plugin-scaffold`) or one-off hook fixes (`plugin-hooks`).

## Memory

Reads and writes the target plugin's `.plugin-improver/baseline.json` (last score, gates the
pass) and appends decisions to its `LEDGER.md` with provenance, so passes compound.

## References

- [`references/regression-checklist.md`](../../skills/plugin-improve/references/regression-checklist.md) — the checklist a pass must clear before it re-scores.
