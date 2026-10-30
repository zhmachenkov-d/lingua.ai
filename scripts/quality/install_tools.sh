#!/usr/bin/env bash
# Install pinned ast-grep, ast-metrics, and revet binaries into PREFIX (default: ~/.local/bin).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/versions.env"

PREFIX="${QUALITY_TOOLS_PREFIX:-${HOME}/.local/bin}"
mkdir -p "${PREFIX}"

os="$(uname -s)"
arch="$(uname -m)"

case "${os}-${arch}" in
  Linux-x86_64)
    SG_ASSET="app-x86_64-unknown-linux-gnu.zip"
    AM_ASSET="ast-metrics_Linux_x86_64"
    RV_ASSET="revet-linux-x64"
    ;;
  Linux-aarch64|Linux-arm64)
    SG_ASSET="app-aarch64-unknown-linux-gnu.zip"
    AM_ASSET="ast-metrics_Linux_arm64"
    RV_ASSET="revet-linux-arm64"
    ;;
  Darwin-x86_64)
    SG_ASSET="app-x86_64-apple-darwin.zip"
    AM_ASSET="ast-metrics_Darwin_x86_64"
    RV_ASSET="revet-darwin-x64"
    ;;
  Darwin-arm64)
    SG_ASSET="app-aarch64-apple-darwin.zip"
    AM_ASSET="ast-metrics_Darwin_arm64"
    RV_ASSET="revet-darwin-arm64"
    ;;
  *)
    echo "unsupported platform: ${os}-${arch}" >&2
    exit 1
    ;;
esac

tmpdir="$(mktemp -d)"
cleanup() { rm -rf "${tmpdir}"; }
trap cleanup EXIT

echo "installing ast-grep ${AST_GREP_VERSION} → ${PREFIX}/ast-grep"
curl -fsSL \
  "https://github.com/ast-grep/ast-grep/releases/download/${AST_GREP_VERSION}/${SG_ASSET}" \
  -o "${tmpdir}/ast-grep.zip"
unzip -qo "${tmpdir}/ast-grep.zip" -d "${tmpdir}/ast-grep"
# Release zip usually contains `sg` and/or `ast-grep`.
if [[ -x "${tmpdir}/ast-grep/ast-grep" ]]; then
  install -m 755 "${tmpdir}/ast-grep/ast-grep" "${PREFIX}/ast-grep"
elif [[ -x "${tmpdir}/ast-grep/sg" ]]; then
  install -m 755 "${tmpdir}/ast-grep/sg" "${PREFIX}/ast-grep"
else
  found="$(find "${tmpdir}/ast-grep" -type f \( -name ast-grep -o -name sg \) | head -n1 || true)"
  if [[ -z "${found}" ]]; then
    echo "ast-grep binary not found in ${SG_ASSET}" >&2
    ls -laR "${tmpdir}/ast-grep" >&2 || true
    exit 1
  fi
  install -m 755 "${found}" "${PREFIX}/ast-grep"
fi

echo "installing ast-metrics ${AST_METRICS_VERSION} → ${PREFIX}/ast-metrics"
curl -fsSL \
  "https://github.com/ast-metrics/ast-metrics/releases/download/${AST_METRICS_VERSION}/${AM_ASSET}" \
  -o "${PREFIX}/ast-metrics"
chmod +x "${PREFIX}/ast-metrics"

echo "installing revet ${REVET_VERSION} → ${PREFIX}/revet"
curl -fsSL \
  "https://github.com/umitkavala/revet/releases/download/${REVET_VERSION}/${RV_ASSET}" \
  -o "${PREFIX}/revet"
chmod +x "${PREFIX}/revet"

echo "installed:"
"${PREFIX}/ast-grep" --version || true
"${PREFIX}/ast-metrics" version || true
"${PREFIX}/revet" --version || true

case ":${PATH}:" in
  *":${PREFIX}:"*) ;;
  *)
    echo "note: add ${PREFIX} to PATH (export PATH=\"${PREFIX}:\$PATH\")" >&2
    ;;
esac
