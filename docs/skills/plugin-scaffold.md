# plugin-scaffold

Source: [`../../skills/plugin-scaffold/SKILL.md`](../../skills/plugin-scaffold/SKILL.md)

## Purpose

Creates a NEW dual-harness plugin from scratch, correctly structured for both Claude Code
and Codex: gathers intent, lays down the canonical layout, writes both manifests with
agreeing versions, adds one starter skill (valid frontmatter + `agents/openai.yaml`), an
optional hooks stub, runs the validator, and prints per-harness install steps.

## When it fires

When asked to create a plugin, make a new plugin, scaffold a plugin, or start a plugin from
scratch. Not for improving or auditing an EXISTING plugin (`plugin-improve` /
`plugin-audit`).

## References

- [`references/layout.md`](../../skills/plugin-scaffold/references/layout.md) — the canonical directory tree with minimal manifest templates for both harnesses.
