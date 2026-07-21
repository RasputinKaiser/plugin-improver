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

## plugin-eval integration

One-time: `python3 scripts/curator.py emit-metric-pack --dir ~/.codex/curator-metric-pack`.
Then every `plugin-eval analyze <skill-or-plugin> --metric-pack
~/.codex/curator-metric-pack/manifest.json` merges inventory-wide findings (duplicate
surfaces, collision clusters, trigger-token bands) into that single-target evaluation.
The CLI ships in the plugin-eval@openai-curated plugin; outside Codex sessions call it as
`node ~/.codex/plugins/cache/openai-curated/plugin-eval/*/scripts/plugin-eval.js`.
