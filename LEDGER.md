# Improvement ledger — plugin-improver

## 2026-07-20 — 1.2.0 → 1.3.0 (diagnostics & evaluation batch: roadmap Phases 2–4 + error/token mining)
- Parallel batch: 9 independently-mergeable units, each owning disjoint files (worktree-isolated,
  merged via 9 PRs #1–#9). curator.py was deliberately kept FROZEN — new capabilities ship as new
  stdlib sibling scripts under `scripts/`, so no worker collided on the 2700-line engine. Workers were
  forbidden from touching versions/CHANGELOG/LEDGER/README/manifests; this integration pass does the
  single release bump.
- Delivered: `score.py` (Phase 2 deterministic scorer + `--min`/`--min-baseline` gate, wired into CI),
  `portfolio.py` (Phase 3 sweep + score trajectory), `route_eval.py` (Phase 4 routing loop, offline by
  default), `errscan.py` (runtime hook/tool/skill-error mining with secret redaction), `tokens.py`
  (per-plugin token/budget report). `validate.py` upgraded to a diagnostic linter (codes/severity/fix
  hints, +3 checks, backward-compatible `--json`). Skills `plugin-audit`/`plugin-improve`/
  `plugin-tune-triggers` now consume the numeric gates; rubric total held at 100.
- Every script worker ran an independent code-review pass that caught REAL bugs before merge: score.py
  (5 — flag IndexError, non-numeric `--min`, malformed-baseline crash, parity over-credit, JSON stdout
  pollution), tokens.py (folded-frontmatter descriptions read as 0 tokens), route_eval.py (3 graceful-
  failure gaps), errscan.py (3 — Codex `exec_command_end` shell exits unhandled, `sk_live_` redaction
  gap, cross-plugin skill bucket collision). All fixed + regression-covered.
- Verify (combined tree on main): validate.py `PASS 11/11`; curator selftest `83/83`; score/portfolio/
  tokens/errscan/route_eval selftests all green; self deterministic auto-score 60/100 (CI floor 57).
  Minor bump (new capability, no behavior change to existing skills). NOT done: `plugin-migrate` (Phase
  3's 8th skill) — deferred as out of scope for a diagnostics/evaluation batch; roster stays 7 skills.

## 2026-07-20 — 1.1.1 → 1.2.0 (roadmap Phase 1: routing graph in skill-curator)
- Implemented the graph core from docs/ROADMAP-measurement-graph.md: `build_trigger_graph`
  (G_t, undirected weighted) and `build_reference_graph` (G_r, directed) plus stdlib graph
  algorithms (connected_components, degree/betweenness centrality via Brandes,
  greedy_min_vertex_cover, find_cycles, in_degree). New `curator.py graph` subcommand
  (--md/--mermaid/--dot/--json) + a compact routing-graph summary folded into `report`.
- Worker (Opus) reused analyze()'s proven collision predicate for edge-gating after a naive
  Jaccard threshold collapsed the 280-skill inventory into one blob — good call; centrality
  still ranks the real hubs (hyperframes, motion-graphics top by betweenness). Collision
  fingerprints kept compatible with the decision ledger so decide/archive still work.
- Verify: curator selftest 69 → 83 (all green, incl. a hand-verified Brandes betweenness
  case), validate.py 8/8, graph runs clean on the real inventory (280 skills, 314 edges,
  22 clusters, 90 orphans, 203 broken handoffs, 75 cycles — spot-checked one as a real find).
  SKILL.md body 588w (≤600). Minor bump (new capability). Next: Phase 2 (deterministic
  scorer + CI gate), which consumes G_t's collision count.

## 2026-07-20 — 1.1.0 → 1.1.1 (sync.sh auto-installs on Claude Code)
- `scripts/sync.sh` now performs the Claude Code marketplace add/install/update via the
  `claude` plugin CLI (idempotent; prints the interactive fallback if the CLI is missing),
  so a single `bash scripts/sync.sh` genuinely installs on BOTH harnesses. Previously it
  only printed the Claude Code slash commands. Patch bump (tooling; no skill/behavior change).

## 2026-07-20 — 1.0.1 → 1.1.0 (Claude Code commands surface)
- Added a `commands/` slash command per skill (7 total) — Claude Code's explicit-invocation
  analogue of Codex `$skill`. Auto-discovered by Claude Code, ignored by Codex; each is a thin
  wrapper that invokes the matching skill on an optional target path.
- `scripts/validate.py`: new "Claude Code commands" check (now 8 checks) — every command file
  must carry a frontmatter description; for plugin-improver itself, one command per skill is
  required. Neutralized a hardcoded `7/7` example so the check count can grow without going stale.
- README Usage + docs/architecture.md updated to document the commands surface.
- Minor bump (new capability, no behavior change to existing skills). Verify: validator 8/8
  (self + external), curator 69/69, CI green. NOT done: no per-command `allowed-tools`
  restriction — these commands only invoke read/write skill work the user already drives.

## 2026-07-20 — 1.0.0 → 1.0.1 (dogfood pass: adversarial self-audit)
- Ran two adversarial Opus reviewers over the fresh 1.0.0 (new skills; dual-harness
  correctness). Reviewers CONFIRMED the suspect "On Claude Code…" hook claims are true
  and the rubric totals 100 — no HIGH defects. Applied the confirmed fixes:
  - `scripts/validate.py`: added an optional target-path arg (validate any plugin, not
    just self; roster enforced only for self); reference-integrity now scans `references/*.md`
    with code-fences stripped + a path-boundary lookbehind (an external `.../scripts/x.js`
    fragment was a false positive — fixed); marketplace check now matches `plugins[].name`.
  - scoring-rubric: scoped Codex-only `policy.installation`/`policy.authentication` away from
    Claude Code marketplace entries; trigger opt-out points earnable on Claude Code too. Total
    still 100.
  - Fixed instruction bugs: plugin-release validator path, plugin-scaffold validation step,
    Codex `source.path` example, false `plugin.json` `icon` claim, hook `model`-field caveat,
    a stale `12/12` report example.
  - `scripts/sync.sh`: exclude `state.yaml` from `--delete` so a Codex install's bookkeeping
    survives a sync.
- Verify: validator 7/7 (self + external target), curator selftest 69/69, rubric = 100, CI green.
- Deliberately NOT done: no version bump beyond patch (all fixes/wording); did not add a
  `commands/` surface for Claude Code (skills auto-trigger — unpaid context).

## 2026-07-20 — 0.4.0 → 1.0.0 (dual-harness rebuild, planner + parallel Opus workers)
- Made the plugin genuinely dual-harness (Claude Code + Codex) from one shared
  `skills/` tree. Added `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`;
  bumped both manifests to an agreeing `1.0.0` semver.
- All five existing skill bodies rewritten to be harness-neutral and correct on both:
  locate a plugin by `.claude-plugin/` OR `.codex-plugin/`; portable `${CLAUDE_PLUGIN_ROOT}`;
  plugin-hooks now presents hook capability per harness (Claude matches all tools + on by
  default vs Codex Bash-only + experimental flag + trust); scoring-rubric gained a
  cross-harness parity requirement inside Manifest integrity + Distribution (100-pt total
  unchanged). No skill `name` changed.
- Two new skills: `plugin-scaffold` (create a new dual-harness plugin) and `plugin-release`
  (package + publish to both marketplaces; prepares everything, hands the final tag/push to
  the user). Each ships `agents/openai.yaml` + a reference file.
- New engineering surface: `scripts/validate.py` (stdlib-only, 7-check registry: manifests
  parse & agree, frontmatter, body budgets, reference integrity, Codex openai.yaml, parity,
  assets), `scripts/sync.sh` (install to both harnesses), `.github/workflows/ci.yml` (runs
  the validator on push + PR). MIT LICENSE, CONTRIBUTING, first-class dual-install README,
  `docs/` (architecture + per-skill pages).
- Verification: validator 7/7, curator selftest 69/69, identity scan clean (RasputinKaiser
  only). Structured as a public repo at github.com/RasputinKaiser/plugin-improver.
- Deliberately NOT done: no skill removed/renamed; no heavyweight test framework beyond the
  validator; live installs left untouched until `scripts/sync.sh` is run.

## 2026-07-07 — 0.3.1 → 0.3.2 (pass by Claude/Cowork)
- plugin-improve: failure-handling fallbacks for missing scoring-rubric.md /
  regression-checklist.md (inline six-dimension scores; minimal verify list).
  Rationale: exact failure hit twice on 2026-07-07 in stripped skill-store
  copies; rubric 2.4 failure-handling.
- plugin-audit: locate step now maps plugin sources via config.toml
  [marketplaces] and forbids auditing read-only cache copies.
- Created LEDGER.md + .plugin-improver/baseline.json (the improver had no
  baseline of its own).
- Score 93 -> 96 (skill_quality 22->25). Context: bodies +71 words (+4.7%),
  descriptions unchanged — within 10% budget.
- Deliberately NOT done: registering [marketplaces.ralto-local] — its cache
  hosts 14 plugins from different source dirs; a single-plugin source would
  risk orphaning the other 13 on sync. NEXT PASS: build a proper ralto-local
  marketplace root (manifest listing all member plugins), then register it.
- Deliberately NOT done: state.yaml removal (may be packaging-tool state;
  needs user confirmation).

### 2026-07-07 addendum (0.3.2)
Deferred marketplace registration closed: [marketplaces.ralto-local] now registered, source ~/plugins/ralto-local — a root manifest listing all 9 member plugins via symlinks, so no member is orphaned by a sync. Verified: config tomllib-valid, throwaway codex exec session ran clean, all cache versions intact (every source version matched cache exactly at registration time).

## 2026-07-13 — 0.3.2 → 0.3.3 (pass by Claude/Cowork, self-applied: /plugin-improve on plugin-improver)
- Marketplace entry (ralto-local): added missing policy.authentication
  ON_INSTALL; verified source.path symlink resolves to this root. (rubric 6.3)
- plugin-improve Record step: multi-manifest sync line — .claude-plugin /
  .ncode-plugin siblings drift if only .codex-plugin is bumped; observed as a
  real risk on retro (its build.sh happens to sync; the loop alone wouldn't).
  +27 words, paid within budget.
- Added .plugin-improver/trigger-matrix.md for this plugin's own four skills
  (regression checklist references it "if present" — now it's present; not
  loaded eagerly, zero context cost).
- Finding withdrawn with evidence: state.yaml is NOT dead weight — it is the
  owner's active cross-repo packaging/state convention (retro, apifyer, goal,
  SIPS all carry one; retro's updated 3x this week). context_economy 19 -> 20
  by correction, not deletion.
- Score 96 -> 99 (context 19->20, distribution 8->10; others unchanged;
  trigger stays 19: user-level skill-store duplicates of these four skills
  still exist outside the plugin — user-space cleanup, deliberately not done
  here).
- Context delta: bodies 1590 -> 1610 words (+1.3%); descriptions 1339 -> 1339.
- Verify: manifests + marketplace JSON parse; names/dirs unchanged; frontmatter
  valid; trigger matrix prompts map 1:1; no hooks. One tooling stumble during
  verify (frontmatter regex assumed trailing newline after description; fixed
  in the check script, not the plugin).
- Next-pass candidate: dedupe the user-level skill-store copies of these four
  skills (trigger_precision's last point) — needs user decision on which copy
  wins.

## 2026-07-13 — 0.3.3 → 0.3.4 (pass 2, user-directed: harden beyond rubric)
- All three changes live in lazy references or one Baseline sentence; score
  unchanged 99/100 (the only open point is the excluded user-space dedupe).
  Justification for a flat-score pass: each change encodes a failure OBSERVED
  this week, not speculation —
  (1) checklist now runs the target's own tests: retro's suite was red on
      2026-07-13 while its state.yaml claimed 34/34 green;
  (2) checklist now verifies artifact content: an unmodified .skill zip
      shipped behind a successful-looking pipeline the same day;
  (3) baseline findings are hypotheses: the state.yaml "dead weight" finding
      survived two baselines before being disproven;
  (4) rubric: multi-manifest version drift named explicitly (retro 1.2.0
      precedent) — bookkeeping: CHANGELOG caught up (was stale at 0.3.1).
- Context delta: bodies 1610 -> 1640 (+1.9%, the Baseline sentence);
  descriptions unchanged 1339. References grew ~90 words (lazy, free).
- Deliberately NOT done: user-level skill-store dedupe (excluded by user);
  any further pass without new evidence — 99/100 with hardened references is
  STABLE; next passes should be evidence-driven, not scheduled.

## 2026-07-20 — 0.3.4 → 0.4.0 (merge pass: skill-curator absorbed, v3 expansion)

- User-directed consolidation: skill-curator (standalone skill, duplicated in
  ~/.codex/skills AND the Claude account skill store) is now the plugin's fifth
  skill. Closes the long-open trigger_precision point ON THE CODEX SIDE
  (~/.codex/skills/skill-curator archived via curator archive); the Claude
  account-store copies of all five skills still exist until the user swaps
  them in the claude.ai UI — delivered as packaged skill files this session.
- skill-curator v3 (curator.py 1756 -> 1938 lines, selftest 47 -> 62 checks,
  all green sandbox AND host, sha256 parity gated):
  new plugin-level findings plugin_version_drift / duplicate_plugins /
  stale_plugin_caches; new scan layer over plugin SOURCE roots
  (--plugin-source; default ~/.codex/plugins + ~/.claude/plugins minus cache/);
  drift always leads "Do these first" (correctness before token savings);
  findings are ledger-fingerprinted like every other section.
  Motivating real case: this plugin's own state.yaml claimed installed_cache
  0.3.2 while the real cache dir was 0.3.4 (stale bookkeeping); and during
  this pass, source 0.4.0 vs cache 0.3.4 was live drift the new finding
  flagged before the refresh (see verification below).
- Context discipline for the merged skill: description rewritten 585 -> 391
  chars; routing-evals + plugin-eval sections moved to a lazy
  references/routing-evals.md; body 563 words. agents/openai.yaml added.
- plugin-audit description: negative-scope clause swapped to point
  inventory-wide curation at skill-curator (+55 chars, paid for by the
  skill-curator trim). Trigger matrix now covers five skills; the old
  "audit my skills for sprawl" near-miss row is a should-trigger.
- Score after re-check against the rubric: 99/100 (manifest 15, skills 25,
  triggers 19, context 20, hooks 10, distribution 10). The open triggers
  point remains the Claude-side user-store duplicates (user action).
  Note: totals include a NEW skill; body words grew 1640 -> ~2200 by merge,
  not bloat — the same content previously cost two skill-store copies.
- Deliberately NOT done: absorbing tool-factory or skill-creator (user chose
  plugin-improver's four + skill-curator only); auto-deleting any user-store
  copy (archive-never-delete, user approval per item).
- Next-pass candidate: run the new plugin_version_drift finding across all
  ralto-local plugins and refresh any stale installs it surfaces.
- Post-merge adversarial review (independent Claude subagent; the planned
  codex-CLI second opinion hit the OpenAI usage limit until Jul 25): 4
  confirmed bugs found and FIXED same-pass, selftest 62 -> 69 checks —
  unguarded listdir crash on unreadable cache dirs; marketplace-less cache
  layouts mis-keyed as plugin="version" (false duplicate_plugins + silent
  drift misses); same-name source in both default roots double-counted drift
  under one fingerprint; 'unknown'/'latest' guard now applied to the source
  side too. Also: duplicate_plugins fp keyed on name only (ledger stability),
  cross-root cache maps merge instead of clobber, base_version strips one
  leading v only. Reviewer's remaining nitpicks (top_actions drift eviction
  at 6+, --no-plugins vs explicit --plugin-cache precedence) deliberately
  left; recorded here so the next pass can litigate them.
