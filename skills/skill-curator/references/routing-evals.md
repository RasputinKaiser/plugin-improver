# Routing evals + plugin-eval integration

Loaded on demand from SKILL.md. Lexical collisions are hypotheses; confusion is
measured by routing probes.

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
