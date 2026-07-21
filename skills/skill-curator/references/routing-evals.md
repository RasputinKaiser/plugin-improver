# Routing evals + plugin-eval integration

Loaded on demand from SKILL.md. Lexical collisions are hypotheses; confusion is
measured by routing probes.

## Routing graph (`curator.py graph`)

`python3 scripts/curator.py graph [--md OUT] [--mermaid|--dot] [--json] [roots…]`
builds two stdlib-only graphs over the same skill records and reports on them
(`report` folds a compact summary of the same data into its output):

- **G_t** — undirected weighted trigger-collision graph. An edge is drawn only
  on a genuine collision (shared quoted phrase, ≥3 distinctive shared terms plus
  a shared bigram, ≥6 distinctive terms, or a near-duplicate); the weight blends
  shared phrases + description-token Jaccard + shared distinctive nouns, and each
  edge records WHY. `connected_components` gives **collision clusters** (fingerprints
  use the same `coll-` scheme as `report`, so `decide`/`archive` keep working and
  ledger-rejected clusters stay hidden). **Trigger-hogs** rank by betweenness
  (Brandes) + degree — the skills bridging the most topic groups are the
  highest-value descriptions to sharpen. The **minimal-edit set**
  (`greedy_min_vertex_cover`) names the K descriptions whose edits remove every
  collision edge.
- **G_r** — directed reference/handoff graph. Edge a→b when a's description or
  SKILL.md body references b by name (distinctive names only) or by a relative
  path resolving into b's dir (fenced code stripped, like validate.py). Surfaces
  **orphans** (no handoff in or out), **broken handoffs** (referenced file
  missing — same signal as validate.py's reference check), and **cycles** (DFS).

`--mermaid`/`--dot` emit a text graph of G_t viewable with no dependency; `--all`
includes ledger-hidden clusters.

## Routing probes (behavioral, not just lexical)

1. `python3 scripts/curator.py probes --only <member> --only <member> --out-dir /tmp/probes`
   → `probes.json` (probes lifted from quoted trigger phrases), `routing-sheet.md`,
   `benchmark-scenarios.json`. It lists skills that need hand-authored probes.
2. Author 2–3 paraphrase and near-miss probes per skill and append them to probes.json —
   verbatim phrases alone overstate accuracy.
3. Route every probe using ONLY routing-sheet.md — yourself, or delegate to codex for an
   independent second opinion — writing JSONL `{"probe_id": ..., "selected": ...}`.
4. `python3 scripts/curator.py probes-grade --probes ... --results ...` → confusion
   matrix, saved so the next report includes it. Re-run after description fixes to prove
   the fix moved the number.

For measured real-model runs, seed plugin-eval's harness: `plugin-eval init-benchmark`,
then paste entries from benchmark-scenarios.json into `.plugin-eval/benchmark.json`.

## Driving it end-to-end: `route_eval.py`

The four manual steps above are the reference pipeline; `route_eval.py` is the driver that
operationalizes them as one measured, repeatable loop, wrapping the same `curator.py graph`
/ `probes` / `probes-grade` stages so a description change is gated on an accuracy *number*
rather than a lexical hypothesis:

```
python3 scripts/route_eval.py                   # full loop: generate → route → grade
python3 scripts/route_eval.py --min-baseline    # gate a change on measured accuracy (CI)
```

1. **Near-miss generation from `G_t`.** It lifts should-trigger probes from each skill's
   quoted trigger phrases and synthesizes 2–3 paraphrase + near-miss probes per skill,
   **prioritized by `G_t`'s confusable pairs** — it probes the collisions the graph found
   rather than random pairs (this is the Phase 1 → Phase 4 dependency). Author-supplied
   probes appended to `probes.json` are honored, same as the manual flow.
2. **Routing.** Presents ONLY the description set (the router's real input) plus one probe
   to a harness-native router — on Codex `gpt-5.6-luna` at `model_reasoning_effort=high`
   (batch to limit session-file pollution), on Claude Code an Opus subagent — with a manual
   fallback when no model is available. This mirrors routing every probe against
   routing-sheet.md.
3. **Confusion matrix.** Grades the routed picks exactly as `curator.py probes-grade` does
   — per-skill precision/recall plus overall accuracy — and persists the run to
   `.plugin-improver/routing-<date>.json` so trajectories are visible across passes.
4. **Accuracy gate.** `--min-baseline` compares the run against the stored baseline (or a
   `--min N` floor) and exits nonzero on regression, so `plugin-tune-triggers` and
   `plugin-improve` carry a *measured* non-regression gate — the number now moves, or the
   change is rejected. Re-run after a description fix to prove the fix raised accuracy.

Use the manual `probes` / `probes-grade` steps when you want to route by hand or delegate
to a second model for an independent opinion; `route_eval.py` is the automated driver over
the same artifacts.

## plugin-eval integration

One-time: `python3 scripts/curator.py emit-metric-pack --dir ~/.codex/curator-metric-pack`.
Then every `plugin-eval analyze <skill-or-plugin> --metric-pack
~/.codex/curator-metric-pack/manifest.json` merges inventory-wide findings (duplicate
surfaces, collision clusters, trigger-token bands) into that single-target evaluation.
The CLI ships in the plugin-eval@openai-curated plugin; outside Codex sessions call it as
`node ~/.codex/plugins/cache/openai-curated/plugin-eval/*/scripts/plugin-eval.js`.
