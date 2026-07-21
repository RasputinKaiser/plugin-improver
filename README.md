# Plugin Improver

A meta-plugin for Codex: audit, tune, and evolve your other plugins — and curate the whole skill+plugin inventory — endlessly improvable, never regressing, never bloating context.

## Skills

| Skill | What it does |
|---|---|
| `$plugin-audit` | Scores any plugin against a 100-point rubric (manifest, skill quality, triggers, context economy, hooks, distribution) and saves a baseline. |
| `$plugin-tune-triggers` | Sharpens skill descriptions so they fire exactly when they should, backed by a should/shouldn't-trigger test matrix. |
| `$plugin-hooks` | Adds or repairs lifecycle hooks with correct per-event stdin/stdout contracts, plus a diagnostic table for silent failures. |
| `$plugin-improve` | The improvement loop: baseline → ≤3 highest-leverage fixes → regression checklist → re-score → version bump → ledger. Reports "stable" instead of churning. |
| `$skill-curator` | Inventory-wide curation: skill sprawl, trigger collisions, near-dupes, dead skills, duplicate installs, and source-vs-cache plugin version drift across Codex and Claude, with a decision ledger and archive-never-delete moves. |

## Design principles

Improvement without regression: every pass is gated by a checklist and must re-score at or above baseline. Improvement without bloat: descriptions and skill bodies have explicit context budgets; additions must be paid for. A per-plugin `LEDGER.md` and `.plugin-improver/baseline.json` give each target plugin memory across passes.

## Install (personal marketplace)

1. Copy this folder to `~/.codex/plugins/plugin-improver`.
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

Point any skill at a plugin folder: "Use $plugin-audit on ~/.codex/plugins/my-plugin" or just "improve my-plugin" and let implicit invocation pick `$plugin-improve`.
