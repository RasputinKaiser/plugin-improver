# Non-regression checklist

Run every item after applying changes, before re-scoring. An unchecked item blocks the pass.

## Identity and compatibility

- [ ] Plugin `name` unchanged.
- [ ] Every skill `name` unchanged and still matches its directory name.
- [ ] No skill directory removed (unless the user explicitly approved removal).
- [ ] Hook event names and blocking semantics unchanged unless the change WAS the hooks.

## Mechanics

- [ ] Every plugin manifest present (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`) parses; `version` bumped, still semver, and agreeing across all manifests (ignore any Codex `+build` suffix).
- [ ] All manifest paths still `./`-prefixed, resolve, and stay inside the plugin root.
- [ ] Every `SKILL.md` still has valid frontmatter with `name` and `description`.
- [ ] `hooks.json` and `.mcp.json` (if present) still parse; hook scripts exist at their referenced paths and pass a sample-payload test.
- [ ] If the plugin ships tests, a build script, or `scripts/validate.py`, RUN them (`python3 scripts/validate.py`, pytest, build.sh). A "verified"/"green" claim in `state.yaml`, `LEDGER.md`, or a prior baseline is not evidence — a red suite hid behind a green state claim (2026-07-13).
- [ ] Verify artifact CONTENT, not exit banners: a copy step that "succeeded" shipped an unmodified file when a permissions error was swallowed mid-pipeline (2026-07-13).

## Behavior

- [ ] Trigger test matrix (`.plugin-improver/trigger-matrix.md`, if present) still passes: all should-trigger prompts select the right skill, all near-miss prompts do not.
- [ ] No description was made vaguer to save characters — precision outranks brevity; brevity outranks decoration.
- [ ] Instructions that an agent previously relied on were moved (to `references/`), not deleted.
- [ ] No new step contradicts an existing step in the same or a sibling skill.

## Context economy

- [ ] Sum of all `description` chars: within 10% of baseline (or lower).
- [ ] Sum of all SKILL.md body words: within 10% of baseline (or lower).
- [ ] No reference content inlined into a body; no body content duplicated across skills.
- [ ] Nothing added "for completeness" — every added sentence changes agent behavior.

## Bookkeeping

- [ ] Re-scored with the audit rubric: total ≥ baseline, no dimension down > 2 points.
- [ ] `LEDGER.md` entry appended (date, version, changes, scores, context delta, deliberate omissions).
- [ ] `.plugin-improver/baseline.json` overwritten with the new state.

## Revert rule

If any item fails and the fix isn't obvious within one attempt, revert that single change, note it in the ledger under "attempted, reverted", and continue with the rest of the pass. A smaller shipped improvement beats a big reverted one.
