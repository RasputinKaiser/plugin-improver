# Plugin health rubric (100 points)

Score each dimension independently on **graduated** criteria — not pass/fail. Validity earns the MIDDLE of a sub-point's range; full marks require excellence beyond mere validity. Award partial credit that scales with how far a plugin exceeds the bar (leaner, more complete, more robust = more). Deduct only with concrete evidence. Half points allowed throughout.

The deterministic scorer (`score.py`) computes the objective slice of several dimensions and returns `{dimension:{auto,max,needs_judgment}}`; treat `auto` as the machine FLOOR (mechanics that are simply present/valid) and judge the quality gradient on top. `references/deterministic-scoring.md` maps each dimension to what is auto-scored vs judged. Two runtime diagnostics supply evidence lines: `tokens.py` (token/budget report) feeds Context economy, and `errscan.py` (session-log error scan) feeds Hooks health — cited inline below.

## Not applicable → redistribute

A dimension (or a sub-point) that **genuinely does not apply** is DROPPED, and its weight is redistributed proportionally across the applicable dimensions, renormalizing the total back to 100. It never earns a free max.

Example: a plugin that correctly ships no hooks and needs none has no Hooks health dimension — drop its 10 points and spread them across the other five in proportion to their nominal maxes, then score out of 100. Likewise, parity sub-points that assume dual-harness support do not apply to a correct single-harness plugin: drop those sub-points and redistribute within the dimension. "Not applicable" means the capability is correctly absent, NOT that it is present but weak — a broken or missing-but-needed component is scored low, not dropped.

## 1. Manifest integrity — 15 points

Full marks require complete, accurate publisher metadata AND lean, correct pointers — not merely valid JSON. Score each sub-point on the gradient from "present/parses" (middle) to "exemplary" (max).

- 4 — Manifest correctness. Middle: each present `plugin.json` is valid JSON with kebab-case `name` and semver `version`. Toward full: `description` is accurate, specific, and current (not stale or templated); nothing vestigial. Malformed, drifted, or misleading fields deduct.
- 4 — Cross-harness parity. A dual-harness plugin ships BOTH `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` with identical `name` and agreeing `version` (ignore any Codex `+build` suffix); a missing manifest or version drift is a deduction. A single-harness plugin: this sub-point does not apply — drop and redistribute within the dimension (its one valid manifest is scored under sub-point 1, not handed a free 4 here).
- 3 — Pointer hygiene. Middle: component pointers (`skills`, `hooks`, `mcpServers`, `apps`) present where components exist, `./`-prefixed, inside plugin root. Toward full: pointers are lean and exact — no dangling, redundant, or unused entries; every declared path resolves.
- 2 — Layout discipline. Each manifest dir holds only its `plugin.json`/`marketplace.json`; components at root. Full credit requires a clean tree with no stray or misplaced files; partial otherwise.
- 2 — Publisher metadata appropriate to distribution level. Middle: `author` present. Toward full: interface `displayName`/`shortDescription` present and polished if shared, icons/legal links present if published. Thin or absent metadata at the plugin's actual distribution level deducts.

## 2. Skill quality — 25 points

Score across all skills, weight by how central each skill is. Full marks require skills that an agent can execute flawlessly without guessing — not just prose that reads plausibly. Credit is graduated per criterion: uneven quality across skills pulls the score toward the middle.

- 8 — Single responsibility. Middle: skills mostly do one job. Toward full: every skill has one crisp job, no kitchen-sink skills, and no two skills overlapping. Any duplication or a bloated catch-all skill deducts in proportion to how central the offender is.
- 7 — Imperative agent instructions. Middle: bodies are mostly directive. Toward full: consistently verb-first, concrete steps with explicit inputs/outputs, zero user-doc or marketing tone. Narrative or explanatory drift deducts.
- 5 — Actionability. Middle: steps are followable in the common case. Toward full: exact file paths, commands, and formats throughout, leaving nothing to guess. Vague or hand-wavy steps deduct.
- 5 — Failure handling. Middle: the main failure mode is addressed. Toward full: missing files, failing commands, and ambiguous input are each handled explicitly across the skills. Silence on failure paths deducts.

## 3. Trigger precision — 20 points

Full marks require descriptions precise enough that the right skill fires and the wrong one never does — not merely a description that exists.

- 7 — What + when. Middle: descriptions state what the skill does. Toward full: also state WHEN to use it with concrete trigger phrases users actually say. Generic or when-less descriptions deduct.
- 5 — Negative scope. Middle: scope is implicitly narrow. Toward full: explicit "not for X" clauses, or descriptions precise enough that misfires are genuinely unlikely. Broad, ambiguous scope deducts.
- 5 — No collisions. Middle: no obvious overlap. Toward full: verified no two skills in the plugin (or obvious user-level skills) claim the same prompt space. Any real collision deducts.
- 3 — Guarding risky/niche skills. Middle: risk is acknowledged. Toward full: accidental firing is actively prevented — on Codex via `agents/openai.yaml` `policy.allow_implicit_invocation: false`; on Claude Code (no opt-out flag) via a tightly negative-scoped description or by shipping the capability as an explicit command. A single-harness plugin is scored on its harness's available mechanism; if the plugin has no risky/niche skills, this sub-point does not apply — drop and redistribute within the dimension.

