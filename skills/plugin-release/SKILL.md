---
name: plugin-release
description: Package and publish an existing dual-harness plugin to the Claude Code and Codex marketplaces. Use when asked to publish, release, package for the marketplace, ship a version, or cut a release: bump agreeing versions, update the changelog, refresh both marketplace manifests, and suggest a git tag. Not for judging plugin quality (plugin-audit) or creating a plugin from scratch (plugin-scaffold).
---

Ready an existing plugin for publication to both marketplaces. This skill prepares everything and hands the user the exact commands — it NEVER runs the final tag, push, or publish itself. Stop and confirm before any irreversible step.

## 1. Preconditions — block on any failure

- **Clean git state:** `git status --porcelain` must be empty. Uncommitted work → stop; ask the user to commit or stash.
- **Green validator:** run `../../scripts/validate.py` from the repo root; it must exit 0. Any FAIL → stop and report. Publishing a broken plugin is regression.
- **Agreeing versions:** read `version` from `.claude-plugin/plugin.json` AND `.codex-plugin/plugin.json` (ignore any Codex `+build` suffix). They must already match. Drift → stop and reconcile first.

## 2. Confirm or bump the version

Ask the user which release this is, or infer from the CHANGELOG's unreleased notes: **patch** for fixes/wording, **minor** for new capability, **major** for anything breaking (renamed/removed skills, changed hook behavior). Set the SAME `X.Y.Z` in BOTH manifests together — never one without the other. Preserve the Codex `+build.<timestamp>` metadata convention if the repo uses it.

## 3. Update the CHANGELOG

Add a `## X.Y.Z - <date>` section at the top of `CHANGELOG.md`. One line per entry, agent-facing behavior deltas — not marketing. Fold any "unreleased" notes into it.

## 4. Refresh both marketplace manifests

The two shapes and their fields sit side by side in `references/marketplace-formats.md`. Update or create:

- **Claude Code** — `.claude-plugin/marketplace.json` (a repo file): ensure the `plugins[]` entry for this plugin exists and its `description`/`keywords`/`homepage` match the plugin manifest; `source` is `"."` for the single-plugin repo marketplace, or a `git-subdir` object for a hosted directory.
- **Codex** — the `~/.agents/plugins/marketplace.json` entry (`plugins[]` object: `name`, `source`, `policy`, `category`) and/or the `~/.codex/config.toml [marketplaces.<name>]` block. These are per-USER files, not repo files: produce the exact snippet for the user to paste; do NOT silently edit their live config.

## 5. Suggest the tag and publish commands

Do not run these — print them for the user:

```
git add -A && git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

Note that a public marketplace pulls from the tagged ref/sha, and that a commit touching `.github/workflows/*` needs `workflow` credential scope to push.

## 6. Per-harness install-refresh reminder

- **Claude Code:** `/plugin marketplace update <name>`, then reinstall/update the plugin; restart if skills don't refresh.
- **Codex:** restart Codex, reopen the marketplace, reinstall so the local install picks up the new version. The installed cache lags the source until refreshed — see the version-drift caution in the reference.

## Report format

Follow the shared style in `../plugin-audit/references/report-style.md`; close with a compact readiness block:

```
## Release ready: plugin-improver v1.0.0 → v1.1.0

✅ clean tree · ✅ validate.py 12/12 · ✅ versions agree · 🧾 CHANGELOG updated

| Manifest | Action |
|---|---|
| `.claude-plugin/plugin.json` | version → 1.1.0 |
| `.codex-plugin/plugin.json` | version → 1.1.0+codex.… |
| `.claude-plugin/marketplace.json` | entry refreshed |
| `~/.agents/plugins/marketplace.json` | paste snippet below |

Run when ready: `git tag v1.1.0 && git push --tags`
```

If a precondition failed, lead with that and ship nothing.
