# plugin-hooks

Source: [`../../skills/plugin-hooks/SKILL.md`](../../skills/plugin-hooks/SKILL.md)

## Purpose

Adds, repairs, or reviews lifecycle hooks in a plugin (`hooks/hooks.json`) with correct
per-event stdin/stdout contracts, and diagnoses hooks that silently fail to fire.

## When it fires

When asked to run something on session start, guard or review Bash commands, inject context
on user prompts, keep the agent going on stop, or when a hook is silently not firing,
blocked, or stuck in trust review. Not for MCP servers or skill authoring.

## Per-harness note

Hook capabilities differ between the harnesses: Claude Code matchers match all tools, while
Codex `PreToolUse`/`PostToolUse` are Bash-only today and its hooks are experimental behind a
feature flag plus trust gate. The skill presents a per-harness capability table rather than a
single one.

## References

- [`references/hooks-reference.md`](../../skills/plugin-hooks/references/hooks-reference.md) — per-event contracts and the per-harness capability/diagnostic table.
