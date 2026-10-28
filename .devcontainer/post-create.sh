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

echo "==> Dev container ready"
