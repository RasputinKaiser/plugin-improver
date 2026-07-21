---
name: plugin-hooks
description: Add, repair, or review lifecycle hooks in a Codex plugin (hooks/hooks.json). Use when asked to run something on session start, guard or review Bash commands, inject context on user prompts, keep the agent going on stop, or when a hook is silently not firing, blocked, or stuck in trust review. Not for MCP servers or skill authoring.
---

Add or repair lifecycle hooks in the target plugin. Hooks are deterministic scripts Codex runs at lifecycle events; plugin hooks live at `hooks/hooks.json` under the plugin root.

## 1. Preconditions — check these first, they cause most "broken hook" reports

1. Hooks are experimental and feature-flagged. Confirm `~/.codex/config.toml` contains:

   ```toml
   [features]
   codex_hooks = true
   ```

2. Plugin hooks are NOT trusted automatically on install. The user must review and trust the hook definition in Codex before it runs. If a hook "does nothing", check trust state first.
3. Hooks are currently disabled on Windows.

## 2. Choose the event

| Goal | Event | Key limitation today |
|---|---|---|
| Load context / conventions at start | SessionStart | matcher = `startup` or `resume` |
| Block or vet a shell command before it runs | PreToolUse | only intercepts Bash; agent can route around it — guardrail, not enforcement |
| Review / annotate command output | PostToolUse | only Bash; cannot undo side effects |
| Inspect or block the user prompt, add context | UserPromptSubmit | matcher ignored |
| Force another pass when the agent stops | Stop | matcher ignored; stdout MUST be JSON |

## 3. Write the config and script

- Config shape: event → matcher group (`matcher` regex, optional) → handler list (`type: "command"`, `command`, optional `timeout` seconds [default 600], optional `statusMessage`).
- Always reference scripts as `python3 ${PLUGIN_ROOT}/hooks/<script>.py` — never absolute or bare relative paths. `PLUGIN_DATA` points to the plugin's writable data dir; write state there, never into `PLUGIN_ROOT`.
- Script contract: read one JSON object on stdin; respond via stdout/exit code. Exit 0 with no output = success/continue. Exit 2 with reason on stderr = block (event-dependent). Full per-event input/output schemas, blocking shapes, and fail-open fields: `references/hooks-reference.md`.
- If hooks live at `hooks/hooks.json`, no manifest entry is needed; Codex finds it. Custom paths require a `hooks` field in `.codex-plugin/plugin.json` (`./`-prefixed).

## 4. Test before shipping

Feed each script a sample payload from `references/hooks-reference.md` and check the response:

```bash
echo '<sample payload>' | python3 hooks/<script>.py; echo "exit=$?"
```

Verify: valid JSON out where required (always for Stop), correct blocking shape, exits fast (well under timeout), and no plain-text stdout on events that require JSON.

## 5. Repairing a hook that misbehaves

Walk the diagnostic table in `references/hooks-reference.md` (feature flag → trust → event support → matcher semantics → contract → paths → timeout). Fix the root cause; do not pile on more hooks. After any repair, rerun step 4 and report per `../plugin-audit/references/report-style.md`: verdict first, the failure mode fixed as a severity-tagged line, test command + output in a code block.
