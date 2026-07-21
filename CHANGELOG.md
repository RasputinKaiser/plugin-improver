# Changelog

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