## 4. Context economy — 20 points

Reward leanness: credit scales with how far UNDER budget a plugin sits and how genuine its progressive disclosure is — merely being within budget earns the middle, not the max.

Budgets (flag, then grade the gradient):

| Item | Budget | Hard flag |
|---|---|---|
| Skill description | ≤ 2 sentences, ≤ 400 chars | > 600 chars |
| SKILL.md body | ≤ 600 words | > 1,500 words |
| References loaded eagerly | 0 (load on demand) | body inlines reference content |

- 8 — Body economy + progressive disclosure. Middle: bodies within budget. Toward full: comfortably UNDER budget with detail genuinely pushed to `references/` and loaded on demand — not padded to the limit. Bodies near or over budget, or that inline reference content, deduct.
- 6 — No duplication. Middle: no glaring repeats. Toward full: shared material lives in exactly one reference that others point to; zero copy-paste across skills. Duplicated passages deduct.
- 4 — Description economy. Middle: descriptions within budget. Toward full: tight and well under the char limit while still stating what + when. Bloated descriptions (they load into every session's metadata) deduct.
- 2 — No dead weight. Full credit requires no unused directories, stale examples, or empty files; any dead weight deducts.

Evidence: read the token/budget report (`tokens.py`) here. Its session-tax headline and per-skill budget headroom quantify leanness — a skill merely at budget scores mid, one comfortably under scores high, and one over its body/description budget (or a plugin whose session tax has grown against baseline) is a concrete deduction line. A green machine floor from `score.py` (chars/words within budget, no dead files) fixes the mechanical part; judge duplication and progressive-disclosure quality on top.

## 5. Hooks health — 10 points

If the plugin correctly ships no hooks and needs none, this dimension does NOT apply — drop it and redistribute its 10 points across the other five dimensions (see the redistribution rule above). Do not award a free 10. Score the sub-points below only when hooks exist; full marks require hooks that are correct at RUNTIME, not just valid on paper.

- 3 — Shape. Middle: valid `hooks.json` shape (event → matcher group → handlers). Toward full: clean, minimal, no vestigial entries.
- 3 — Runtime-correct contracts. Static shape is necessary but not sufficient — full credit requires the hook actually runs without error and honors its event's contract (on Codex: Stop returns JSON on stdout; blocking uses documented shapes or exit 2 + stderr). A hook whose command errors, times out, or misbehaves at runtime deducts even with valid JSON.
- 2 — Paths + executables. Middle: paths use `${CLAUDE_PLUGIN_ROOT}` (Codex also accepts `${PLUGIN_ROOT}`). Toward full: every referenced script exists, is executable, and carries a sensible `timeout`. Absolute/bare paths or missing scripts deduct.
- 2 — Per-harness limits respected. Full credit requires hooks that work within each target harness's actual limits rather than silently depending on unsupported behavior (on Codex tool events are Bash-only today and matchers are ignored on UserPromptSubmit/Stop; on Claude Code matchers match all tools). Latent dependence on unsupported behavior deducts.

Evidence: read the runtime error scan (`errscan.py`) here. Hook/tool/skill errors it aggregates for the target plugin are direct evidence against the contracts and paths sub-points — a hook that throws, times out, or hits a missing script at runtime is a real deduction the static shape check cannot see. `score.py` auto-scores only the shape/paths-present part; runtime health and per-harness correctness are judgment on top.

## 6. Distribution readiness — 10 points

Full marks require a plugin someone else could actually find, install, and trust — not just a README that exists.

- 3 — README. Middle: covers what the plugin does. Toward full: also lists the skills it ships and correct install steps per targeted harness, and is current with the code. Thin, stale, or install-less READMEs deduct.
- 3 — Version discipline. Middle: a version exists. Toward full: version is bumped with changes and a changelog or ledger records history where the plugin has any. Stale versions or missing history deduct.
- 4 — Marketplace entries. A marketplace entry exists for each harness the plugin targets, in that harness's own schema: Claude Code `.claude-plugin/marketplace.json` lists the plugin under `plugins[]` with a resolvable `source` and a `category` (`policy.*` do not exist here); the Codex registration (`~/.agents/plugins/marketplace.json` or `~/.codex/config.toml [marketplaces]`) carries `policy.installation`, `policy.authentication`, `category`, and a resolvable `source.path`. A targeted harness with no entry deducts; a harness the plugin does not target does not apply (drop that share and redistribute within the dimension). Do not deduct a Claude Code entry for lacking Codex-only `policy` fields.

## Grade bands

Score each dimension on the graduated criteria above so a typical good-but-improvable plugin lands **Solid/Strong (~78–84)**, and reserve **Exceptional** for a plugin that is near-perfect across ALL applicable dimensions.

- **92–100 — Exceptional.** Strong across every applicable dimension; nothing material left to improve. Rare but achievable.
- **82–91 — Strong.** Solid throughout with a few real wins available.
- **68–81 — Solid.** Mature and working; a prioritized improvement pass pays off.
- **50–67 — Needs work.** Functional but with clear gaps; improve before feature work.
- **< 50 — Poor.** Structural problems; rebuild the weak dimensions first.
