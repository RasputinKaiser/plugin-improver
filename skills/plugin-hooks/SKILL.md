---
name: plugin-hooks
description: Add, repair, or review lifecycle hooks in a plugin (hooks/hooks.json) for Claude Code and Codex. Use when asked to run something on session start, guard or review Bash commands, inject context on user prompts, keep the agent going on stop, or when a hook is silently not firing, blocked, or stuck in trust review. Not for MCP servers or skill authoring.
---

Add or repair lifecycle hooks in the target plugin. Hooks are deterministic scripts the harness runs at lifecycle events; plugin hooks live at `hooks/hooks.json` under the plugin root. Capabilities differ by harness — write hooks that work on the harnesses the plugin targets.

## 1. Preconditions — check these first, they cause most "broken hook" reports

- **On Claude Code:** plugin hooks are enabled by default — no feature flag, no per-hook trust gate. Matchers match ALL tools (Edit, Write, Read, Bash, MCP).
- **On Codex (experimental — the source of most "broken hook" reports):**
  1. Feature flag: confirm `~/.codex/config.toml` contains `[features]` with `codex_hooks = true`.
  2. Trust: plugin hooks are NOT trusted automatically on install — the user must review and trust the hook in Codex before it runs. If a hook "does nothing", check trust first.
  3. Tool events (PreToolUse/PostToolUse) are Bash-only today; hooks are disabled on Windows.

## 2. Choose the event

| Goal | Event | Tool scope & matcher (by harness) |
|---|---|---|
| Load context / conventions at start | SessionStart | matcher = `startup`/`resume` (both) |
| Block or vet a command before it runs | PreToolUse | Claude Code: any tool by matcher (Edit/Write/Read/Bash/MCP). Codex: Bash only, and the agent can route around it — guardrail, not enforcement |
| Review / annotate tool output | PostToolUse | Claude Code: any tool. Codex: Bash only; cannot undo side effects |
| Inspect or block the user prompt, add context | UserPromptSubmit | matcher ignored (both) |
| Force another pass when the agent stops | Stop | matcher ignored (both); on Codex stdout MUST be JSON |

## 3. Write the config and script

- Config shape: event → matcher group (`matcher` regex, optional) → handler list (`type: "command"`, `command`, optional `timeout` seconds [default 600], optional `statusMessage`).
- Reference scripts with the portable env var: `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/<script>.py` — never absolute or bare relative paths. Codex sets `CLAUDE_PLUGIN_ROOT` too (and also accepts `${PLUGIN_ROOT}`). `${CLAUDE_PLUGIN_DATA}` (Codex: `${PLUGIN_DATA}`) is the writable data dir; write state there, never into the plugin root.
- Script contract: read one JSON object on stdin; respond via stdout/exit code. Exit 0 with no output = success/continue. Exit 2 with reason on stderr = block (event-dependent). Full per-event input/output schemas, blocking shapes, and fail-open fields: `references/hooks-reference.md`.
- If hooks live at `hooks/hooks.json`, no manifest entry is needed; the harness finds it. Custom paths require a `hooks` field in the plugin manifest (`.claude-plugin/plugin.json` and/or `.codex-plugin/plugin.json`, `./`-prefixed).

## 4. Test before shipping

Feed each script a sample payload from `references/hooks-reference.md` and check the response:

```bash
echo '<sample payload>' | python3 hooks/<script>.py; echo "exit=$?"
```

Verify: valid JSON out where required (on Codex, always for Stop), correct blocking shape, exits fast (well under timeout), and no plain-text stdout on events that require JSON.

## 5. Repairing a hook that misbehaves

Walk the diagnostic table in `references/hooks-reference.md` (feature flag → trust → event support → matcher semantics → contract → paths → timeout). Fix the root cause; do not pile on more hooks. After any repair, rerun step 4 and report per `../plugin-audit/references/report-style.md`: verdict first, the failure mode fixed as a severity-tagged line, test command + output in a code block.
