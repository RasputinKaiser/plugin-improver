# Architecture

plugin-improver is one plugin that serves two harnesses — Claude Code and Codex — from a
single source tree. This page explains how that works, how each harness discovers and
installs the plugin, what the validator guarantees, and how per-target memory is stored.

## One `skills/` tree, two harnesses

Every skill lives in `skills/<skill>/` and its instructions live in a **harness-neutral**
`SKILL.md`. The two harnesses consume that directory differently:

| File | Claude Code | Codex |
|---|---|---|
| `SKILL.md` | read (frontmatter + body) | read (frontmatter + body) |
| `agents/openai.yaml` | ignored | read — Codex-only per-skill interface (`display_name`, `interface`) |
| `commands/*.md` | read — one slash command per skill (Claude-Code-only explicit invocation, the analogue of Codex `$skill`) | ignored |
| `references/*.md` | lazy-loaded on demand | lazy-loaded on demand |
| `scripts/*` | run when the body calls them | run when the body calls them |

Because Claude Code ignores `agents/openai.yaml`, the same skill directory is complete for
both harnesses: Codex gets a polished skills-list surface, Claude Code gets the body it
needs, and neither reads anything wrong. Skill bodies are written to be true on both
harnesses and only branch into "On Codex… / On Claude Code…" where the platforms genuinely
diverge — hooks capabilities, hook feature flags, and the manifest paths used when locating
a plugin root.

## The manifest and marketplace story

Each harness has its own manifest and its own distribution channel. plugin-improver ships
both so a single clone installs anywhere.

| Concern | Claude Code | Codex |
|---|---|---|
| Plugin manifest | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` |
| Marketplace | `.claude-plugin/marketplace.json` (this repo is a single-plugin marketplace) | an entry in `~/.agents/plugins/marketplace.json` (or `~/.codex/config.toml [marketplaces]`) |
| Install root | `~/.claude/plugins/` | `~/.codex/plugins/` |

The two plugin manifests share the same `name` (`plugin-improver`) and the same `version`.
The Codex manifest may carry a `+build` metadata suffix (e.g. `1.0.0+codex.…`); the base
semver must still equal the Claude Code manifest's version. A dual-harness plugin therefore
always ships **both** manifests with agreeing versions — the validator and the audit rubric
both enforce this as the definition of "dual-harness."

## The validator's role

`scripts/validate.py` is a stdlib-only, dependency-free self-test run from the repo root
(`python3 scripts/validate.py`, add `--json` for machine output). It is the contract that
keeps the two-harness setup honest, checking that:

1. Both plugin manifests parse, agree on a kebab-case `name`, and carry equal semver
   versions (ignoring any Codex `+build` suffix); the Claude Code marketplace references
   this plugin.
2. Every `skills/*/SKILL.md` has frontmatter with a `name` matching its directory and a
   `description` within budget (≤ 400 chars).
3. Each SKILL.md body stays within its context budget (warn over the soft limit,
   hard-fail past the ceiling).
4. Every relative link in a SKILL.md — `references/*.md`, cross-skill paths, `scripts/*` —
   resolves to a real file.
5. Every skill ships a parseable Codex `agents/openai.yaml`.
6. The skill set is discoverable by both harnesses (SKILL.md for both, openai.yaml for
   Codex) — any skill missing either surface is reported.
7. Every asset path referenced by a manifest exists.

CI (`.github/workflows/ci.yml`) runs the validator on push and pull request, so the two
harnesses can never silently drift apart in `main`.

## The `scripts/` diagnostic surface

`validate.py` checks a plugin's *shape*; a family of stdlib-only diagnostics in repo-root
`scripts/` *measures* it. They compose with `skill-curator`, whose own
`skills/skill-curator/scripts/curator.py` does the inventory-wide analysis (sprawl,
collisions, the routing graph) — curator picks *which* target to fix, these quantify *why*.

| Script | What it reports |
|---|---|
| `scripts/validate.py` | The CI contract above — manifests/frontmatter/body-budget/reference-integrity/parity. |
| `scripts/sync.sh` | Installs the repo into `~/.claude` and `~/.codex` (auto-installs on Claude Code via the `claude` CLI). |
| `scripts/score.py` | Deterministic machine sub-score of the audit rubric's objective parts, with a `--min-baseline` CI gate that fails the build on score regression. |
| `scripts/portfolio.py` | Portfolio sweep — runs `score.py` across every local plugin source, emits a fix-first leaderboard (low score × high usage) and a per-plugin score trajectory. |
| `scripts/tokens.py` | Deep per-plugin token / context-budget report — session tax, headroom, and delta vs the stored baseline. |
| `scripts/errscan.py` | Runtime error/health mining from Claude Code and Codex session logs, attributed per plugin/skill. |
| `scripts/route_eval.py` | Empirical routing-accuracy loop wrapping curator's routing probes, with a `--min-baseline` gate so trigger precision is measured, not asserted. |

`plugin-audit` and `plugin-improve` consume `score.py` as their deterministic floor;
`plugin-tune-triggers` and `plugin-improve` consume `route_eval.py`'s measured accuracy as
a non-regression gate. `docs/ROADMAP-measurement-graph.md` maps each script to its
measurement-roadmap phase, and `skill-curator`'s "Companion diagnostics" section shows the
same composition from the skill side. All are stdlib-only except `route_eval.py`'s opt-in
model call.

## Memory model

plugin-improver never mutates the plugins it works on without leaving a trail, and it
never re-litigates decisions across passes. Two artifacts live **inside each target
plugin** (not in this repo):

- **`LEDGER.md`** — an append-only record of what each pass decided and why, with
  provenance. Inherited findings are treated as hypotheses to re-verify, and mistakes are
  withdrawn in the ledger rather than erased.
- **`.plugin-improver/baseline.json`** — the target plugin's last audit score and key
  metrics. `plugin-improve` reads it to gate a pass (re-score must land at or above
  baseline) and writes the new score back when a pass completes.

Together these give every target plugin memory across passes: successive runs compound
improvements and can honestly report "stable" when there is nothing high-leverage left to
change.
