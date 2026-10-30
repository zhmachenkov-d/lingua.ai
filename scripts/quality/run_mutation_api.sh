#!/usr/bin/env bash
# Soft mutation gate for apps/api (mutmut). Always exits 0 after writing summary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$ROOT/apps/api"
OUT_DIR="$ROOT/_bmad-output/quality/mutation"
BASELINE="$ROOT/quality/mutation/api-baseline.json"
MODE="auto"
BASE_REF=""

usage() {
  cat <<'EOF'
Usage: run_mutation_api.sh [--full|--pr] [--base <git-ref>]

  --full   Mutate full high-value scope (ignore diff skip).
  --pr     Skip when no scoped files changed vs --base (default on PR CI).
  --base   Git ref for diff (default: origin/main).
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

mkdir -p "$OUT_DIR" "$API_DIR/contracts"
cp -f "$ROOT/apps/web/src/app/chat/max-turn-text-length.json" \
  "$API_DIR/contracts/max-turn-text-length.json"

SCOPED_PREFIXES=(
  "apps/api/app/llm/"
  "apps/api/app/router/"
  "apps/api/app/review/"
  "apps/api/app/tutor/"
  "apps/api/app/corpus/"
)

should_run=1
if [[ "$MODE" == "pr" ]] || [[ "$MODE" == "auto" && "${GITHUB_EVENT_NAME:-}" == "pull_request" ]]; then
  if git -C "$ROOT" rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    mapfile -t changed < <(git -C "$ROOT" diff --name-only "$BASE_REF"...HEAD -- 'apps/api/app/**/*.py' || true)
    matched=0
    if ((${#changed[@]} > 0)); then
      for f in "${changed[@]}"; do
        [[ -z "$f" ]] && continue
        for p in "${SCOPED_PREFIXES[@]}"; do
          if [[ "$f" == "$p"* ]]; then
            matched=1
            break
          fi
        done
        [[ "$matched" -eq 1 ]] && break
      done
    fi
    if [[ "$matched" -eq 0 ]]; then
      should_run=0
    fi
  fi
fi

cd "$API_DIR"
TOOL_EXIT=0
STATS="$API_DIR/mutants/mutmut-cicd-stats.json"

if [[ "$should_run" -eq 0 ]]; then
  mkdir -p "$API_DIR/mutants"
  cat >"$STATS" <<'EOF'
{
  "killed": 0,
  "survived": 0,
  "total": 0,
  "no_tests": 0,
  "skipped": 0,
  "suspicious": 0,
  "timeout": 0,
  "check_was_interrupted_by_user": 0,
  "segfault": 0
}
EOF
  echo "mutation api: no scoped diff vs $BASE_REF — skipping mutmut run"
else
  set +e
  CI=true uv run mutmut run
  TOOL_EXIT=$?
  set -e
  set +e
  uv run mutmut export-cicd-stats
  set -e
  if [[ ! -f "$STATS" ]]; then
    cat >"$STATS" <<'EOF'
{
  "killed": 0,
  "survived": 0,
  "total": 0,
  "no_tests": 0,
  "skipped": 0,
  "suspicious": 0,
  "timeout": 0,
  "check_was_interrupted_by_user": 0,
  "segfault": 0
}
EOF
    if [[ "$TOOL_EXIT" -eq 0 ]]; then
      TOOL_EXIT=1
    fi
  fi
fi

python3 "$ROOT/scripts/quality/mutation_report.py" \
  --stack api \
  --input "$STATS" \
  --baseline "$BASELINE" \
  --out "$OUT_DIR/api.json" \
  --tool-exit "$TOOL_EXIT" \
  --project-root "$ROOT"

# Soft gate: never fail the job from this script.
exit 0
