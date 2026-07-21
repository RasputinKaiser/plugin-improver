# Codex hooks reference

Source of truth: https://developers.openai.com/codex/hooks and generated schemas at github.com/openai/codex → codex-rs/hooks/schema/generated. Hooks are experimental; re-verify against the docs when something contradicts this file.

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
            "command": "python3 ${PLUGIN_ROOT}/hooks/session_start.py",
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

`session_id`, `transcript_path` (nullable), `cwd`, `hook_event_name`, `model`. Turn-scoped events add `turn_id`.

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

### PreToolUse (Bash only today)
- matcher filters `tool_name` — currently always `Bash`. `Edit|Write` matchers match nothing today.
- Extra input: `turn_id`, `tool_name`, `tool_use_id`, `tool_input.command`.
- Plain stdout ignored. Block with:
  ```json
  { "hookSpecificOutput": { "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "why" } }
  ```
  or legacy `{ "decision": "block", "reason": "why" }`, or exit 2 + reason on stderr.
- `permissionDecision: "allow"/"ask"`, `updatedInput`, `additionalContext`, `continue:false` are parsed but NOT supported — they fail open. Never rely on them for enforcement.
- The model can write a script to disk and run it — treat PreToolUse as a guardrail, not a boundary.

### PostToolUse (Bash only today)
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

| Symptom | Likely cause | Fix |
|---|---|---|
| Never runs at all | `codex_hooks` flag off; hook not trusted; Windows | Enable flag; trust hook in Codex; use macOS/Linux |
| Never runs for Edit/Write/MCP | Tool events only emit Bash today | Re-scope to Bash or a different event |
| Runs but has no effect | Plain text on an event that ignores it; fail-open field (`allow`, `ask`, `updatedInput`) | Use the documented blocking shape for that event |
| Stop hook errors | Plain-text stdout | Emit JSON only |
| Works in one repo, not another | Bare relative path resolved from session cwd | Use `${PLUGIN_ROOT}` (plugins) or git-root resolution (repo hooks) |
| Runs forever / hangs turn | Script waits on input or network; 600 s default timeout | Set a small `timeout`; make script non-interactive |
| Infinite continuation loop | Stop hook ignores `stop_hook_active` | Exit 0 with `{}` when `stop_hook_active` is true |
| Writes fail after install | Writing into `PLUGIN_ROOT` (read-only install cache) | Write to `PLUGIN_DATA` |

## Environment

Plugin hook commands receive `PLUGIN_ROOT` (installed plugin root, treat read-only) and `PLUGIN_DATA` (writable data dir). `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA` are set for compatibility.
