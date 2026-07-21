---
description: Add, repair, or review a plugin's lifecycle hooks
argument-hint: "[plugin-dir]"
---
Use the **plugin-hooks** skill on the plugin at $ARGUMENTS (default: current directory) to add, repair, or review lifecycle hooks. Respect the per-harness capability differences (Claude Code matches all tools and hooks are on by default; Codex is Bash-only today and gated by an experimental flag plus trust), test each script against a sample payload, and report verdict-first.
