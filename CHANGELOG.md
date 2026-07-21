# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## 1.3.0 - 2026-07-20

### Added
- **Deterministic scorer + CI gate (roadmap Phase 2).** New `scripts/score.py` computes the machine-verifiable floor of the 100-pt audit rubric per dimension (`{auto, max, needs_judgment}`), with `--json`/`--md`, a `--min N` floor gate, and a `--min-baseline PATH` regression gate. Wired into `.github/workflows/ci.yml` alongside the existing validator + curator selftests.
- **Portfolio sweep (roadmap Phase 3).** New `scripts/portfolio.py` scores every local plugin **source** (never read-only caches), prints a fix-first leaderboard, and persists per-plugin score history so slow rot shows as a trajectory delta.
- **Empirical routing-evaluation loop (roadmap Phase 4).** New `scripts/route_eval.py` wraps `skill-curator`'s probes: generates near-miss probes prioritized by the G_t collision graph's confusable pairs, scores a confusion matrix + per-skill precision/recall, and gates description changes on measured accuracy ≥ baseline. Offline manual router by default (no model dependency).
- **Runtime error / health mining.** New `scripts/errscan.py` scans Claude Code + Codex session logs for hook failures, tool errors, and skill-invocation failures, attributed per `plugin:skill`, with hard secret-redaction and an incremental cache. The health counterpart to curator's usage mining.
- **Deep token / context-budget report.** New `scripts/tokens.py` reports per-skill trigger-vs-invoke tokens, per-plugin "session tax", budget headroom vs the rubric, and a baseline delta to catch slow bloat (`--save-baseline`, `--max-trigger-tokens N` gate).

### Changed
- **`scripts/validate.py` is now a diagnostic linter.** Every finding carries a stable code (`PI-<letter>NNN`), a severity (`error`/`warn`/`info`), and a one-line fix hint; `--json` gains a flat `findings` array while keeping the legacy `results`/`passed`/`total`/`summary` keys. Three new mechanical checks added (hook script exists/executable/uses `${CLAUDE_PLUGIN_ROOT}`; `.mcp.json` shape; dead/empty files under `skills/`). Exit-code contract preserved (self-validates `PASS 11/11`).
- **`plugin-audit`, `plugin-improve`, `plugin-tune-triggers` now consume the new diagnostics.** Audit folds in the deterministic floor + token + runtime-error signals (rubric total unchanged at 100); improve's non-regression gate now carries numbers (score/tokens/errors/routing baselines); tune-triggers is graph-driven and gated on measured routing accuracy.
- Docs: `docs/ROADMAP-measurement-graph.md` marks Phases 2–4 delivered; `docs/architecture.md` documents the new `scripts/` diagnostic surface. `plugin-migrate` remains intentionally unbuilt (out of scope; roster stays 7 skills).

## 1.2.0 - 2026-07-20

### Added
- **Routing graph (roadmap Phase 1).** `skill-curator` now models the inventory as two graphs: a trigger-collision graph (weighted edges from shared trigger phrases + description overlap) and a directed reference/handoff graph. New `curator.py graph [--md|--mermaid|--dot|--json]` subcommand and a folded summary in `report` surface: collision clusters, **centrality-ranked trigger-hogs** (which skill steals prompts from the most siblings), a **minimal-edit set** (which K descriptions to fix to break the most collisions), and orphan skills / broken handoffs / cycles from the reference graph. Stdlib only; 14 new deterministic selftests (69 → 83).

## 1.1.1 - 2026-07-20

### Changed
- **`scripts/sync.sh` now installs on Claude Code automatically** when the `claude` CLI is present: it adds/refreshes the marketplace and installs/updates the plugin (`claude plugin marketplace add|update`, `claude plugin install|update`), instead of only printing the interactive `/plugin` commands. Idempotent; falls back to printing the slash commands if the CLI is absent.

## 1.1.0 - 2026-07-20

### Added
- **Claude Code slash commands.** A `commands/` file per skill (`/plugin-improver:plugin-audit`, `…:plugin-improve`, and so on) gives Claude Code users explicit invocation matching Codex's `$skill`. Auto-discovered by Claude Code; ignored by Codex. `scripts/validate.py` gained a "Claude Code commands" check (well-formedness always; one-command-per-skill enforced for plugin-improver itself).

## 1.0.1 - 2026-07-20

