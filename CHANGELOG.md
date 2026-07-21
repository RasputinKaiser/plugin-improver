# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

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
