# Plugin health rubric (100 points)

Score each dimension independently. Deduct only with concrete evidence. Half points allowed.

## 1. Manifest integrity — 15 points

- 5 — Valid JSON, kebab-case `name`, semver `version`, accurate `description`. Multi-manifest plugins (`.claude-plugin/plugin.json`, `.ncode-plugin/marketplace.json` alongside `.codex-plugin/`): versions must agree across all manifests — drift is a deduction here.
- 4 — All component pointers (`skills`, `hooks`, `mcpServers`, `apps`) present where components exist, `./`-prefixed, inside plugin root.
- 3 — Correct layout: only `plugin.json` in `.codex-plugin/`; components at root.
- 3 — Publisher metadata appropriate to distribution level: `author` always; `interface.displayName`/`shortDescription` if shared; icons/legal links only if published.

## 2. Skill quality — 25 points

Score across all skills, weight by how central each skill is.

- 8 — Each skill does one job. No kitchen-sink skills; no two skills doing the same job.
- 7 — Bodies are imperative instructions for the agent (verb-first, concrete steps, explicit inputs/outputs) — not user documentation, not marketing.
- 5 — Steps are actionable: file paths, commands, exact formats. An agent could follow them without guessing.
- 5 — Failure handling: what to do when a file is missing, a command fails, or input is ambiguous.

## 3. Trigger precision — 20 points

- 7 — Every description states what the skill does AND when to use it, with concrete trigger phrases users actually say.
- 5 — Negative scope: says when NOT to use it, or is precise enough that misfires are unlikely.
- 5 — No trigger collisions: no two skills in the plugin (or obvious user-level skills) claim the same prompt.
- 3 — Risky or niche skills opt out of implicit invocation via `agents/openai.yaml` `policy.allow_implicit_invocation: false`.

## 4. Context economy — 20 points

Budgets (flag, then deduct):

| Item | Budget | Hard flag |
|---|---|---|
| Skill description | ≤ 2 sentences, ≤ 400 chars | > 600 chars |
| SKILL.md body | ≤ 600 words | > 1,500 words |
| References loaded eagerly | 0 (load on demand) | body inlines reference content |

- 8 — Bodies within budget; detail pushed to `references/` (progressive disclosure).
- 6 — No duplicated content across skills; shared material lives in one reference, pointed to.
- 4 — Descriptions within budget (they load into every session's metadata).
- 2 — No dead weight: unused directories, stale examples, empty files.

## 5. Hooks health — 10 points

If the plugin has no hooks and needs none, award 10.

- 3 — Valid `hooks.json` shape: event → matcher group → handlers.
- 3 — Contracts correct per event (see plugin-hooks skill references): Stop returns JSON on stdout; blocking uses documented shapes or exit 2 + stderr.
- 2 — Paths use `${PLUGIN_ROOT}`; scripts exist and are executable; sensible `timeout`.
- 2 — Hooks respect current limitations (tool events are Bash-only today; matchers ignored on UserPromptSubmit/Stop) rather than silently depending on unsupported behavior.

## 6. Distribution readiness — 10 points

- 4 — README covers what it does, the skills it ships, and install steps.
- 3 — Version discipline: version bumped with changes; changelog or ledger exists if the plugin has history.
- 3 — Marketplace entry (if any) has `policy.installation`, `policy.authentication`, `category`, and a resolvable `source.path`.

## Grade bands

- 90–100 — Excellent. Maintain; audit after major changes.
- 75–89 — Good. Quick wins available.
- 55–74 — Fair. Prioritized improvement pass recommended.
- < 55 — Poor. Structural work needed before feature work.
