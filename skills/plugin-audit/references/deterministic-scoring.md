# Deterministic scoring — the machine floor

`score.py` computes the objective slice of the 100-point rubric so the agent only judges what a script cannot. It reads the same manifests, skill frontmatter, and budgets the human rubric uses, and returns a per-dimension floor, a redistributed effective total, and a list of what still needs judgment.

Run it against a plugin root (the dir holding `.claude-plugin/plugin.json` and/or `.codex-plugin/plugin.json`):

```
python3 scripts/score.py <plugin-root> --json
```

Output shape, one entry per rubric dimension plus a renormalized total and a grade:

```
{
  "dimensions": {
    "manifest_integrity": {"auto": 13.5, "max": 15, "ceiling": 15.0, "applicable": true,  "needs_judgment": [...]},
    "hooks_health":       {"auto": 0.0,  "max": 10, "ceiling": 0.0,  "applicable": false, "needs_judgment": ["no hooks present — dimension N/A, weight redistributed"]},
    ...
  },
  "grade": "Solid",
  "total": {"auto": 78.2, "max": 100, "effective": 78.2}
}
```

Per dimension:

- `auto` — machine-verifiable points earned, scored against the dimension's nominal `max`.
- `max` — the dimension's nominal rubric ceiling (unchanged: 15 / 25 / 20 / 20 / 10 / 10).
- `ceiling` — the machine-achievable slice of `max` (`auto` never exceeds it; the remainder is judgment residue the agent scores on top).
- `applicable` — whether the dimension applies to this plugin at all. A dropped dimension (`false`) is excluded from the total.
- `needs_judgment` — the sub-criteria the script cannot decide.

`total.auto` (== `total.effective`) is the **effective score out of 100**: the earned auto renormalized against the achievable auto ceiling of the *applicable* dimensions. `total.max` stays `100` so totals stay comparable across plugins. The final dimension score is `auto` + (judged points), never below `auto`.

## Calibration principles

1. **Graduated credit, no coarse pass/fail.** Every sub-point awards a gradient. Validity earns the MIDDLE of a sub-point, not its max.
2. **No free points.** A dimension never hands out a free maximum for being absent.
3. **N/A → redistribute.** A dimension that genuinely does not apply (no hooks; no skills) is DROPPED — excluded from both the numerator and the denominator of the effective total — so its weight spreads proportionally across the applicable dimensions. Renormalized to 100.
4. **Reward leanness.** Budget dimensions reward being well UNDER budget via a gradient (see Context economy).
5. **Skill quality gets machine signal.** Per-skill proxies for imperative bodies, actionable specifics, and failure handling replace the old flat `0`.

## Effective total & redistribution

Let `A` = the set of applicable dimensions (`applicable == true` and `ceiling > 0`).

```
effective = 100 * (sum of auto over A) / (sum of ceiling over A)
```

A dimension that is N/A contributes to neither sum, so the remaining dimensions absorb its weight proportionally — no free max, no dead weight. A plugin with no hooks is scored purely on the dimensions that apply to it; a plugin with no skills drops `skill_quality`, `trigger_precision`, and `context_economy` the same way.

## Grade bands (on the effective total)

| Band | Range |
|---|---|
| Exceptional | 92–100 |
| Strong | 82–91 |
| Solid | 68–81 |
| Needs work | 50–67 |
| Poor | < 50 |

A mature-but-improvable plugin lands in the Solid/Strong range (~78–84); 92+ is rare but achievable when every applicable dimension is strong.

## Auto formulas, per dimension

