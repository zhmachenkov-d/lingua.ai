#!/usr/bin/env bash
set -euo pipefail

echo "==> Dev container post-create"

# Safety net if initializeCommand was skipped (e.g. non-Dev-Containers workflows).
bash "$(dirname "${BASH_SOURCE[0]}")/ensure-env.sh"

echo "==> Installing tmux"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tmux

# https://cursor.com/docs/cli/installation
echo "==> Installing Cursor CLI"
curl https://cursor.com/install -fsS | bash
export PATH="${HOME}/.local/bin:${PATH}"
agent --version

# https://docs.graphify.com/installation
# https://docs.graphify.com/integrations/cursor

# AST quality gate binaries (ast-grep / ast-metrics / revet) — pinned in
# scripts/quality/versions.env; same installer CI uses.
echo "==> Installing AST quality tools"
bash scripts/quality/install_tools.sh
export PATH="${HOME}/.local/bin:${PATH}"

echo "==> Dev container ready"
