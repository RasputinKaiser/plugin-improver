# Plugin health rubric (100 points)

Score each dimension independently. Deduct only with concrete evidence. Half points allowed.

## 1. Manifest integrity — 15 points

- 4 — Each present `plugin.json` is valid JSON with kebab-case `name`, semver `version`, accurate `description`.
- 4 — Cross-harness parity: a plugin claiming dual-harness support ships BOTH `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, with identical `name` and agreeing `version` across every manifest (ignore any Codex `+build` suffix) — a missing manifest or version drift is a deduction. A single-harness plugin earns full credit for its one valid manifest.
- 3 — All component pointers (`skills`, `hooks`, `mcpServers`, `apps`) present where components exist, `./`-prefixed, inside plugin root.
- 2 — Correct layout: each manifest dir holds only its `plugin.json`/`marketplace.json`; components at root.
- 2 — Publisher metadata appropriate to distribution level: `author` always; interface `displayName`/`shortDescription` if shared; icons/legal links only if published.

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
- 3 — Risky or niche skills are guarded against accidental firing. On Codex, via `agents/openai.yaml` `policy.allow_implicit_invocation: false`. On Claude Code (which has no opt-out flag), via a tightly negative-scoped description or by shipping the capability as an explicit command. Award full credit to a single-harness plugin that uses its harness's available mechanism.

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
- 3 — Contracts correct per event (see plugin-hooks skill references): on Codex, Stop returns JSON on stdout, blocking uses documented shapes or exit 2 + stderr.
- 2 — Paths use `${CLAUDE_PLUGIN_ROOT}` (Codex also accepts `${PLUGIN_ROOT}`); scripts exist and are executable; sensible `timeout`.
- 2 — Hooks respect each target harness's limits rather than silently depending on unsupported behavior: on Codex tool events are Bash-only today and matchers are ignored on UserPromptSubmit/Stop; on Claude Code matchers match all tools.

## 6. Distribution readiness — 10 points

- 3 — README covers what it does, the skills it ships, and install steps (per targeted harness).
- 3 — Version discipline: version bumped with changes; changelog or ledger exists if the plugin has history.
- 4 — A marketplace entry exists for each harness the plugin targets, using that harness's own schema: Claude Code `.claude-plugin/marketplace.json` lists the plugin under `plugins[]` with a resolvable `source` (string or object) and a `category` (`policy.*` do not exist here); the Codex registration (`~/.agents/plugins/marketplace.json` or `~/.codex/config.toml [marketplaces]`) carries `policy.installation`, `policy.authentication`, `category`, and a resolvable `source.path`. A targeted harness with no entry is a deduction; do not deduct a Claude Code entry for lacking Codex-only `policy` fields.

## Grade bands

- 90–100 — Excellent. Maintain; audit after major changes.
- 75–89 — Good. Quick wins available.
- 55–74 — Fair. Prioritized improvement pass recommended.
- < 55 — Poor. Structural work needed before feature work.
