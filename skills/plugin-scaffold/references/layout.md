# Canonical dual-harness plugin layout + templates

Copy these verbatim, then fill the placeholders. Every template is real and valid as-is.
Replace `<plugin-name>` / `<skill-name>` with kebab-case identifiers matching their directories.

## Tree

```
<plugin-name>/
├─ .claude-plugin/plugin.json          # Claude Code plugin manifest
├─ .claude-plugin/marketplace.json     # Claude Code single-plugin marketplace
├─ .codex-plugin/plugin.json           # Codex plugin manifest (interface, defaultPrompt)
├─ skills/<skill-name>/SKILL.md        # shared, harness-neutral skill body
│                     /agents/openai.yaml   # Codex-only per-skill interface
│                     /references/*.md      # optional progressive disclosure
├─ hooks/hooks.json                     # OPTIONAL — only if reacting to a lifecycle event
├─ scripts/                             # OPTIONAL — hook scripts / helpers
├─ assets/                              # OPTIONAL — icon.svg, logo.svg
├─ README.md
└─ .gitignore
```

Only create a directory when it will hold a file. `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` are the only files that belong inside those two dirs — `skills/`,
`hooks/`, `assets/` all sit at the plugin root.

## `.claude-plugin/plugin.json` (Claude Code)

```json
{
  "name": "<plugin-name>",
  "version": "0.1.0",
  "description": "<one sentence: what the plugin does and when to reach for it>",
  "author": {
    "name": "<public-handle>",
    "url": "https://github.com/<public-handle>"
  },
  "homepage": "https://github.com/<public-handle>/<plugin-name>",
  "license": "MIT",
  "keywords": ["<topic>", "<topic>"]
}
```

## `.codex-plugin/plugin.json` (Codex)

Same `name`; same `version` core semver (a `+build` suffix is the only permitted difference).

```json
{
  "name": "<plugin-name>",
  "version": "0.1.0",
  "description": "<same one sentence as the Claude Code manifest>",
  "author": {
    "name": "<public-handle>",
    "url": "https://github.com/<public-handle>"
  },
  "license": "MIT",
  "keywords": ["<topic>", "<topic>"],
  "skills": "./skills/",
  "interface": {
    "displayName": "<Title Case, 1-3 words>",
    "shortDescription": "<= 8 words, verb-first",
    "longDescription": "2-4 sentences of benefits, not file structure.",
    "developerName": "<public-handle>",
    "category": "Developer Tools",
    "capabilities": ["Read", "Write"],
    "brandColor": "#5B8DEF",
    "defaultPrompt": [
      "Use $<skill-name> to <do the thing it does>."
    ]
  }
}
```

## `.claude-plugin/marketplace.json` (Claude Code, single-plugin)

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "<plugin-name>",
  "description": "Single-plugin marketplace for <plugin-name>.",
  "owner": {
    "name": "<public-handle>",
    "url": "https://github.com/<public-handle>"
  },
  "plugins": [
    {
      "name": "<plugin-name>",
      "description": "<same one sentence>",
      "author": { "name": "<public-handle>", "url": "https://github.com/<public-handle>" },
      "category": "development",
      "source": ".",
      "homepage": "https://github.com/<public-handle>/<plugin-name>",
      "license": "MIT"
    }
  ]
}
```

## `skills/<skill-name>/SKILL.md`

```markdown
---
name: <skill-name>
description: <Verb-first, what it does + trigger phrases users say. Add a NOT clause if a sibling skill could steal the trigger. <= 400 chars.>
---

<Imperative agent instructions — the real steps the skill runs. Verb-first, concrete.
Push long templates/schemas into references/, don't inline them.>
```

## `skills/<skill-name>/agents/openai.yaml` (Codex-only)

```yaml
interface:
  display_name: "<Title Case>"
  short_description: "<short verb phrase>"
  brand_color: "#5B8DEF"
  default_prompt: "<a real prompt a user would send>"
```

## `hooks/hooks.json` (optional)

Use the portable `${CLAUDE_PLUGIN_ROOT}` (Codex sets it too, and also accepts `${PLUGIN_ROOT}`).
On Codex, PreToolUse/PostToolUse fire for Bash only and sit behind `[features] codex_hooks = true`
plus trust — don't wire an event the harness can't run.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/scripts/on-start.sh" }
        ]
      }
    ]
  }
}
```
