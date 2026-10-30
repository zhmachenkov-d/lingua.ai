#!/usr/bin/env bash
# Soft mutation gate for apps/web (Stryker). Always exits 0 after writing summary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB_DIR="$ROOT/apps/web"
OUT_DIR="$ROOT/_bmad-output/quality/mutation"
BASELINE="$ROOT/quality/mutation/web-baseline.json"
MODE="auto"
BASE_REF=""

usage() {
  cat <<'EOF'
Usage: run_mutation_web.sh [--full|--pr] [--base <git-ref>]

  --full   Full mutate scope (no --since).
  --pr     Diff-scoped via Stryker --since (default on PR CI).
  --base   Git ref for --since (default: origin/main).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) MODE="full"; shift ;;
    --pr) MODE="pr"; shift ;;
    --base) BASE_REF="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$BASE_REF" ]]; then
  BASE_REF="origin/main"
fi

mkdir -p "$OUT_DIR"
cd "$WEB_DIR"

STRYKER_ARGS=(run)
if [[ "$MODE" == "full" ]]; then
  :
elif [[ "$MODE" == "pr" ]] || [[ "$MODE" == "auto" && "${GITHUB_EVENT_NAME:-}" == "pull_request" ]]; then
  STRYKER_ARGS+=(--since "$BASE_REF")
fi

TOOL_EXIT=0
set +e
npx stryker "${STRYKER_ARGS[@]}"
TOOL_EXIT=$?
set -e

REPORT="$WEB_DIR/reports/mutation/mutation.json"
if [[ ! -f "$REPORT" ]]; then
  mkdir -p "$WEB_DIR/reports/mutation"
  echo '{"files":{},"schemaVersion":"1.0"}' >"$REPORT"
  if [[ "$TOOL_EXIT" -eq 0 ]]; then
    TOOL_EXIT=1
  fi
fi

# Copy raw report next to normalized summary for artifacts.
cp -f "$REPORT" "$OUT_DIR/web-stryker.json"

python3 "$ROOT/scripts/quality/mutation_report.py" \
  --stack web \
  --input "$REPORT" \
  --baseline "$BASELINE" \
  --out "$OUT_DIR/web.json" \
  --tool-exit "$TOOL_EXIT" \
  --project-root "$ROOT"

exit 0
