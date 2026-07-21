# plugin-improver 2.0 — measurement & graph roadmap (design + worker contract)

Status: **all four phases delivered.** Four capabilities forming a dependency DAG
(`Phase 1 → {2,3} → 4`), each independently shippable with its own version bump +
LEDGER entry. Everything is stdlib-only except Phase 4's injected model call.
Conventions and hard constraints from `docs/DESIGN.md` still apply (identity =
RasputinKaiser only; never rename existing skills; context discipline).

Delivery map (which script delivers which phase):

| Phase | Delivered by | Status |
|---|---|---|
| Phase 1 — Graph core | `curator.py graph` (+ `report` fold-in) | DELIVERED (v1.2.0) |
| Phase 2 — Deterministic scoring + CI gate | `scripts/score.py` (`--min-baseline`) | DELIVERED |
| Phase 3 — Portfolio | `scripts/portfolio.py` | DELIVERED |
| Phase 3 — `plugin-migrate` (8th skill) | — | **NOT built** — out of scope (this batch is diagnostics/evaluation, not migration); still a future item |
| Phase 4 — Empirical routing loop | `scripts/route_eval.py` (`--min-baseline`) | DELIVERED |

Two further diagnostic scripts ship alongside the phase work, beyond the original DAG:
`scripts/tokens.py` (deep per-plugin token / context-budget report — session tax, headroom,
baseline delta) and `scripts/errscan.py` (runtime error/health mining from Claude Code +
Codex session logs, per plugin/skill). `skill-curator`'s "Companion diagnostics" section
documents how all five compose with the inventory-wide curator.

## Shared analysis core (in `skills/skill-curator/scripts/curator.py`)

curator.py already enumerates skills, descriptions, quoted trigger phrases, plugin
sources/caches, and usage. Extend it with two graph builders (no new deps):

- **Trigger-collision graph `G_t`** — undirected, weighted. Nodes = skills (across all
  scanned roots). Edge weight `w(a,b)` = α·(shared identical quoted trigger phrases) +
  β·(Jaccard over description content tokens, stopwords removed) + γ·(shared coverage
  nouns). Create an edge when `w ≥ threshold`. Each edge stores its *reason* (which
  phrases/tokens caused it) for explainable reports.
- **Reference/handoff graph `G_r`** — directed. Edge `a→b` when skill a's body or
  description references skill b (by `name`, or by a relative path resolving into b's
  dir). Built from the same link extraction `validate.py check_reference_integrity` uses,
  mapped from file path → owning skill.

Add graph algorithms as small pure functions with selftest cases (deterministic):
`connected_components`, `degree_centrality`, `betweenness_centrality` (Brandes),
`greedy_min_vertex_cover`, `find_cycles` (DFS), `in_degree`.

## Phase 1 — Graph core — DELIVERED (`curator.py graph`, v1.2.0)

New subcommand `python3 curator.py graph [--md OUT] [--dot|--mermaid] [roots…]` and
fold a "Routing graph" section into the main `report`:

- **Collision clusters** from `connected_components(G_t)`, each edge annotated with why.
  Replaces today's heuristic clustering; keep the same finding fingerprints so the
  decision ledger continues to work.
- **Trigger-hog ranking** from betweenness + degree centrality — "skill X sits between N
  topic groups / shares triggers with M siblings" → the highest-value description to fix.
- **Minimal-edit set** from `greedy_min_vertex_cover(G_t)` — "editing these K descriptions
  removes E of the total collision edges."
- **Reference-graph findings**: orphan skills (`in_degree 0` and not an entry point),
  broken handoffs (reference target skill/file missing — ties to validate.py), cycles.
- **Export**: text Mermaid/DOT of `G_t` (and optionally `G_r`) so the graph is viewable
  with no dependency.

Selftest: add graph-algorithm cases to `curator.py selftest` (must stay green).

## Phase 2 — Deterministic scoring + CI gate — DELIVERED (`scripts/score.py`)

New `scripts/score.py` (stdlib; may import shared helpers from validate.py) or a
`validate.py --score` mode. Computes a **machine sub-score** for the objective parts of
the 100-pt rubric, emitting `{dimension: {auto: N, max: M, needs_judgment: [notes]}}`:

- Manifest integrity: parse, agree, kebab `name`, semver, `./`-prefixed in-root paths.
- Context economy: description chars vs budget, body words vs budget, dead files.
- Trigger precision (mechanical part): char budgets, NOT-clause presence heuristic, and
  **collision count from `G_t`** (this is why Phase 2 depends on Phase 1).
- Hooks health: hooks.json shape/paths present and well-formed.
- Distribution: README sections present, changelog/ledger exists, a marketplace entry per
  targeted harness.

