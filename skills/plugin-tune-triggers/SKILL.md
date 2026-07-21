---
name: plugin-tune-triggers
description: Tune skill descriptions and trigger behavior in an existing Codex plugin so each skill fires exactly when it should. Use when a skill triggers too often, never triggers, overlaps with another skill, or when asked to improve descriptions, trigger phrases, or implicit invocation. Not for rewriting a skill's body instructions.
---

Fix when and how the target plugin's skills trigger. Implicit invocation is driven entirely by the `description` frontmatter, so that string is the product here.

## 1. Gather the trigger surface

1. Collect every `description` from `skills/*/SKILL.md` in the target plugin.
2. Also list skill names from `~/.agents/skills/` and other enabled plugins if discoverable — collisions across sources cause misfires too.
3. Note any `agents/openai.yaml` files and their `policy.allow_implicit_invocation` values.

## 2. Diagnose

For each description, check against `references/description-patterns.md`:

- Does it state WHAT the skill does, WHEN to use it (verbatim trigger phrases), and when NOT to?
- Is it specific enough that a router choosing among 30 skills would pick correctly?
- Does it collide with a sibling skill? Two descriptions that could claim the same prompt is a bug in both.
- Is it within budget (≤ 2 sentences of substance, ≤ 400 chars)? Descriptions load into every session.

## 3. Build a test matrix before rewriting

Write 5 prompts that SHOULD trigger the skill and 5 near-miss prompts that should NOT (they belong to a sibling skill or to no skill). Keep the matrix — it is the regression test for this and every future pass.

## 4. Rewrite

Rewrite failing descriptions using the anatomy and before/after examples in `references/description-patterns.md`. Rules:

- Third person, starts with a verb phrase describing the capability.
- Include the user's actual words as trigger phrases ("audit", "score", "health-check").
- One negative-scope clause when a sibling skill is nearby.
- Never grow a description to fix precision — replace vague words with specific ones.

For niche, destructive, or expensive skills, set `policy.allow_implicit_invocation: false` in `agents/openai.yaml` so only explicit `$skill` invocation works.

## 5. Verify

Run every matrix prompt mentally against the FULL set of sibling descriptions: each should-trigger prompt selects the right skill; each should-not prompt does not. Show the user a before/after diff per skill formatted per `../plugin-audit/references/report-style.md` (char counts, matrix cases fixed). Do not touch skill `name` fields — they are identifiers.
