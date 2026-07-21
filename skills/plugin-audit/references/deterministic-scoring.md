# Deterministic scoring — the machine floor

`score.py` computes the objective slice of the 100-point rubric so the agent only judges what a script cannot. It reads the same manifests, skill frontmatter, and budgets the human rubric uses, and returns a per-dimension floor plus a list of what still needs judgment.

Run it against a plugin root (the dir holding `.claude-plugin/plugin.json` and/or `.codex-plugin/plugin.json`):

```
python3 scripts/score.py <plugin-root> --json
```

Output shape, one entry per rubric dimension:

```
{
  "manifest-integrity": {"auto": 11, "max": 15, "needs_judgment": ["description accuracy"]},
  "context-economy":    {"auto": 18, "max": 20, "needs_judgment": ["duplication across skills"]},
  ...
  "_total": {"auto": 71, "max": 100}
}
```

`auto` is the machine FLOOR: points the script is confident about. `max` is the dimension cap (unchanged from `scoring-rubric.md`). `needs_judgment` names the sub-criteria the script cannot decide — the agent scores those, on top of `auto`, up to `max`. The final dimension score is `auto` + (judged points), never below `auto`.

## What is auto-scored vs judged, per dimension

| Dimension (max) | `score.py` auto-scores | Agent judges (`needs_judgment`) |
|---|---|---|
| Manifest integrity (15) | JSON parses; kebab-case `name`; semver `version`; cross-harness `name`/`version` parity; component pointers `./`-prefixed and in-root; manifest-dir layout | `description` accuracy; whether publisher metadata suits the distribution level |
| Skill quality (25) | — (all judgment) | one-job-per-skill; imperative bodies; actionable steps; failure handling |
| Trigger precision (20) | Description char budget; NOT-clause presence heuristic; collision count from the trigger graph (`G_t`) | Whether triggers match real user phrasing; genuine vs apparent collisions; guard adequacy for risky skills |
| Context economy (20) | Description chars vs budget; body words vs budget; dead/empty files and unused dirs | Cross-skill duplication; progressive-disclosure quality (aided by `tokens.py`) |
| Hooks health (10) | `hooks.json` shape; `${CLAUDE_PLUGIN_ROOT}`/`${PLUGIN_ROOT}` paths; referenced scripts exist and are executable | Per-event contract correctness; per-harness capability limits; runtime health (from `errscan.py`) |
| Distribution readiness (10) | README sections present; changelog/ledger exists; a marketplace entry per targeted harness | Interface/presentation quality (`presentation.md`); asset craft; copy quality |

Skill quality is fully judged — nothing mechanical stands in for reading the bodies. Every other dimension has a floor.

## Mapping to the rubric

- The `auto`/`max` pairs correspond one-to-one to the six dimensions in `scoring-rubric.md`; the sub-point weights there are unchanged. `score.py` never invents points — it only fills the objective fraction of each dimension.
- Feed `tokens.py` output into the Context-economy judgment and `errscan.py` output into the Hooks-health judgment (see `scoring-rubric.md` for the evidence notes).
- Report the split explicitly (see the Diagnostics block in `report-style.md`): floor total, judged delta, final, and which dimensions carried `needs_judgment` notes.

## Gates and CI

`score.py` can also enforce a floor instead of just reporting one:

```
python3 scripts/score.py <plugin-root> --min 55            # fail if the auto total drops below 55
python3 scripts/score.py <plugin-root> --min-baseline      # fail if below the stored .plugin-improver/score-baseline.json
```

CI runs the `--min-baseline` form so a change that mechanically regresses the plugin (a blown budget, a broken pointer, a lost manifest) fails the build before any human judgment is applied. When auditing, run the plain report form first; treat a red gate as an automatic 🔴 finding.

## When the scorer is unavailable

If `score.py` is missing or errors, score every dimension by hand from `scoring-rubric.md` and note `floor: manual` in the Diagnostics block so the report stays honest about provenance. The floor is an accelerator, not a dependency — the rubric is still the source of truth.
