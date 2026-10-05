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

## Current CI checks

Run the [workflow's](.github/workflows/ci.yml) command set from the repository root:

```bash
python3 scripts/validate.py
python3 skills/skill-curator/scripts/curator.py selftest
python3 scripts/score.py selftest
python3 scripts/portfolio.py selftest
python3 scripts/calibrate.py selftest
python3 scripts/score.py . --min 70
```

The deterministic selftests use temporary fixtures. The final command checks the
current repository against CI's score floor. Diagnostic warnings are advisory;
validator error findings fail the run. See [troubleshooting](docs/troubleshooting.md)
for finding codes and score-baseline caveats. For documentation changes, check
relative links and verify every new command against its script's CLI parser.
Report any checks you could not run and why.

## Installing locally

After reviewing the helper, sync the source into Codex and install or refresh the
Claude Code marketplace with:

```
scripts/sync.sh
```

The helper uses `rsync --delete` to refresh `~/.codex/plugins/plugin-improver/`.
It preserves excluded per-install bookkeeping such as `.plugin-improver` and
`state.yaml`, but other destination files absent from the source can be removed.
Do not keep independent edits in that destination.

For Claude Code, it invokes the available `claude` CLI marketplace add/update and
plugin install/update commands. Without the CLI it prints the interactive commands
for you to run; it does not copy files directly into the Claude cache. Some
marketplace operations tolerate failures, so the helper's final message alone
does not prove both hosts installed successfully. Verify skills in a new session
on each host. Codex marketplace registration remains a separate step from copying
the source to disk; see [the README](README.md#codex).

## Pull requests

- `python3 scripts/validate.py` must pass (CI runs it on every push and PR).
- Do not rename the plugin or any existing skill `name` — they are identifiers users
  and configs depend on.
- Keep the two manifest versions in agreement in the same PR that bumps either.
- Author attribution is `RasputinKaiser` only.

