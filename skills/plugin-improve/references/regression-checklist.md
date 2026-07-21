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

## Measured gates (run in order; each must pass before the pass ships)

These are the numeric non-regression gates. They compare against the baselines captured in step 1 (`.plugin-improver/score-baseline.json`, the token baseline, and — if a routing set exists — `.plugin-improver/route-baseline.json`). If a script is absent (stripped install), fall back to the qualitative checks below and say the measured gate was unavailable.

1. [ ] **Validator green.** A red validator blocks the pass:

    ```
    python3 scripts/validate.py
    ```

2. [ ] **Deterministic score did not drop.** Exit 1 = regression → revert the offending change:

    ```
    python3 scripts/score.py <plugin> --min-baseline .plugin-improver/score-baseline.json
    ```

3. [ ] **Token / session-tax budget held.** Net metadata growth ≤ 10% vs the saved baseline; trigger tokens under the cap:

    ```
    python3 scripts/tokens.py <plugin> --max-trigger-tokens N
    ```

4. [ ] **No NEW runtime errors.** Compare against the step-1 error signal; a newly introduced error blocks the pass:

    ```
    python3 scripts/errscan.py --plugin <plugin>
    ```

5. [ ] **Routing accuracy ≥ baseline** — only when trigger descriptions changed. Exit 1 = accuracy regressed → revert the trigger edit:

    ```
    python3 scripts/route_eval.py --min-baseline .plugin-improver/route-baseline.json
    ```

Any red gate → revert only the offending change (see Revert rule), re-run the gate, then continue the pass.

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
- [ ] `.plugin-improver/baseline.json` overwritten with the new state, and the numeric baselines refreshed for the next pass:

    ```
    python3 scripts/score.py <plugin>  > .plugin-improver/score-baseline.json
    python3 scripts/tokens.py <plugin> --save-baseline
    ```

## Revert rule

If any item fails and the fix isn't obvious within one attempt, revert that single change, note it in the ledger under "attempted, reverted", and continue with the rest of the pass. A smaller shipped improvement beats a big reverted one.
