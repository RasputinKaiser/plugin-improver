---
name: plugin-improve
description: Run a disciplined improvement pass on an existing plugin (Claude Code and/or Codex) - audit, apply the highest-leverage fixes, verify nothing regressed, and keep context cost flat. Use when asked to improve, polish, upgrade, evolve, iterate on, or "make better" a plugin, including recurring maintenance passes. Not for first-time plugin creation (use plugin-scaffold) or one-off hook fixes.
---

Improve the target plugin in one bounded, verifiable pass. The contract: every pass leaves the plugin measurably better, never behaviorally worse, and never heavier in context than it needs to be.

## The loop

### 1. Baseline

Load `<plugin-root>/.plugin-improver/baseline.json` and `LEDGER.md` if they exist. If not, run the `plugin-audit` procedure (its rubric is at `../plugin-audit/references/scoring-rubric.md`) and save the baseline first. If the rubric file is missing (stripped install), score the six dimensions from the plugin-audit skill body — manifest 15, skills 25, triggers 20, context 20, hooks 10, distribution 10 — and say the detailed rubric was unavailable. No changes before a baseline exists. Treat inherited findings as hypotheses: re-verify each against current evidence before acting, and withdraw mistaken ones in the ledger — never "fix" what a stale finding merely claims is wrong.

### 2. Select — at most 3 improvements per pass

From audit findings, pick by leverage (score points gained ÷ effort), tie-broken toward fixes that REDUCE context cost. Check `LEDGER.md`: never re-apply something a past pass did or deliberately reverted. If nothing clears the bar — meaning no change gains points without costing context or risking behavior — report the plugin as stable and stop. Churn is regression.

### 3. Apply — smallest diff that fixes the finding

Hard rules while editing:

- Never rename the plugin or any skill `name` — they are identifiers users and configs depend on.
- Never delete user-authored content without explicit confirmation; move it to `references/` instead of destroying it.
- Trigger work → follow `plugin-tune-triggers`; hook work → follow `plugin-hooks`; install-surface polish (displayName, brandColor, icons, starter prompts, per-skill openai.yaml) → follow `../plugin-audit/references/presentation.md`.
- Context budget: net metadata (all descriptions) and net SKILL.md body words must not grow more than 10% in a pass. Pay for additions with removals or by pushing detail into `references/`.

### 4. Verify — the non-regression gate

Work through `references/regression-checklist.md` completely (if missing: verify identity unchanged, manifests parse, frontmatter valid, context budgets held — never skip verification silently). If the plugin ships `scripts/validate.py`, run it (`python3 scripts/validate.py`) — a red validator blocks the pass. Then re-score with the audit rubric. Ship only if: new total ≥ baseline total, no dimension dropped more than 2 points, and the context budget held. Any failure → revert the offending change, not the whole pass.

### 5. Record

- Bump `version` in EVERY plugin manifest together — `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` (whichever exist) plus any marketplace entry — keeping them in agreement (ignore any Codex `+build` suffix). Drift between manifests is itself a regression. patch for fixes/wording, minor for new capability, major for anything breaking (renames, removed skills, changed hook behavior). If the plugin has a build/sync script, run it. To package and publish the bumped plugin, hand off to `plugin-release`.
- Append to `<plugin-root>/LEDGER.md`: date, version, changes with rationale, score before → after, context delta in words, anything deliberately NOT done and why.
- Overwrite `.plugin-improver/baseline.json` with the new state.
- Remind the user to refresh the install so changes take effect: restart the harness or refresh the local marketplace install (`~/.claude/plugins/` or `~/.codex/plugins/`).

## Report format

End with the "Pass complete" block defined in `../plugin-audit/references/report-style.md`: version bump, score before → after, context delta, per-change table, and the single highest-value candidate for the next pass.