| Dimension (max / auto ceiling) | `score.py` auto-scores | Agent judges (`needs_judgment`) |
|---|---|---|
| Manifest integrity (15 / 15) | validity graduated — kebab `name` (2) + semver `version` (1.5) + `description` present (0.5); cross-harness parity — identical `name` (2) + agreeing `version` (2), single-harness earns full 4; component pointers `./`-prefixed & resolvable (proportional, 3); manifest-dir layout clean (proportional, 2); `author` present (2) | `description` accuracy; publisher-metadata appropriateness |
| Skill quality (25 / 18) | per-skill proxies averaged — imperative body (≤8: verb-first line density vs a 35% target, numbered/step markers, verb-first heading); actionable specifics (≤5: code fences, inline `` `code` ``, file paths); failure handling (≤5: `missing`/`fails`/`fallback`/`error`/`ambiguous`/`absent`/… signals, 3+ distinct → full) | one-job-per-skill; genuine instruction depth (~7pt residue) |
| Trigger precision (20 / 13) | description ≤400 chars AND carries a when/trigger signal or quoted phrase (proportional, 3); redirecting NOT-clause — `"instead of"` / `"rather than"` / `"not for X … use Y"` / `"use Y instead"`, a bare `not` earns nothing (proportional, 5); no collisions — `clamp(5 − collision_count, 0, 5)` | what+when completeness & trigger-phrase quality; risky-skill guarding |
| Context economy (20 / 14) | body utilization gradient (≤600-word budget: full at ≤50%, linear decay to 0 at ≥100%, averaged, 8); description utilization gradient (≤400-char budget, same shape, 4); no dead/empty files or empty ref dirs (2) | cross-skill duplication (6); progressive-disclosure quality |
| Hooks health (10 / 5) | **N/A → dropped when no `hooks/hooks.json`** (no free 10); when present: valid shape event→matcher→handlers (3), paths use `${CLAUDE_PLUGIN_ROOT}`/`${PLUGIN_ROOT}` (2) | per-event contract correctness; per-harness capability limits; runtime health |
| Distribution readiness (10 / 8) | README signals present — `install` + `skill` + a heading (proportional, 3); changelog/ledger exists (3); Claude `marketplace.json` lists the plugin (2) | README completeness; version-bump discipline; Codex registration (user-global, unverifiable, 2) |

The **budget gradient** (`budget_fraction`) is the leanness reward: `clamp(2 * (1 − used/budget), 0, 1)` — full credit at ≤50% of budget, 0 at ≥100%. A 599/600-word body scores far below a 300-word one.

## Mapping to the rubric

- The `auto`/`max` pairs correspond one-to-one to the six dimensions in `scoring-rubric.md`; the nominal maxes are unchanged. `score.py` never invents points — it only fills the objective fraction of each dimension, capped at `ceiling`.
- Feed `tokens.py` output into the Context-economy judgment and `errscan.py` output into the Hooks-health judgment (see `scoring-rubric.md` for the evidence notes).
- Report the split explicitly (see the Diagnostics block in `report-style.md`): effective total, grade, which dimensions were dropped as N/A, and which carried `needs_judgment` notes.

## Gates and CI

`score.py` can also enforce a floor instead of just reporting one:

```
python3 scripts/score.py <plugin-root> --min 55                     # fail if the effective total drops below 55
python3 scripts/score.py <plugin-root> --min-baseline PATH          # fail if below the stored baseline JSON
```

Both gates read `total.auto` (the effective /100 score). CI runs a floor form so a change that mechanically regresses the plugin (a blown budget, a broken pointer, a lost manifest) fails the build before any human judgment is applied. When auditing, run the plain report form first; treat a red gate as an automatic 🔴 finding.

## When the scorer is unavailable

If `score.py` is missing or errors, score every dimension by hand from `scoring-rubric.md` and note `floor: manual` in the Diagnostics block so the report stays honest about provenance. The floor is an accelerator, not a dependency — the rubric is still the source of truth.

## Selftest

```
python3 scripts/score.py selftest
```

Runs deterministic temp-dir fixtures spanning poor / fair / solid / excellent and asserts band membership of their effective totals, monotonic ordering, and the de-saturation invariants: (a) hooks is dropped (not auto-max) when absent and graduated when present; (b) `skill_quality` auto is > 0 for a good plugin; (c) context scores strictly higher for a lean body than a near-budget one; (d) a demanding-but-not-impossible fixture reaches 92+. Stdlib-only, no network, no fixtures on disk.
