---
name: skill-curator
description: "Audit and curate the skill and plugin inventory: sprawl, trigger collisions, near-dupes, dead skills, duplicate installs, plugin version drift; propose merges/prunes. Use for 'curate my skills', 'skill sprawl', 'plugin sprawl', 'prune skills', 'audit my skills', 'version drift', or after a batch install. Not for one plugin's health score (plugin-audit) or one skill's body (skill-creator)."
---

# Skill Curator

Deterministic detection lives in `scripts/curator.py` (stdlib only); your job is judgment
on its findings, with user approval before anything moves. It scans every trigger surface
plus plugin-level state and keeps a decision ledger, so repeat runs surface only new
findings.

## Workflow

1. **Scan.** `python3 scripts/curator.py report --usage --md CURATION.md`
   Defaults: roots ~/.codex/skills + ~/.claude/skills, plugin caches under ~/.claude +
   ~/.codex (`--no-plugins` to skip); usage mined from BOTH ecosystems (~/.codex/sessions
   and ~/.claude/projects — SKILL.md refs + Skill-tool calls). Incremental mtime caches
   make later passes near-instant (`--rebuild-usage` to force); `--json` for
   machine-readable, `--all` to include rejected/snoozed findings.
2. **Read the header.** Health grade, trigger-token tax, and "since last run: N new,
   M resolved". On a recurring pass work the **NEW** findings first — the rest already
   lives in the ledger.
3. **Interpret, in payoff order** (the "Do these first" list is pre-ranked by tokens saved):
   - `plugin_version_drift` — source version ≠ installed cache: edits aren't live. Always
     leads (correctness, not tokens); refresh the install. `duplicate_plugins` /
     `stale_plugin_caches` are litigated like any finding; `--plugin-source` overrides the
     default source roots (~/.codex/plugins, ~/.claude/plugins, minus cache/).
   - `duplicate_surfaces` — same skill shipped in 2+ places. `diverged-copies` is worst
     (which copy is true?); `identical-copies` wastes trigger tokens; `shared` (symlink)
     is deliberate economy — leave it.
   - `collision_clusters` — topic groups competing for the same triggers; phrase-backed
     clusters (identical quoted phrases) are worst. Fix by sharpening descriptions (see
     plugin-tune-triggers), verify with routing probes; merge only as a last resort.
     `report` folds in a graph summary; `python3 scripts/curator.py graph`
     (`--md`/`--mermaid`/`--dot`) is the full map — trigger-hogs, minimal-edit set,
     reference orphans/broken-handoffs/cycles (`references/routing-evals.md`).
   - `near_dupes` / `families` — merge candidates. Diff both bodies first; a family split
     can be deliberate economy.
   - `prune_candidates` — never-referenced skills ranked by per-session trigger cost;
     the `usage_note` caveat is part of any prune proposal, and `--grace-days` (default
     14) shields new skills.
   - `long_descriptions` / economics — trim the heavy ones; per-surface totals show who
     pays what.
4. **Decide with the user, then record every verdict** so it never re-surfaces:
   `python3 scripts/curator.py decide <fp> --reject --note "deliberate split"`
   (or `--accept`, or `--snooze-days 30`). `decisions` lists the ledger.
5. **Execute approved items.**
   - Archive, never delete: `python3 scripts/curator.py archive <name> --reason "..."
     --fp <fp>` moves it to `<root>/.archive/YYYYMMDD/` with a provenance manifest;
     `restore` undoes it. Symlinks: only the link is archived (target untouched).
     Plugin-cache skills can't be archived — disable the plugin in its app.
   - Merges: combine bodies, keep the sharper description, archive the loser.
6. **Verify.** Re-run the report: counts dropped, the diff line shows resolutions, no
   healthy skill vanished. Record before/after counts in the gap ledger note.

## Companion diagnostics

Curator is the inventory-wide lens; for per-plugin depth compose it with sibling
`scripts/` (stdlib):

```
scripts/score.py      # deterministic rubric sub-score + --min-baseline CI gate
scripts/portfolio.py  # score sweep + fix-first leaderboard + trajectory, all local sources
scripts/tokens.py     # per-plugin token / context-budget report
scripts/errscan.py    # runtime error/health mining from Claude Code + Codex logs
scripts/route_eval.py # measured routing-accuracy loop + --min-baseline gate
```

Curator picks *which* target to fix; these quantify *why*. `portfolio.py` ranks via
`score.py`; `route_eval.py` drives the probes in `references/routing-evals.md`.

## Scheduled drift watch

Weekly quiet check: `python3 scripts/curator.py check --usage --max-trigger-tokens <budget>
--max-new-findings 0` exits nonzero on drift — only then surface a digest.

## Rules

- Read-only by default; every move requires explicit user approval per item.
- Archive, never delete. Unresolved symlinks are unknowns, not dead skills — say so.
- never_used means "no recorded reference", not proof of zero use; repeat the caveat.
- After editing curator.py, run `python3 scripts/curator.py selftest` before trusting it.
