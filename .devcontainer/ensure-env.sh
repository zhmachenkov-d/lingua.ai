#!/usr/bin/env bash
# Host-side: Docker --env-file requires .env before the container starts.
# Dev Containers run this via initializeCommand on the local machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
EXAMPLE="${ROOT}/.env.example"

if [[ -f "${ENV_FILE}" ]]; then
  exit 0
fi

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "error: missing ${EXAMPLE}; cannot create .env" >&2
  exit 1
fi

cp "${EXAMPLE}" "${ENV_FILE}"
echo "==> Created .env from .env.example (fill in secrets locally; never commit .env)"
