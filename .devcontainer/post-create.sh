#!/usr/bin/env bash
set -euo pipefail

echo "==> Dev container post-create"

# Safety net if initializeCommand was skipped (e.g. non-Dev-Containers workflows).
bash "$(dirname "${BASH_SOURCE[0]}")/ensure-env.sh"

# https://docs.graphify.com/installation
# https://docs.graphify.com/integrations/cursor
echo "==> Installing Graphify"
uv tool install "graphifyy[mcp]"
graphify install --project --platform cursor

echo "==> Dev container ready"
