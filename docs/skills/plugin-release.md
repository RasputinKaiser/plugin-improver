# plugin-release

Source: [`../../skills/plugin-release/SKILL.md`](../../skills/plugin-release/SKILL.md)

## Purpose

Packages and publishes an existing plugin to both marketplaces: verifies a clean state and a
green validator, bumps/confirms agreeing versions across all manifests, updates the
changelog, produces the Claude Code `.claude-plugin/marketplace.json` entry and the Codex
marketplace registration snippet, suggests a git tag, and prints a post-publish
install-refresh reminder per harness.

## When it fires

When asked to package, publish, release, or ship a plugin to its marketplaces. It does not
judge quality (`plugin-audit`) and does not create plugins (`plugin-scaffold`).

## References

- [`references/marketplace-formats.md`](../../skills/plugin-release/references/marketplace-formats.md) — the Claude Code and Codex marketplace manifest shapes, side by side.