`plugin-audit` and `plugin-improve` consume this as the deterministic floor; the agent
only scores the judgment dimensions on top → less cross-pass variance.

**CI gate**: `.github/workflows/ci.yml` runs `score.py --min-baseline` (compares against a
stored `.plugin-improver/score-baseline.json`, or a `--min N` floor) and fails the build
on regression. `plugin-scaffold` seeds new plugins with the same gate.

## Phase 3 — Portfolio + migration — portfolio DELIVERED (`scripts/portfolio.py`); `plugin-migrate` NOT built

- **Portfolio sweep** — **DELIVERED as `scripts/portfolio.py`** (a standalone sibling of
  `score.py`, not a `curator.py` subcommand). Runs `score.py` across every discovered
  plugin source (curator enumerates them; never score read-only caches) → ranked "fix
  first" leaderboard = low auto-score × high usage. Persists per-plugin score history so
  trajectories (slow rot) are visible; the report shows the delta since last sweep.
- **`plugin-migrate` (NEW 8th skill)** — **NOT built in this batch.** Intentionally out of
  scope: this batch is diagnostics/evaluation, not migration. It remains a future item —
  do not treat it as shipped; the plugin still has seven skills. Design, unchanged, for
  whoever builds it: a dedicated skill for single→dual-harness
  conversion. Detects a plugin shipping only `.codex-plugin/` or only `.claude-plugin/`,
  then generates the missing manifest, plus the missing per-harness surface (`commands/`
  for Claude Code, `agents/openai.yaml` for Codex), reusing `plugin-scaffold`'s
  `references/layout.md` templates. Keeps versions agreeing. Description must be tightly
  scoped with NOT-clauses vs plugin-scaffold (creates NEW) and plugin-improve (improves an
  already-dual plugin). Ships `agents/openai.yaml`, a `commands/plugin-migrate.md`, a
  `docs/skills/plugin-migrate.md` page, and updates: `EXPECTED_SKILLS` in validate.py,
  the README seven→eight-skill table, CHANGELOG/LEDGER.

## Phase 4 — Empirical routing loop — DELIVERED (`scripts/route_eval.py`; opt-in, only phase with a model dependency)

Makes trigger precision *measured*. Delivered as `scripts/route_eval.py`, the driver that
wraps curator's `probes`/`probes-grade` scaffolding (documented in
`skills/skill-curator/references/routing-evals.md`):

1. **Probe generation** — should-trigger probes lifted from each skill's quoted trigger
   phrases + 2–3 near-miss paraphrases per skill, **prioritized by `G_t`'s confusable
   pairs** (probe the collisions the graph found). Depends on Phase 1.
2. **Routing** — present ONLY the description set (the router's real input) + a probe; ask
   the model to pick one skill. **Router is harness-native** (measures how the real router
   would route): on Codex, `gpt-5.6-luna` at `model_reasoning_effort=high` (per the user's
   delegation pin; needs codex-cli ≥ 0.144; batch probes to limit session-file pollution);
   on Claude Code, Opus 4.8 (a subagent). Implement as a pluggable `Router` interface with
   a manual fallback when no model is available; auto-select the default by detected harness.
3. **Score** — confusion matrix, per-skill precision/recall, overall accuracy; persist to
   `.plugin-improver/routing-<date>.json`.
4. **Gate** — `plugin-tune-triggers` and `plugin-improve` must show measured accuracy ≥
   baseline after a description change. The non-regression gate now carries a number.

Later opt-in upgrade (separate, not this roadmap): swap lexical `G_t` edges for an
embedding k-NN graph when embeddings are available; degrade to lexical otherwise.

## Build sequence & ownership

1. Phase 1 (graph core) — foundational; unblocks 2, 3, 4. **Done** (`curator.py graph`, v1.2.0).
2. Phase 2 (scorer + CI) — consumes `G_t` collision count. **Done** (`scripts/score.py`).
3. Phase 3 (portfolio) — consumes the scorer. **Done** (`scripts/portfolio.py`).
   `plugin-migrate` deliberately **not** built (out of scope: diagnostics, not migration).
4. Phase 4 (routing loop) — consumes `G_t`; harness-native model; opt-in. **Done**
   (`scripts/route_eval.py`).

Follow-through for each shipped phase: keep `validate.py` and `curator.py selftest` green,
bump BOTH manifests together, update CHANGELOG + LEDGER, `bash scripts/sync.sh`, commit,
push, confirm CI. No existing skill was renamed. The only new skill still owed is
`plugin-migrate`, which this diagnostics batch left as a future item.
