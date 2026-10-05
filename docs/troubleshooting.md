# plugin-improver troubleshooting

Use an editable plugin source folder, not an installed copy under
`~/.claude/plugins/cache/` or `~/.codex/plugins/cache/`. See
[installation](../README.md#install) and [architecture](architecture.md).

## Skills do not appear

- Claude Code: confirm the `plugin-improver` marketplace is added and
  `plugin-improver@plugin-improver` is installed, then refresh or restart the host
- Codex: confirm the source folder contains `.codex-plugin/plugin.json` and
  `skills/`, register its local marketplace entry, then install from that marketplace
- After source updates, refresh the installed plugin and start a new session;
  source version, cache version, and loaded session version can differ
- For explicit invocation, use `$plugin-audit` on Codex or
  `/plugin-improver:plugin-audit` on Claude Code, with your source folder as the target

Copying files alone does not establish marketplace registration or live discovery.
The plugin's own Codex manifest declares a skills surface; an absent
plugin-improver MCP server is not an installation failure because none is declared.

## The sync helper says it finished, but one host is stale

[`scripts/sync.sh`](../scripts/sync.sh) copies the source into Codex using `rsync`
and handles Claude Code through its marketplace CLI, or prints manual instructions
when the CLI is absent. Several marketplace add/update calls tolerate errors;
inspect output and verify in a new host session rather than relying on “Done.”

The helper requires a POSIX shell and `rsync`. It uses `--delete` for non-excluded
destination files, so do not keep independent changes in its Codex destination.
Excluded bookkeeping such as `.plugin-improver` and `state.yaml` is protected.
See [local development](../CONTRIBUTING.md#installing-locally) before running it.

## Understand validator findings

From the plugin-improver source root:

```bash
python3 scripts/validate.py /path/to/my-plugin --json
```

[`validate.py`](../scripts/validate.py) emits stable `PI-<letter><3 digits>`
finding codes with severity, path, and a fix hint. Namespaces include manifests
(`M`), skill frontmatter (`S`), body budget (`B`), references (`R`), Codex interface
(`I`), commands (`C`), parity (`P`), hooks (`H`), assets (`A`), and MCP shape (`J`).

- Exit 0: no error-severity findings; warnings and informational findings may remain
- Exit 1: at least one check has an error
- Exit 2: the target does not look like a plugin root

Read the exact finding before changing anything. For example, `PI-M006` is
manifest version disagreement, `PI-S005` is a description exceeding 400 characters,
and `PI-R001` is an unresolved reference. The soft body limit warns above 600
words; the hard limit fails above 1,500. A green validator proves structural
checks, not correct runtime behavior or measured trigger accuracy.

## A score or baseline gate is surprising

```bash
python3 scripts/score.py /path/to/my-plugin --json
python3 scripts/tokens.py /path/to/my-plugin
```

[`score.py`](../scripts/score.py) reports deterministic evidence and outstanding
`needs_judgment`; a fuller audit still requires judgment. Its effective score
normalizes applicable machine-scored dimensions to 100. Token reports use
estimates rather than tokenizer-exact counts.

`score.py --min-baseline PATH` warns and skips regression comparison when the
baseline is missing, unreadable, has no usable `total.auto`, or predates effective
scoring. Exit 0 alone therefore does not prove that a baseline comparison occurred.
Inspect stderr and the baseline schema. Use an explicit `--min N` floor when a
numeric floor is what you intend to enforce. Current repository CI uses 70.

Saving a baseline or running an agent-driven improvement pass changes files.
Choose that separately from inspection, and preserve the target's provenance and
decision history.

## Share a useful issue

Include the host, OS, Python version, plugin source commit, both manifest versions,
sanitized command, exit status, and relevant finding codes. Note which tests ran
and whether the problem is in source, an installed cache, or a loaded session.
Do not post private session logs, credentials, or unsanitized home-directory paths.
