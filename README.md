# plugin-improver

[![CI](https://github.com/RasputinKaiser/plugin-improver/actions/workflows/ci.yml/badge.svg)](https://github.com/RasputinKaiser/plugin-improver/actions/workflows/ci.yml)

**A meta-plugin that audits, tunes, and evolves your other plugins — and curates your whole skill+plugin inventory — endlessly improvable, never regressing, never bloating context.**

## What it is

plugin-improver is a single plugin that runs on **both Claude Code and Codex** from one shared `skills/` tree. It gives plugin authors a disciplined loop for making plugins better: score a plugin's health, sharpen the descriptions that decide when its skills fire, repair its lifecycle hooks, run bounded improvement passes that are gated against regression, and widen the lens to the entire inventory to catch sprawl, collisions, and version drift. Two new skills round out the lifecycle: scaffolding a fresh dual-harness plugin, and packaging one for release to both marketplaces.

Every skill body, manifest, and doc here is written to be true on both harnesses — the same SKILL.md drives Claude Code (which reads `SKILL.md`) and Codex (which reads `SKILL.md` plus a Codex-only `agents/openai.yaml`).

## Skills

| Skill | What it does |
|---|---|
| `plugin-audit` | Scores a plugin against a 100-point rubric — manifest integrity, skill quality, trigger precision, context economy, hooks health, distribution readiness — and saves a baseline. |
| `plugin-tune-triggers` | Sharpens skill descriptions and trigger phrases so each skill fires exactly when it should, backed by a should/shouldn't-trigger matrix. |
| `plugin-hooks` | Adds, repairs, or reviews lifecycle hooks with correct per-event stdin/stdout contracts and a per-harness capability table for silent failures. |
| `plugin-improve` | The improvement loop: baseline → ≤3 highest-leverage fixes → regression checklist → re-score → version bump → ledger. Reports "stable" instead of churning. |
| `skill-curator` | Inventory-wide curation: skill sprawl, trigger collisions, near-dupes, dead skills, duplicate installs, and source-vs-cache version drift across both harnesses, with an archive-never-delete decision ledger. |
| `plugin-scaffold` | Creates a NEW dual-harness plugin from scratch — canonical layout, both manifests with agreeing versions, a starter skill, and per-harness install steps. |
| `plugin-release` | Packages and publishes an existing plugin to both marketplaces — version/changelog checks, marketplace entries for each harness, tag suggestion, and a post-publish install-refresh reminder. |

## Design principles

- **Improvement without regression.** Every pass is gated by a checklist and must re-score at or above its baseline. A pass that finds nothing worth changing reports "stable" rather than inventing churn.
- **Improvement without bloat.** Descriptions and skill bodies carry explicit context budgets; every added sentence must change agent behavior, and detail is pushed to `references/` for progressive disclosure.
- **Per-plugin memory.** Each target plugin gets a `LEDGER.md` (decisions, with provenance) and a `.plugin-improver/baseline.json` (last score), so successive passes compound instead of relitigating.

## Install

plugin-improver installs on either harness — or both — from this one repository.

### Claude Code

This repo is a single-plugin marketplace (`.claude-plugin/marketplace.json`). Add it, then install the plugin:

```
/plugin marketplace add RasputinKaiser/plugin-improver
/plugin install plugin-improver@plugin-improver
```

You can also point the marketplace at a local clone:

```
/plugin marketplace add /path/to/plugin-improver
```

### Codex

1. Copy (or symlink) this repo to `~/.codex/plugins/plugin-improver`.
2. Add an entry to `~/.agents/plugins/marketplace.json`:

   ```json
   {
     "name": "plugin-improver",
     "source": { "source": "local", "path": "./.codex/plugins/plugin-improver" },
     "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
     "category": "Developer Tools"
   }
   ```

3. Restart Codex, open the plugin directory, choose your personal marketplace, and install.

## Usage

Point any skill at a plugin folder and describe the goal:

- "Audit the plugin in `~/.claude/plugins/my-plugin`."
- "Improve my-plugin" — implicit invocation picks `plugin-improve`.
- "Curate my skills and find version drift."

Both harnesses auto-trigger skills from their descriptions. To invoke one explicitly, use the harness's own syntax: on Codex, `$plugin-improve`; on Claude Code, the matching slash command (`/plugin-improver:plugin-improve`, one per skill) or the Skill tool. The skill bodies are harness-neutral and branch only where the two genuinely diverge (hooks capabilities, feature flags, manifest paths).

## Development

The repo self-validates with a stdlib-only Python script — no dependencies:

```
python3 scripts/validate.py          # human-readable table
python3 scripts/validate.py --json   # machine-readable
```

It checks that both manifests parse and agree, that every SKILL.md has valid frontmatter within its context budget, that every reference link resolves, that each skill ships its Codex `agents/openai.yaml`, and that the plugin is discoverable by both harnesses. CI runs it on every push and pull request (`.github/workflows/ci.yml`). See [`docs/architecture.md`](docs/architecture.md) for how one tree serves both harnesses, and [`docs/skills/`](docs/skills/) for one page per skill.

## License

MIT © [RasputinKaiser](https://github.com/RasputinKaiser)
