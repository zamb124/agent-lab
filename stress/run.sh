#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${SERVICE:-flows}"
PROFILE="${PROFILE:-${STRESS_PROFILE:-local}}"
URL="${URL:-${STRESS_URL:-}}"
TOKEN="${TOKEN:-${STRESS_TOKEN:-}}"
RESULTS_DIR="${RESULTS_DIR:-${STRESS_RESULTS_DIR:-$ROOT_DIR/stress/results}}"
RPS="${RPS:-${STRESS_RPS:-}}"
USER_PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-}"
USER_MAX_VUS="${MAX_VUS:-}"

if [[ -t 0 && -z "${CI:-}" && -z "${STRESS_NON_INTERACTIVE:-}" ]]; then
  if [[ -z "$URL" ]]; then
    read -r -p "Stress URL [http://localhost:8001]: " URL
    URL="${URL:-http://localhost:8001}"
  fi
  if [[ -z "$TOKEN" ]]; then
    read -r -s -p "API token (Enter for no token): " TOKEN
    echo ""
  fi
else
  URL="${URL:-http://localhost:8001}"
fi

case "$PROFILE" in
  smoke)
    RATE="${RATE:-1}"
    DURATION="${DURATION:-20s}"
    PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-5}"
    MAX_VUS="${MAX_VUS:-20}"
    ;;
  local)
    RATE="${RATE:-5}"
    DURATION="${DURATION:-2m}"
    PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-20}"
    MAX_VUS="${MAX_VUS:-100}"
    ;;
  hard)
    RATE="${RATE:-25}"
    DURATION="${DURATION:-5m}"
    PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-100}"
    MAX_VUS="${MAX_VUS:-500}"
    ;;
  prod)
    RATE="${RATE:-10}"
    DURATION="${DURATION:-5m}"
    PRE_ALLOCATED_VUS="${PRE_ALLOCATED_VUS:-50}"
    MAX_VUS="${MAX_VUS:-250}"
    ;;
  *)
    echo "Unknown PROFILE=$PROFILE. Use smoke, local, hard, or prod." >&2
    exit 2
    ;;
esac

if [[ -n "$RPS" ]]; then
  if [[ ! "$RPS" =~ ^[0-9]+$ ]] || [[ "$RPS" -lt 1 ]]; then
    echo "RPS must be a positive integer, got: $RPS" >&2
    exit 2
  fi
  RATE="$RPS"
  if [[ -z "$USER_PRE_ALLOCATED_VUS" ]]; then
    PRE_ALLOCATED_VUS=$(( RPS < 20 ? 20 : RPS * 2 ))
  fi
  if [[ -z "$USER_MAX_VUS" ]]; then
    MAX_VUS=$(( RPS < 20 ? 100 : RPS * 5 ))
  fi
fi

SCRIPT="$ROOT_DIR/stress/services/$SERVICE.js"
if [[ ! -f "$SCRIPT" ]]; then
  echo "Stress service script not found: $SCRIPT" >&2
  exit 2
fi

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is required. Install Grafana k6 and rerun make stress." >&2
  exit 127
fi

mkdir -p "$RESULTS_DIR"

export STRESS_SERVICE="$SERVICE"
export STRESS_PROFILE="$PROFILE"
export STRESS_URL="$URL"
export STRESS_TOKEN="$TOKEN"
export STRESS_RESULTS_DIR="$RESULTS_DIR"
export STRESS_RATE="$RATE"
export STRESS_RPS="$RPS"
export STRESS_DURATION="$DURATION"
export STRESS_PRE_ALLOCATED_VUS="$PRE_ALLOCATED_VUS"
export STRESS_MAX_VUS="$MAX_VUS"

echo "Stress run"
echo "  service: $SERVICE"
echo "  profile: $PROFILE"
echo "  url:     $URL"
if [[ -n "$TOKEN" ]]; then
  echo "  token:   provided"
else
  echo "  token:   empty"
fi
echo "  rate:    $RATE rps"
echo "  time:    $DURATION"
echo "  vus:     $PRE_ALLOCATED_VUS-$MAX_VUS"
echo "  results: $RESULTS_DIR"

if [[ "${DRY_RUN:-${STRESS_DRY_RUN:-}}" == "1" || "${DRY_RUN:-${STRESS_DRY_RUN:-}}" == "true" ]]; then
  exit 0
fi

k6 run "$SCRIPT"

echo ""
echo "Reports:"
echo "  $RESULTS_DIR/report.md"
echo "  $RESULTS_DIR/report.html"
echo "  $RESULTS_DIR/summary.json"
