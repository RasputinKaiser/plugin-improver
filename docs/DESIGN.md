# plugin-improver — dual-harness rebuild (design + worker contract)

This document is the single source of truth for the rebuild. Every worker MUST read it
before editing and MUST conform to the conventions here so the parallel slices integrate
cleanly. Target: `github.com/RasputinKaiser/plugin-improver`, public, MIT.

## What plugin-improver is

A meta-plugin for **both Claude Code and Codex**: audit, tune, and evolve *other*
plugins, and curate the whole skill+plugin inventory — endlessly improvable, never
regressing, never bloating context. Skills: `plugin-audit`, `plugin-hooks`,
`plugin-improve`, `plugin-tune-triggers`, `skill-curator`, plus two NEW skills this
rebuild adds: `plugin-scaffold` (create a new dual-harness plugin) and `plugin-release`
(package + publish to both marketplaces).

## Hard constraints (never violate)

1. **Identity:** author is `RasputinKaiser` only. The maintainer's legal name must NEVER
   appear in any file, manifest, commit, or doc. If you are unsure whether a string is a
   real name, leave it out.
2. **Never rename** the plugin or any existing skill `name` — they are identifiers users
   and configs depend on. New skills use kebab-case `name` matching their directory.
3. **Context discipline:** this is a major version, so growth is allowed, but every added
   sentence must change agent behavior. Push detail to `references/`, never inline it.
   Descriptions ≤ 2 sentences of substance, ≤ 400 chars. Skill bodies ≤ ~600 words.
4. **Dual-harness correctness:** every skill body, manifest, and doc must be correct for
   BOTH harnesses. Never write "Codex plugin" when you mean "plugin". See conventions.

## Repository layout (final)

```
plugin-improver/
├─ README.md CHANGELOG.md CONTRIBUTING.md LICENSE .gitignore
├─ .github/workflows/ci.yml            # runs scripts/validate.py on push + PR
├─ .claude-plugin/plugin.json          # Claude Code plugin manifest
├─ .claude-plugin/marketplace.json     # Claude Code single-plugin marketplace
├─ .codex-plugin/plugin.json           # Codex plugin manifest (interface, defaultPrompt)
├─ skills/<skill>/SKILL.md             # shared, harness-NEUTRAL body
│                /agents/openai.yaml    # Codex-only per-skill interface (Claude ignores)
│                /references/*.md       # progressive disclosure
│                /scripts/*             # only skill-curator today
├─ scripts/validate.py                 # the validator / self-test (stdlib only)
├─ scripts/sync.sh                      # install repo → ~/.codex and ~/.claude
├─ docs/DESIGN.md (this) docs/architecture.md docs/skills/*.md
└─ assets/plugin-improver-icon.svg  assets/plugin-improver-logo.svg
```

## Dual-harness conventions (the correctness rules every skill body follows)

The two harnesses differ; skill bodies must be written so they are true on both.

| Concern | Claude Code | Codex | How to write it in a skill body |
|---|---|---|---|
| Plugin manifest | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | Say "the plugin manifest(s)". When locating a plugin root, look for **either** `.claude-plugin/plugin.json` **or** `.codex-plugin/plugin.json`. A dual-harness plugin has both. |
| Install root | `~/.claude/plugins/` | `~/.codex/plugins/` | Say "the harness plugin dir (`~/.claude/plugins/` or `~/.codex/plugins/`)". |
| Marketplace | `.claude-plugin/marketplace.json` | `~/.agents/plugins/marketplace.json` entry / `~/.codex/config.toml [marketplaces]` | Mention both when relevant. |
| Invoke a skill | Skill tool / auto-trigger via description; `/name` for commands | `$name`, or auto-trigger | Write "invoke `plugin-improve`" (no `$`). Only show `$name` / Skill-tool syntax when the difference matters, and then show both. |
| Per-skill interface | ignored (no openai.yaml) | `agents/openai.yaml` | openai.yaml is Codex-only surface; keep it, note it's Codex-only. |
| Hooks env var | `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` | `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` (also sets CLAUDE_* for compat) | Use `${CLAUDE_PLUGIN_ROOT}` as the portable form (Codex sets it too); note Codex also accepts `${PLUGIN_ROOT}`. |
| Hook tool events | matchers match ALL tools (Edit, Write, Read, Bash, MCP…) | PreToolUse/PostToolUse are **Bash-only today**; matchers ignored on UserPromptSubmit/Stop | plugin-hooks must present a per-harness capability table, not a single one. |
| Hook feature flag | on by default | experimental: `[features] codex_hooks = true`, must be trusted | plugin-hooks must call out Codex's flag+trust gate as Codex-only. |

