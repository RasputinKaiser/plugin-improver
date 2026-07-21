# Hooks reference (Claude Code + Codex)

The config shape and per-event contracts below are the **Codex** schema (source of truth: https://developers.openai.com/codex/hooks and generated schemas at github.com/openai/codex → codex-rs/hooks/schema/generated; experimental — re-verify against the docs). Claude Code shares the same `hooks.json` structure and event names; the compact section next records where it diverges.

## Claude Code differences (compact)

- **Enablement:** on by default — no `[features] codex_hooks` flag, no per-hook trust gate, not Windows-restricted.
- **Tool scope:** PreToolUse/PostToolUse matchers match ALL tools (Edit, Write, Read, Bash, MCP…), not just Bash. A `matcher` like `Edit|Write` works.
- **Env vars:** `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}` (Codex sets these too, and also accepts `${PLUGIN_ROOT}`/`${PLUGIN_DATA}`).
- **Events & blocking:** same event names and `{ "decision": "block", "reason": … }` / exit-2 blocking semantics; consult Claude Code's own docs for fields it supports beyond this Codex schema (e.g. PreToolUse `permissionDecision` is honored). Where a plugin targets both, write to the intersection: Bash-scoped tool hooks, JSON output, `${CLAUDE_PLUGIN_ROOT}` paths.

## Config shape

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py",
            "statusMessage": "Loading context",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- `timeout` in seconds (`timeoutSec` accepted); default 600.
- All matching hooks from all files run; same-event command hooks launch concurrently — one hook cannot block another from starting.
- Commands run with the session cwd as working directory.

## Common stdin fields (every event)

`session_id`, `transcript_path` (nullable), `cwd`, `hook_event_name`, `model`. Turn-scoped events add `turn_id`. (Claude Code: `model` is not guaranteed on every event — read it only where documented, e.g. SessionStart.)

## Common output fields (SessionStart, UserPromptSubmit, Stop)

```json
{ "continue": true, "stopReason": "optional", "systemMessage": "optional", "suppressOutput": false }
```

`continue: false` marks the run stopped; `systemMessage` surfaces a warning in the UI; `suppressOutput` is parsed but not implemented yet.

## Per-event contracts

### SessionStart
- matcher filters `source`: `startup` | `resume`.
- Extra input: `source`.
- Plain text on stdout → added as developer context. Or JSON with `hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: "..." }`.

### PreToolUse (Codex: Bash only today; Claude Code: all tools)
- matcher filters `tool_name` — on Codex currently always `Bash`, so `Edit|Write` matchers match nothing today; on Claude Code `Edit|Write|Read|Bash|<MCP>` all match.
- Extra input: `turn_id`, `tool_name`, `tool_use_id`, `tool_input.command`.
- Plain stdout ignored. Block with:
  ```json
  { "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "why" } }
  ```
  or legacy `{ "decision": "block", "reason": "why" }`, or exit 2 + reason on stderr.
- `permissionDecision: "allow"/"ask"`, `updatedInput`, `additionalContext`, `continue:false` are parsed but NOT supported — they fail open. Never rely on them for enforcement.
- The model can write a script to disk and run it — treat PreToolUse as a guardrail, not a boundary.

### PostToolUse (Codex: Bash only today; Claude Code: all tools)
- Extra input: `turn_id`, `tool_name`, `tool_use_id`, `tool_input.command`, `tool_response`.
- Plain stdout ignored. `{ "decision": "block", "reason": "..." }` does not undo the command; Codex replaces the tool result with your feedback and continues from it. `hookSpecificOutput.additionalContext` adds developer context. `continue: false` stops normal processing of the original result. Exit 2 + stderr also works.

### UserPromptSubmit
- matcher ignored. Extra input: `turn_id`, `prompt`.
- Plain stdout → developer context, or `hookSpecificOutput.additionalContext`. Block with `{ "decision": "block", "reason": "..." }` or exit 2 + stderr.

### Stop
- matcher ignored. Extra input: `turn_id`, `stop_hook_active`, `last_assistant_message` (nullable).
- stdout MUST be JSON on exit 0 — plain text is invalid for this event.
- `{ "decision": "block", "reason": "..." }` = keep going: Codex creates a continuation prompt from `reason`. Exit 2 + stderr does the same. Any matching Stop hook returning `continue: false` wins over continuation.
- Always check `stop_hook_active` to avoid infinite continuation loops.

## Sample payloads for local testing

```bash
# SessionStart
echo '{"session_id":"t","transcript_path":null,"cwd":".","hook_event_name":"SessionStart","model":"gpt-5","source":"startup"}' | python3 hooks/session_start.py

# PreToolUse
echo '{"session_id":"t","cwd":".","hook_event_name":"PreToolUse","model":"gpt-5","turn_id":"1","tool_name":"Bash","tool_use_id":"x","tool_input":{"command":"rm -rf /"}}' | python3 hooks/pre_tool_use.py

# Stop
echo '{"session_id":"t","cwd":".","hook_event_name":"Stop","model":"gpt-5","turn_id":"1","stop_hook_active":false,"last_assistant_message":"done"}' | python3 hooks/stop.py
```

## Diagnostic table — "my hook doesn't work"

| Symptom | Harness | Likely cause | Fix |
|---|---|---|---|
| Never runs at all | Codex | `codex_hooks` flag off; hook not trusted; Windows | Enable flag; trust hook in Codex; use macOS/Linux |
| Never runs at all | Claude Code | `hooks.json` not found / bad JSON; plugin not installed | Fix path/JSON; reinstall the plugin |
| Never runs for Edit/Write/MCP | Codex | Tool events only emit Bash today | Re-scope to Bash or a different event |
| Never runs for Edit/Write/MCP | Claude Code | matcher regex doesn't match the tool name | Fix the `matcher` (e.g. `Edit|Write`) |
| Runs but has no effect | both | Plain text on an event that ignores it; fail-open field (`allow`, `ask`, `updatedInput`) | Use the documented blocking shape for that event |
| Stop hook errors | Codex | Plain-text stdout | Emit JSON only |
| Works in one repo, not another | both | Bare relative path resolved from session cwd | Use `${CLAUDE_PLUGIN_ROOT}` (plugins) or git-root resolution (repo hooks) |
| Runs forever / hangs turn | both | Script waits on input or network; 600 s default timeout | Set a small `timeout`; make script non-interactive |
| Infinite continuation loop | both | Stop hook ignores `stop_hook_active` | Exit 0 with `{}` when `stop_hook_active` is true |
| Writes fail after install | both | Writing into the plugin root (read-only install cache) | Write to `${CLAUDE_PLUGIN_DATA}` |

## Environment

Plugin hook commands receive `CLAUDE_PLUGIN_ROOT` (installed plugin root, treat read-only) and `CLAUDE_PLUGIN_DATA` (writable data dir) on both harnesses. Codex additionally sets `PLUGIN_ROOT`/`PLUGIN_DATA` as aliases; prefer the `CLAUDE_*` names for portability.
