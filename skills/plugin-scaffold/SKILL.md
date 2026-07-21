---
name: plugin-scaffold
description: Create a NEW dual-harness plugin from scratch for both Claude Code and Codex. Use when asked to create a plugin, make a new plugin, scaffold a plugin, or start a plugin from scratch. Lays down the layout, both manifests with agreeing versions, a starter skill, and install steps. Not for improving or auditing an EXISTING plugin (use plugin-improve / plugin-audit).
---

Create a well-formed dual-harness plugin from nothing. The contract: what you lay down parses on both harnesses, ships both manifests with agreeing versions, and passes `scripts/validate.py` before you hand it back. Never guess schema — copy the templates in `references/layout.md`.

## 1. Gather intent

Ask only what you can't infer, in one turn:

- **Name** — kebab-case, becomes the plugin dir and both manifests' `name`. Reject spaces/caps.
- **What it does** — one sentence; seeds the manifest `description` and the starter skill.
- **Skills** — the first skill's name and job (scaffold exactly one; more come later).
- **Target harnesses** — both (default), or one. Even single-harness plugins get both manifests so they stay portable; note which is primary.
- **Hooks?** — only if the user names a lifecycle event to react to.

Do not scaffold commands, MCP servers, or extra skills unprompted. One skill, done right.

## 2. Lay down the layout

Create the tree from `references/layout.md` under `<plugin-name>/`: `.claude-plugin/`, `.codex-plugin/`, `skills/<skill>/`, `assets/`, `README.md`, `.gitignore`. Directories only where they'll hold a file.

## 3. Write BOTH manifests — agreeing versions

Copy the two manifest templates from `references/layout.md` and fill them:

- `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` — identical `name` (kebab-case) and `version`. Start at `0.1.0`.
- Versions MUST agree. If Codex needs build metadata, only a `+build` suffix may differ (`0.1.0` vs `0.1.0+codex.<stamp>`); the core semver is the same.
- `author.name` is the user's public handle only — never a legal name.
- Add `.claude-plugin/marketplace.json` referencing the plugin with `"source": "."` so it's installable locally from day one.

## 4. One starter skill

In `skills/<skill>/`:

- `SKILL.md` with frontmatter `name` (matches the dir, kebab-case) + `description` (≤ 400 chars, verb-first trigger phrasing, a NOT clause if a sibling could collide). Body: a few imperative lines the agent runs — real, not a "TODO" placeholder.
- `agents/openai.yaml` — the Codex-only per-skill interface (`display_name`, `short_description`, `brand_color`, `default_prompt`). Claude Code ignores it; keep it anyway so the skill is discoverable on both.

Write both from the templates in `references/layout.md`.

## 5. Optional hooks stub

Only if requested. Add `hooks/hooks.json` with one event and a command referencing `${CLAUDE_PLUGIN_ROOT}` (portable — Codex sets it too, and also accepts `${PLUGIN_ROOT}`). Point it at a real script under `scripts/`. On Codex, note that PreToolUse/PostToolUse are Bash-only and hooks sit behind `[features] codex_hooks = true` plus trust — don't wire an event the harness can't fire.

## 6. Validate

Validate the new plugin with the improver's validator, which takes a target path: `python3 <plugin-improver>/scripts/validate.py <new-plugin-dir>`. It checks that both manifests parse and agree, frontmatter is valid, references resolve, and every skill has `openai.yaml` (the fixed 7-skill roster is only enforced when validating the improver itself). If the improver isn't on hand, verify those same items by inspection. Fix every failure before reporting — a scaffold that doesn't validate is not done.

## 7. Install instructions

Print both, per the shared report style (`../plugin-audit/references/report-style.md`):

- **Claude Code** — `/plugin marketplace add <path>` then `/plugin install <name>@<name>`.
- **Codex** — register the local marketplace in `~/.codex/config.toml` / `~/.agents/plugins/marketplace.json`, then restart Codex.

End with a compact "Scaffolded" summary: the tree created, the version, and the one next step (`invoke plugin-audit to score it`).
