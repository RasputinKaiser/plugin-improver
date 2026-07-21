#!/usr/bin/env sh
# sync.sh - install this repo into the local Codex + Claude Code harnesses.
#
#   Codex:  copies the plugin into ~/.codex/plugins/plugin-improver/
#   Claude: this repo IS a single-plugin marketplace (.claude-plugin/), so we do
#           NOT blindly copy into the Claude cache; we print the marketplace
#           command to run instead (adding via marketplace is the correct path).
#
# Idempotent. Uses rsync --delete with explicit excludes. No rm -rf on user dirs.
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PLUGIN_NAME=plugin-improver
CODEX_DEST="${HOME}/.codex/plugins/${PLUGIN_NAME}"

EXCLUDES="
--exclude=.git
--exclude=.github
--exclude=docs
--exclude=tests
--exclude=__pycache__
--exclude=*.pyc
--exclude=.DS_Store
--exclude=.plugin-improver
--exclude=state.yaml
"
# NOTE: excluded paths are also protected from --delete (rsync default), so a
# destination's per-install bookkeeping (.plugin-improver baseline, Codex
# state.yaml) survives a sync instead of being clobbered.

echo "plugin-improver sync"
echo "  source: ${REPO_ROOT}"
echo

# ---- Codex ---------------------------------------------------------------
echo "==> Codex: ${CODEX_DEST}"
mkdir -p "${CODEX_DEST}"
# shellcheck disable=SC2086
rsync -a --delete ${EXCLUDES} "${REPO_ROOT}/" "${CODEX_DEST}/"
echo "    synced."
echo
echo "  Next steps (Codex):"
echo "    1. Restart Codex (or reload plugins) to pick up ${PLUGIN_NAME}."
echo "    2. Verify: the plugin's skills appear (e.g. invoke plugin-audit)."
echo

# ---- Claude Code ---------------------------------------------------------
echo "==> Claude Code: add this repo as a marketplace (do NOT hand-copy the cache)"
if [ -f "${REPO_ROOT}/.claude-plugin/marketplace.json" ]; then
  echo "    marketplace manifest: ${REPO_ROOT}/.claude-plugin/marketplace.json"
else
  echo "    NOTE: ${REPO_ROOT}/.claude-plugin/marketplace.json not found yet"
  echo "          (it is created by the rebuild); the commands below still apply."
fi
echo
echo "  Next steps (Claude Code) - run inside an interactive Claude session:"
echo "    /plugin marketplace add ${REPO_ROOT}"
echo "    /plugin install ${PLUGIN_NAME}@${PLUGIN_NAME}"
echo
echo "  Already installed? Refresh it:"
echo "    /plugin marketplace update ${PLUGIN_NAME}"
echo
echo "Done. Codex synced to disk; Claude Code via the marketplace commands above."
