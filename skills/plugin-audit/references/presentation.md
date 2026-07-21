# Visual presentation

How a plugin LOOKS on its install/detail page and in the composer.

**Harness scope.** The `interface` block below and per-skill `agents/openai.yaml` are the **Codex-only** presentation surface — Claude Code ignores both. Claude Code reads its own display fields from `.claude-plugin/plugin.json` (`name`, `displayName`, `description`, `author`, `homepage`, `keywords`) and renders skills from their SKILL.md frontmatter; the Claude Code plugin manifest has no `icon` field. When auditing a dual-harness plugin, check Codex presentation here and confirm the Claude Code `plugin.json` carries a clean `description`/`author`; do not penalize a Claude-Code-only plugin for lacking `interface`/openai.yaml.

## Plugin-level `interface` (Codex `.codex-plugin/plugin.json`)

```json
"interface": {
  "displayName": "Plugin Improver",
  "shortDescription": "Continuously improve existing plugins",
  "longDescription": "2–4 sentences. Renders as body copy on the detail page.",
  "developerName": "Your name",
  "category": "Developer Tools",
  "capabilities": ["Read", "Write"],
  "brandColor": "#5B8DEF",
  "composerIcon": "./assets/icon.png",
  "logo": "./assets/logo.png",
  "screenshots": ["./assets/screenshot-1.png"],
  "defaultPrompt": [
    "Use $plugin-audit to score the plugin in this folder."
  ]
}
```

Craft rules:

- `displayName`: Title Case, 1–3 words, no "Plugin" suffix unless it reads naturally.
- `shortDescription`: ≤ 8 words, verb-first — it's the subtitle under the title.
- `longDescription`: benefits, not file structure. Never paste the manifest description verbatim; the detail page shows both.
- `defaultPrompt`: 3–4 entries; each renders as a tappable starter card. Write them as real prompts a user would send, each showcasing a DIFFERENT skill. Start with "Use $skill-name to…" so invocation is explicit.
- `brandColor`: one saturated mid-tone hex that survives dark UI (the Codex app is dark); avoid near-black/near-white.
- `category`: pick a real store category (Developer Tools, Productivity…), consistent with the marketplace entry.

## Assets (`./assets/`)

| Asset | Use | Spec |
|---|---|---|
| `composerIcon` | shown next to $mentions in composer | square PNG/SVG, ≥256px, legible at 16px, transparent bg |
| `logo` | detail-page hero | square, ≥512px |
| `screenshots` | detail-page gallery | app-window ratio, show OUTPUT (a scorecard, a report), not file trees |

Missing icon = generic placeholder tile in the directory. For a shareable plugin, flag a missing `composerIcon` as a 🟡 finding.

## Per-skill polish (Codex-only: `skills/<name>/agents/openai.yaml`)

```yaml
interface:
  display_name: "Plugin Audit"
  short_description: "Score any plugin's health out of 100"
  icon_small: "./assets/icon-small.svg"
  icon_large: "./assets/icon-large.png"
  brand_color: "#5B8DEF"
  default_prompt: "Audit the plugin in this folder and show the scorecard"
```

- `display_name`: humanized Title Case (skill `name` stays kebab-case — never change it).
- `short_description`: this is what the Skills list shows under the toggle; without it the raw frontmatter description is truncated with "…". Any skill whose frontmatter description is > ~90 chars should get one.
- Keep skill `brand_color` matching the plugin `brandColor` for a coherent family.

## Audit checks (fold into Distribution readiness)

- 🟡 `interface` missing entirely on a plugin that is shared or in a marketplace.
- 🟡 `shortDescription` > 8 words, or duplicates `description`.
- 🟡 No `defaultPrompt`, or prompts that don't name a `$skill`.
- 🟢 Skills lacking `agents/openai.yaml` short_descriptions (truncated text in the Skills list).
- 🟢 `brandColor` absent or illegible on dark backgrounds.
- Verify every referenced asset file exists; a broken `./assets/` path renders as an empty image.

Verification: after changes, open the plugin's detail page in the Codex app (Plugins → your marketplace → plugin) and confirm title, subtitle, starter cards, and icons render as intended.
