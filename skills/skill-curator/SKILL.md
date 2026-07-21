---
name: skill-curator
description: "Audit and curate the skill and plugin inventory: sprawl, trigger collisions, near-dupes, dead skills, duplicate installs, plugin version drift; propose merges/prunes. Use for 'curate my skills', 'skill sprawl', 'plugin sprawl', 'prune skills', 'audit my skills', 'version drift', or after a batch install. Not for one plugin's health score (plugin-audit) or one skill's body (skill-creator)."
---

# Skill Curator

Deterministic detection lives in `scripts/curator.py` (stdlib only). Your job is judgment
on top of its findings — and user approval before anything moves. v3 scans every trigger
surface (skills roots AND installed plugin caches) plus plugin-level state (local plugin
sources vs installed caches), and keeps a decision ledger so repeat runs surface only
what's new.

## Workflow

1. **Scan.** `python3 scripts/curator.py report --usage --md CURATION.md`
   Defaults: roots ~/.codex/skills + ~/.claude/skills, plugin caches
   ~/.claude/plugins/cache + ~/.codex/plugins/cache (`--no-plugins` to skip), usage mined
   from BOTH ecosystems — ~/.codex/sessions (SKILL.md refs) and ~/.claude/projects
   (SKILL.md refs + Skill-tool calls). Incremental mtime caches: first pass is slow,
   later passes near-instant (`--rebuild-usage` to force). `--json` for machine-readable,
   `--all` to include rejected/snoozed findings.
2. **Read the header.** Health grade, trigger-token tax, and "since last run: N new,
   M resolved". On a recurring pass work the **NEW** findings first — everything else was
   already litigated and lives in the ledger.
3. **Interpret, in payoff order** (the "Do these first" list is pre-ranked by tokens saved):
   - `plugin_version_drift` — source version ≠ installed cache: edits aren't live. Always
     leads the list (correctness, not tokens); refresh the install. `duplicate_plugins` /
     `stale_plugin_caches` are litigated like any finding. `--plugin-source` overrides
     the default source roots (~/.codex/plugins, ~/.claude/plugins, minus cache/).
   - `duplicate_surfaces` — same skill shipped in 2+ places. `diverged-copies` is worst
     (drift risk: which copy is true?); `identical-copies` wastes trigger tokens;
     `shared` (symlink) is deliberate economy — leave it.
   - `collision_clusters` — topic groups competing for the same triggers. Phrase-backed
     clusters (identical quoted trigger phrases) are the most dangerous. Fix by sharpening
     descriptions (see plugin-tune-triggers), verify with routing probes
     (`references/routing-evals.md`); merge only as a last resort.
   - `near_dupes` / `families` — merge candidates. Diff both bodies before proposing;
     a family split can be deliberate context economy.
   - `prune_candidates` — never-referenced skills ranked by per-session trigger cost.
     The `usage_note` caveat is part of any prune proposal; `--grace-days` (default 14)
     shields new skills.
   - `long_descriptions` / economics — trim the heavy ones; per-surface totals show
     which app pays what.
4. **Decide with the user, then record every verdict** so it never re-surfaces:
   `python3 scripts/curator.py decide <fp> --reject --note "deliberate split"`
   (or `--accept`, or `--snooze-days 30`). `decisions` lists the ledger.
5. **Execute approved items.**
   - Archive, never delete: `python3 scripts/curator.py archive <name> --reason "..."
     --fp <fp>` moves it to `<root>/.archive/YYYYMMDD/` with a provenance manifest;
     `restore <name>` undoes it. For symlinks only the link is archived (target untouched
     — say so). Plugin-cache skills can't be archived — disable the plugin in its app.
   - Merges: combine bodies, keep the sharper description, archive the loser.
6. **Verify.** Re-run the report: finding counts dropped, the diff line shows resolutions,
   and no healthy skill vanished. Record before/after counts in the gap ledger memory note.

## Measuring routing behaviorally

Lexical collisions are hypotheses. To measure real confusion (probes → routing sheet →
confusion matrix) and to merge inventory findings into plugin-eval runs, follow
`references/routing-evals.md`.

## Scheduled drift watch

Weekly quiet check: `python3 scripts/curator.py check --usage --max-trigger-tokens <budget>
--max-new-findings 0` exits nonzero on drift — only then surface a digest.

## Rules

- Read-only by default; every move requires explicit user approval per item.
- Archive, never delete. Unresolved symlinks are unknowns, not dead skills — say so.
- never_used means "no recorded reference", not proof of zero use; repeat the caveat.
- After editing curator.py, run `python3 scripts/curator.py selftest` before trusting it.
