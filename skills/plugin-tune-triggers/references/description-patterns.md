# Description patterns for skill triggering

The `description` is the ONLY signal the router sees before deciding to load a skill. Optimize it like an API contract, not ad copy.

## Anatomy of a strong description

```
<Verb phrase: what it does, on what> <WHEN: "Use when..." with verbatim
trigger phrases users say>. <Optional: coverage nouns that aid matching>.
<NOT clause: nearest sibling or lookalike task it must NOT claim>.
```

## Before / after examples

**Too vague — never fires or misfires**

- Before: `Helps with database stuff.`
- After: `Write and optimize PostgreSQL queries and migrations. Use when asked to write SQL, speed up a slow query, design a schema, or create a migration. Not for MongoDB or application-level ORM configuration.`

**Marketing copy — router can't match words users say**

- Before: `Your one-stop shop for world-class deployment excellence!`
- After: `Deploy this repo to staging or production. Use when asked to deploy, ship, roll out, or roll back a release. Not for local dev servers.`

**Collision pair — both claim "review"**

- Before A: `Review code changes.` / Before B: `Review pull requests.`
- After A: `Review uncommitted local changes for bugs and style before commit. Not for opened pull requests.`
- After B: `Review an opened GitHub pull request and post review comments. Not for uncommitted local changes.`

**Missing negative scope**

- Before: `Work with PDF files.`
- After: `Extract text and tables from PDFs and fill PDF forms. Use when a .pdf file is the input or output. Not for Word documents or scanned-image OCR quality restoration.`

## Anti-patterns

- First person ("I can help you...") — routers match capabilities, not chat.
- Trigger words only in the body — the body is not loaded at routing time.
- Restating the skill name and nothing else.
- Lists of 15 trigger synonyms — 3 or 4 that users actually say beat 15 generic ones.
- Growing past ~400 chars — every char is paid in every session's context.

## Reading the routing graph

The graph (`curator.py graph`) is measured collision evidence — read it, don't guess which skills fight. Three signals, each pointing at a specific edit:

- **Confusable pair / cluster edge** — every edge prints WHY: `shared: <terms>` and, when present, `PHRASES: <quoted trigger>`. Fix by making ONE side distinctive: drop or replace the generic shared token, or add a term the other skill can't claim. If the edge names a shared PHRASE, one skill must stop claiming that phrase (reword it or add a NOT-clause naming the sibling).
  - Example edge `evaluate-plugin ~ evaluate-skill — shared: evaluate, fix, first; PHRASES: what should i fix first` → give one a distinctive object ("evaluate a whole plugin's manifest+skills" vs "evaluate a single skill's quality") and let only one own "what should I fix first".
- **Trigger-hog** (high betweenness) — bridges many topic groups, so a single sharpening removes many edges. Edit these before leaf skills.
- **Minimal-edit set** — the smallest set of descriptions whose edits clear every edge. Work this list top-down; skills nearer the top cover the most edges.

A lexical edge is a hypothesis. Confirm the fix behaviorally with probes + `route_eval.py` (SKILL.md step 5), not by re-reading the descriptions.

## Authoring near-miss probes

Near-misses are where routing actually breaks — a probe set of only should-trigger phrases will score ~100% and prove nothing. For each skill:

- **Should-trigger (5)** — real user phrasings, including paraphrases the description doesn't quote verbatim.
- **Near-miss (5)** — prompts a naive router would hand to THIS skill but that belong to a sibling or to no skill. Mine them straight from the graph: each `shared:` term on a collision edge is a near-miss seed. Write a prompt built around that shared term whose correct target is the sibling, and confirm the rewritten description no longer claims it.

## Test matrix as a probes file

| # | Prompt | Expected skill | Passes before | Passes after |
|---|--------|----------------|---------------|--------------|
| S1–S5 | should-trigger prompts | this skill | | |
| N1–N5 | near-miss prompts | sibling / none | | |

Persist this as `probes.json` in the target plugin's `.plugin-improver/probes/` (seed it with `curator.py probes`, then hand-add rows) so `route_eval.py --min-baseline` reruns it every pass — a measured regression test, not a mental exercise.

## Opting out of implicit invocation (Codex only)

`skills/<name>/agents/openai.yaml`:

```yaml
policy:
  allow_implicit_invocation: false
```

Use for destructive operations, expensive workflows, or skills with unavoidably generic descriptions. Explicit invocation still works. Claude Code has no equivalent flag — there, rely on a precise, negative-scoped description or ship the capability as a command.
