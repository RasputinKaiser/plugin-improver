# skill-curator

Source: [`../../skills/skill-curator/SKILL.md`](../../skills/skill-curator/SKILL.md)

## Purpose

Audits and curates the whole skill and plugin inventory across both harnesses: skill sprawl,
trigger collisions, near-dupes, dead skills, duplicate installs, and source-vs-cache plugin
version drift. Proposes merges and prunes with an archive-never-delete decision ledger.

## When it fires

For "curate my skills", "skill sprawl", "plugin sprawl", "prune skills", "audit my skills",
"version drift", or after a batch install. Not for one plugin's health score
(`plugin-audit`) or one skill's body (`skill-creator`).

## References

- [`references/routing-evals.md`](../../skills/skill-curator/references/routing-evals.md) — routing/plugin-eval detail for collision and near-dupe detection.
- [`scripts/curator.py`](../../skills/skill-curator/scripts/curator.py) — the inventory-scanning self-test the skill drives.