### Changed
- **`scripts/validate.py` is now target-aware:** `python3 scripts/validate.py <plugin-dir>` validates any dual-harness plugin (the fixed 7-skill roster is enforced only for plugin-improver itself). This makes `plugin-scaffold`'s and `plugin-release`'s validation steps actually runnable against other plugins.

### Fixed
- Adversarial audit fixes: reference-integrity now also scans `references/*.md` (code-fence templates and absolute-path fragments excluded); marketplace check matches `plugins[].name` instead of a loose substring.
- Scoring rubric no longer applies Codex-only `policy.installation`/`policy.authentication` to Claude Code marketplace entries, and lets the trigger opt-out points be earned on Claude Code (no `openai.yaml` flag there). Rubric still totals 100.
- Corrected skill instructions: `plugin-release` validator path (`scripts/validate.py`, not `../../`), `plugin-scaffold` validation step, the Codex `source.path` marketplace example, a false `plugin.json` `icon` field claim, and a hook-input `model`-field caveat for Claude Code.
- `scripts/sync.sh` no longer clobbers a Codex install's `state.yaml` (excluded from `--delete`).

## 1.0.0 - 2026-07-20

### Added
- **Dual-harness support.** plugin-improver now runs on **both Claude Code and Codex** from one shared `skills/` tree. Added the Claude Code plugin manifest (`.claude-plugin/plugin.json`) and single-plugin marketplace (`.claude-plugin/marketplace.json`) alongside the existing Codex manifest.
- **`plugin-scaffold`** — creates a NEW dual-harness plugin from scratch: canonical layout, both manifests with agreeing versions, a starter skill, and per-harness install steps.
- **`plugin-release`** — packages and publishes an existing plugin to both marketplaces: version/changelog checks, a marketplace entry for each targeted harness, a git-tag suggestion, and a post-publish install-refresh reminder.
- **Validator + CI.** `scripts/validate.py` (stdlib only) checks manifest agreement, skill frontmatter and body budgets, reference-link integrity, per-skill Codex interfaces, cross-harness parity, and asset paths. `.github/workflows/ci.yml` runs it on every push and pull request.
- **Docs.** Open-source README, `docs/architecture.md`, and one page per skill under `docs/skills/`.

### Changed
- **Repo-ification.** Restructured for a public MIT release at `github.com/RasputinKaiser/plugin-improver`.
- Existing skill bodies, descriptions, and the audit rubric now read as harness-neutral and credit cross-harness parity (both manifests present with agreeing versions; a marketplace entry per targeted harness), keeping the audit total at 100.

### Notes
- This release **does not rename or remove any existing skill**. `plugin-audit`, `plugin-hooks`, `plugin-improve`, `plugin-tune-triggers`, and `skill-curator` keep their names and identifiers.

## 0.4.0 - 2026-07-20

- Merged skill-curator into the plugin as a fifth skill (was a standalone skill duplicated across both user-level skill stores).
- skill-curator v3: plugin-level curation - source-vs-cache version drift, plugins installed from 2+ marketplaces, stale cached versions; cross-ecosystem defaults now include plugin SOURCE roots. Selftest grown to 62 checks.
- skill-curator description trimmed to 391 chars and routing-evals/plugin-eval detail moved to a lazy reference (body 563 words, within budget).
- plugin-audit description gains a sibling boundary clause (inventory-wide curation -> skill-curator).
- Trigger matrix covers all five skills.

## 0.3.4 - 2026-07-13

- Regression checklist: run the target plugin's own tests/build (state-file "green" claims are not evidence); verify artifact content, not exit banners.
- Baseline step: inherited findings are hypotheses - re-verify before acting, withdraw mistakes in the ledger.
- Audit rubric: multi-manifest version drift is now an explicit manifest-integrity deduction.

## 0.3.3 - 2026-07-13

- ralto-local marketplace entry: added policy.authentication; verified source.path resolves.
- plugin-improve Record step: sync sibling manifests (.claude-plugin/.ncode-plugin) on version bump.
- Added .plugin-improver/trigger-matrix.md for this plugin's own skills.

## 0.3.2 - 2026-07-07

- Failure fallbacks for stripped installs (missing rubric/checklist); audit locate step forbids editing cache copies; own LEDGER + baseline created.

## 0.3.1 - 2026-07-02

- Tightened Codex app presentation metadata for the plugin card and composer.
- Added reusable plugin assets for the composer icon and detail logo.
- Added per-skill `agents/openai.yaml` metadata so each skill has a polished Codex skills-list surface.
- Updated public author identity to `RasputinKaiser`.
