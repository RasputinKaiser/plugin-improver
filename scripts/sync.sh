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
# Claude Code installs from a marketplace, not a hand-copied cache. If the
# `claude` CLI is present we do the add/install/update directly (idempotent);
# otherwise we print the interactive slash commands as a fallback.
echo "==> Claude Code: ${PLUGIN_NAME} marketplace"
if command -v claude >/dev/null 2>&1; then
  if claude plugin marketplace list 2>/dev/null | grep -q "${PLUGIN_NAME}"; then
    claude plugin marketplace update "${PLUGIN_NAME}" >/dev/null 2>&1 || true
    echo "    marketplace refreshed."
  else
    claude plugin marketplace add "${REPO_ROOT}" >/dev/null 2>&1 || true
    echo "    marketplace added."
  fi
  if claude plugin list 2>/dev/null | grep -q "${PLUGIN_NAME}@${PLUGIN_NAME}"; then
    claude plugin update "${PLUGIN_NAME}@${PLUGIN_NAME}" >/dev/null 2>&1 || true
    echo "    plugin updated (restart Claude Code to apply)."
  else
    claude plugin install "${PLUGIN_NAME}@${PLUGIN_NAME}" >/dev/null 2>&1 \
      && echo "    plugin installed." \
      || echo "    install failed — run: claude plugin install ${PLUGIN_NAME}@${PLUGIN_NAME}"
  fi
else
  echo "    'claude' CLI not found. In an interactive Claude session run:"
  echo "      /plugin marketplace add ${REPO_ROOT}"
  echo "      /plugin install ${PLUGIN_NAME}@${PLUGIN_NAME}   (or /plugin marketplace update ${PLUGIN_NAME})"
fi
echo
echo "Done. Codex synced to disk; Claude Code marketplace add/install/update handled above."
