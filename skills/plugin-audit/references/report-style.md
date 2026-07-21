# Chat report style (shared by all plugin-improver skills)

Reports are read in chat. Optimize for scannability: the verdict in the first 3 lines, detail below, nothing the reader must scroll past twice.

## Scorecard

Lead with grade + total, then a compact table with bar sparklines:

```
## Plugin health: my-plugin — 82/100 (Good)

| Dimension | Score | |
|---|---|---|
| Manifest integrity | 14/15 | █████████▌ |
| Skill quality | 20/25 | ████████░░ |
| Trigger precision | 15/20 | ███████▌░░ |
| Context economy | 18/20 | █████████░ |
| Hooks health | 7/10 | ███████░░░ |
| Distribution | 8/10 | ████████░░ |
```

Bars: 10 chars wide, `█` per 10%, `▌` for half, `░` fill. Always same width so columns align.

## Findings

One line each, severity-tagged, evidence in backticks, fix after the arrow:

```
🔴 HIGH `skills/deploy/SKILL.md:3` description claims same prompts as `release` → add NOT-clause
🟡 MED  `hooks/hooks.json` Stop hook prints plain text → emit JSON only
🟢 LOW  README missing install steps → add marketplace snippet
```

Severity: 🔴 breaks behavior, 🟡 degrades quality, 🟢 cosmetic. Sort 🔴→🟢. Cap at 8 lines; fold the rest into "…and N minor findings (ask to expand)".

## Diagnostics

A compact block placed right under the scorecard, showing the machine floor vs judgment split and the two runtime signals. Keep it to 3–4 lines:

```
🔎 Floor 71/100 auto (score.py) · +9 judged = 80/100 · needs_judgment: skill-quality, trigger-negativescope
🪙 Session tax 4.1k tok · body headroom OK · descriptions +180 tok vs baseline (tokens.py)
🩺 Runtime: 2 hook errors, 1 skill error in 14 sessions — `hooks/lint.sh` exit 1 ×2 (errscan.py)
✅ Runtime clean — no hook/tool/skill errors in scanned sessions
```

- Floor line: `auto` total from `score.py`, points you judged on top, final, and which dimensions still carried `needs_judgment` notes.
- Token line: session-tax headline, budget headroom (or the skill that blew it), and baseline delta — the evidence behind any Context economy deduction.
- Runtime line: error counts per plugin/skill and the top offending handler; when clean, collapse to the single ✅ line. This is the evidence behind any Hooks health deduction.

Show the tool name in parentheses so the number is traceable. If a script didn't run, say `floor: manual (score.py unavailable)` rather than omitting the line.

## Before/after (trigger tuning)

```
### deploy — fixed: never fired on "ship it" (S3), stole "release notes" (N2)
- Before (61 chars): `Helps with deployments.`
+ After (142 chars): `Deploy this repo to staging or production. Use when asked to deploy, ship, or roll back. Not for release notes.`
```

Always show char counts and which matrix cases the rewrite fixes.

## Improvement pass summary

End every `plugin-improve` pass with exactly this block:

```
## Pass complete: v0.1.0 → v0.1.1

📈 Score 74 → 82 (+8) · 📉 context −218 words · 🧾 ledger updated

| Change | Dimension | Δ |
|---|---|---|
| Split kitchen-sink skill into 2 | Skill quality | +4 |
| Rewrote 3 descriptions | Trigger precision | +3 |
| Moved schemas to references/ | Context economy | +1 |

Next best candidate: add SessionStart hook trust note (+2 hooks health)
```

If nothing cleared the bar: `✅ Stable at 91/100 — no change ships this pass. Churn is regression.`

## Rules

- Verdict first, always. Never open with methodology.
- Tables over prose for anything with 3+ comparable items; prose for reasoning.
- Emoji only as severity/status markers shown above — never decorative.
- Monospace (backticks) for every path, skill name, field, and command.
- Whole report under ~40 lines; deep detail goes to a saved file (`.plugin-improver/audit-<date>.md`), linked at the end.
