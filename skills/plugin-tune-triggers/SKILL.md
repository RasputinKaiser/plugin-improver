---
name: plugin-tune-triggers
description: Tune skill descriptions and trigger behavior in an existing plugin so each skill fires exactly when it should. Use when a skill triggers too often, never triggers, overlaps with another skill, or when asked to improve descriptions, trigger phrases, or implicit invocation. Not for rewriting a skill's body instructions.
---

Fix when and how the target plugin's skills trigger. Implicit invocation is driven entirely by the `description` frontmatter, so that string is the product here. Diagnose collisions with the routing graph and prove every rewrite with a MEASURED routing eval — never ship a description change on a mental check alone.

## 1. Gather the trigger surface

1. Collect every `description` from `skills/*/SKILL.md` in the target plugin.
2. Also list skill names from the installed roots (`~/.claude/skills/`, `~/.codex/skills/`) and other enabled plugins if discoverable — collisions across sources cause misfires too.
3. On Codex, note any `agents/openai.yaml` `policy.allow_implicit_invocation` values (Claude Code has no such opt-out — its triggering is description-only).

## 2. Diagnose with the routing graph

Don't eyeball which skills collide — measure it. Build the trigger-collision graph (G_t) over the target and installed roots:

```
python3 skills/skill-curator/scripts/curator.py graph --md /tmp/graph.md
```

Read three signals, in order (details in `references/description-patterns.md`):

- **Confusable pairs / collision clusters** — each edge records WHY (shared distinctive terms, a shared bigram, or a shared quoted PHRASE). These are the descriptions that actually claim each other's prompts, not the ones you'd guess.
- **Trigger-hogs** (betweenness · degree) — the descriptions bridging the most topic groups. Sharpen these first; one edit clears many edges.
- **Minimal-edit set** — the K descriptions whose edits remove every collision edge. This is your work list; target the descriptions covering the most edges.

Then check each flagged description against `references/description-patterns.md`: does it state WHAT, WHEN (verbatim trigger phrases), and when NOT? Is it ≤ 2 sentences of substance and ≤ 400 chars?

## 3. Author probes, not a mental matrix

Turn the test into a persisted regression, not a thought experiment. For each skill you'll touch, write 5 prompts that SHOULD trigger it and 5 near-miss prompts that should route to a sibling or nothing (`references/description-patterns.md` shows how to author near-misses from the graph's shared terms). Persist them as a probes file the eval can score:

```
python3 skills/skill-curator/scripts/curator.py probes --out-dir .plugin-improver/probes
```

Add your paraphrase and near-miss probes to the generated `probes.json` — verbatim phrases alone overstate accuracy. Keep the file in the target plugin; it is the regression test for this and every future pass.

## 4. Rewrite

Rewrite failing descriptions using the anatomy and before/after examples in `references/description-patterns.md`. Rules:

- Third person, starts with a verb phrase describing the capability.
- Include the user's actual words as trigger phrases ("audit", "score", "health-check"); add the distinctive term the graph says is missing.
- One negative-scope clause per nearby sibling. Never grow a description to fix precision — replace vague words with specific ones.

For niche, destructive, or expensive skills on Codex, set `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. Claude Code offers no equivalent opt-out — keep the description precise and negative-scoped, or ship the capability as a command instead of an auto-triggering skill.

## 5. Verify — measured, gated

Score the probes against the rewritten descriptions and refuse to ship a regression:

```
python3 scripts/route_eval.py --probes .plugin-improver/probes/probes.json --min-baseline
```

A description change ships only if MEASURED routing accuracy is ≥ the recorded baseline; `--min-baseline` fails the run otherwise, so churn that doesn't help can't land. Then re-run the graph build to confirm the collision edges you targeted are gone.

Show the user a before/after diff per skill formatted per `../plugin-audit/references/report-style.md` (char counts, which probe/matrix cases the rewrite fixes, and the measured accuracy delta). Do not touch skill `name` fields — they are identifiers.
