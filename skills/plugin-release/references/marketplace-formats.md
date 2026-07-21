# Marketplace manifest formats (Claude Code vs Codex)

A dual-harness plugin is published through TWO independent marketplace mechanisms. Keep both in sync with the plugin manifests on every release.

## (a) Claude Code — `.claude-plugin/marketplace.json`

A repo file. One marketplace can list many plugins; a single-plugin repo lists one with `source: "."`.

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "plugin-improver",
  "description": "Single-plugin marketplace for plugin-improver.",
  "owner": { "name": "RasputinKaiser", "url": "https://github.com/RasputinKaiser" },
  "plugins": [
    {
      "name": "plugin-improver",
      "description": "…matches the plugin manifest description…",
      "author": { "name": "RasputinKaiser", "url": "https://github.com/RasputinKaiser" },
      "category": "development",
      "source": ".",
      "homepage": "https://github.com/RasputinKaiser/plugin-improver",
      "license": "MIT",
      "keywords": ["plugins", "meta", "audit"]
    }
  ]
}
```

`source` variants for a hosted directory (pin the release):

```json
"source": {
  "source": "git-subdir",
  "url": "https://github.com/RasputinKaiser/plugin-improver.git",
  "path": ".",
  "ref": "v1.1.0",
  "sha": "<commit-sha>"
}
```

`ref`/`sha` are what pin consumers to a specific release — bump them when you tag.

## (b) Codex — two registration forms

Codex registers marketplaces per USER, not from a repo file. Use either form (or both); produce the snippet for the user to paste — never silently edit their live config.

**Form 1 — `~/.agents/plugins/marketplace.json`** (a `plugins[]` entry in the user's local marketplace):

```json
{
  "name": "plugin-improver",
  "source": { "source": "local", "path": "./plugins/plugin-improver" },
  "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
  "category": "Developer Tools"
}
```

`source.path` is relative to the marketplace file's own directory (`~/.agents/plugins/`), so `./plugins/<name>` resolves to `~/.agents/plugins/plugins/<name>`. Use whatever path actually holds the plugin — an absolute path to a repo checkout is fine; verify the target exists before handing the snippet over.

**Form 2 — `~/.codex/config.toml` `[marketplaces.<name>]`** (registers a source root directly):

```toml
[marketplaces.plugin-improver-local]
last_updated = "2026-07-20T00:00:00Z"
source_type = "local"
source = "/Users/<you>/Code/plugin-improver"
```

After registering, the user restarts Codex, opens the marketplace, and installs the plugin.

## Version drift caution: source vs installed cache

The version you edit in the repo manifests is the SOURCE version. Both harnesses install into a local CACHE that does not update automatically:

- Claude Code copies under `~/.claude/plugins/…`; Codex under `~/.codex/plugins/…` (read-only cache copies under `~/.codex/plugins/cache/` must never be edited).

A freshly bumped source will not take effect until the user refreshes the install (Claude Code: `/plugin marketplace update` + reinstall; Codex: restart + reinstall). Until then the running plugin reports the OLD version. When diagnosing "my change didn't apply", compare the source manifest version against the installed copy's version before assuming the edit was wrong.
