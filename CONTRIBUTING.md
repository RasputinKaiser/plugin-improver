# Contributing to plugin-improver

plugin-improver is a dual-harness meta-plugin: it ships for **both Claude Code and
Codex** from a single repo. Contributions must keep both harnesses correct.

## Developing

- Skills live in `skills/<skill>/`. The `SKILL.md` body is shared and must be
  harness-neutral (true on both Claude Code and Codex); only branch into
  "On Codex… / On Claude Code…" where the harnesses genuinely differ.
- Push detail into `references/*.md` (progressive disclosure); keep SKILL.md bodies
  tight (≤ ~600 words) and descriptions ≤ 2 sentences / 400 chars. Every added
  sentence must change agent behavior — respect the context budget.
- `agents/openai.yaml` in each skill is Codex-only surface; keep it in sync but know
  Claude Code ignores it.
- Run the validator before every commit:

  ```
  python3 scripts/validate.py
  ```

  It is stdlib-only and self-contained. Exit 0 means all checks pass.

- **Keep both manifest versions in agreement.** `.claude-plugin/plugin.json` and
  `.codex-plugin/plugin.json` must share the same `name` and the same base semver
  `version` (the Codex manifest may carry a `+codex.<build>` metadata suffix; the
  base semver must match). The validator enforces this.

## Installing locally

Sync the repo into both harness plugin dirs with:

```
scripts/sync.sh
```

This installs into `~/.codex/plugins/` and `~/.claude/plugins/` so you can exercise
your changes in a real session on each harness.

## Pull requests

- `python3 scripts/validate.py` must pass (CI runs it on every push and PR).
- Do not rename the plugin or any existing skill `name` — they are identifiers users
  and configs depend on.
- Keep the two manifest versions in agreement in the same PR that bumps either.
- Author attribution is `RasputinKaiser` only.