**Rule of thumb:** default wording is harness-neutral ("the plugin", "the manifest(s)",
"invoke X"). Only branch into "On Codex… / On Claude Code…" where the harnesses genuinely
diverge (hooks capabilities, feature flags, manifest paths when locating). Do not double
every sentence — branch only where it's true.

## validate.py contract (scripts/validate.py) — the shared spec all workers build to

Stdlib-only Python 3. `python3 scripts/validate.py [--json]` run from repo root.
Exit 0 = all pass; exit 1 = any failure. Human-readable table by default. Checks:

1. **Manifests parse & agree.** `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`
   both parse as JSON; `name` identical and kebab-case in both; `version` semver and equal
   in both (ignoring any Codex `+build` metadata suffix); `.claude-plugin/marketplace.json`
   parses and references this plugin.
2. **Skill frontmatter.** Every `skills/*/SKILL.md` has YAML frontmatter with `name`
   (matches dir, kebab-case) and `description`; description ≤ 400 chars.
3. **Body budget.** Each SKILL.md body ≤ 600 words (warn), hard-fail > 1500.
4. **Reference integrity.** Every relative link in a SKILL.md (e.g. `references/x.md`,
   `../plugin-audit/references/y.md`, `scripts/z.py`) resolves to an existing file.
5. **Codex per-skill interface.** Every skill has `agents/openai.yaml` that parses (YAML;
   use a tiny stdlib parse or a minimal hand parser — do NOT add a pyyaml dependency; a
   line-based check for `interface:` + `display_name:` is acceptable).
6. **Parity.** The set of skill dirs is consistent; each skill is discoverable by both
   harnesses (SKILL.md present for both; openai.yaml present for Codex). Report any skill
   missing either.
7. **Assets.** Every asset path referenced by either manifest exists.

Print a summary line `PASS n/n` / `FAIL: <count>`. Keep it under ~250 lines, readable.
Design the check registry as a list of `(name, fn)` so adding checks is trivial.

## Two new skills

### skills/plugin-scaffold/
Creates a NEW dual-harness plugin from scratch, correctly structured for both harnesses
(fills the gap the other skills punt on — "not for first-time plugin creation"). Body:
gather intent → lay down the layout above → write both manifests (agreeing versions) →
one starter skill with valid frontmatter + openai.yaml → optional hooks stub → run
`validate.py` (or the inline checks) → tell the user how to install on each harness.
Description must NOT collide with `plugin-improve` (improve EXISTING) — add a NOT clause.
Include `agents/openai.yaml`. Reference file: `references/layout.md` with the canonical
tree + minimal manifest templates for both harnesses.

### skills/plugin-release/
Packages and publishes an existing plugin to both marketplaces: verify clean state + green
validator → bump/confirm agreeing versions across all manifests → update CHANGELOG →
produce/update the Claude Code `.claude-plugin/marketplace.json` entry and the Codex
marketplace registration snippet (`~/.agents/plugins/marketplace.json` /
`~/.codex/config.toml`) → git tag suggestion → post-publish install-refresh reminder per
harness. It does NOT judge quality (that's plugin-audit) and does NOT create plugins
(that's plugin-scaffold) — add NOT clauses. Include `agents/openai.yaml`. Reference:
`references/marketplace-formats.md` (both marketplace manifest shapes, side by side).

## scoring-rubric parity dimension

`skills/plugin-audit/references/scoring-rubric.md` gains explicit **cross-harness parity**
credit inside existing dimensions (do NOT change the 100-point total): under Manifest
integrity, require that a plugin claiming dual-harness support ships BOTH manifests with
agreeing versions; under Distribution readiness, require marketplace entries for each
harness it targets. Keep total = 100; redistribute within dimensions, don't add points.

## Out of scope (do not do)

- No new plugin skills beyond the two named.
- No rename/removal of existing skills.
- Do not touch the user's live installs during worker runs — the integrator handles sync.
- No heavyweight test framework beyond validate.py + CI wiring.
