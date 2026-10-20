#!/usr/bin/env bash
set -euo pipefail

echo "Installing uv..."

VERSION="${VERSION:-latest}"

if ! command -v curl >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends curl ca-certificates
    rm -rf /var/lib/apt/lists/*
  else
    echo "error: curl is required to install uv" >&2
    exit 1
  fi
fi

INSTALL_URL="https://astral.sh/uv/install.sh"
if [[ "${VERSION}" != "latest" ]]; then
  INSTALL_URL="https://astral.sh/uv/${VERSION}/install.sh"
fi

curl -LsSf "${INSTALL_URL}" | env UV_UNMANAGED_INSTALL="/usr/local/bin" sh

uv --version
