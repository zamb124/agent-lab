#!/usr/bin/env bash
# Concurrent load: N "subagents" hit CBM + claude-context while reindex runs.
# Pass criterion: RestartCount does not increase; containers stay healthy.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

ENV_FILE="$REPO/scripts/zed_search/docker/.env"
MCP="$REPO/scripts/zed_search/mcp_http.py"
CBM_URL="${CBM_URL:-http://127.0.0.1:9751/mcp}"
CLAUDE_URL="${CLAUDE_URL:-http://127.0.0.1:9752/mcp}"
PROJECT="${CBM_PROJECT:-Users-sombrero-power-agent-lab}"

AGENTS="${AGENTS:-6}"
DURATION_S="${DURATION_S:-90}"
TIMEOUT_S="${TIMEOUT_S:-60}"
TRIGGER_REINDEX="${TRIGGER_REINDEX:-1}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "FAIL: no $ENV_FILE" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
: "${MCP_API_KEY:?MCP_API_KEY missing in .env}"

CONTAINERS=(zed-search-cbm zed-search-claude-context zed-search-milvus)
if [[ "${OLLAMA_MODE:-metal}" == "docker" ]]; then
  CONTAINERS+=(zed-search-ollama)
fi
WORKDIR=$(mktemp -d /tmp/zed-search-concurrent-XXXXXX)
RESULTS="$WORKDIR/results.tsv"
echo -e "agent\tcalls\tok\tfail\tlast_err" > "$RESULTS"

restart_snapshot() {
  local name out
  for name in "${CONTAINERS[@]}"; do
    out=$(docker inspect --format='{{.RestartCount}}' "$name" 2>/dev/null || echo NA)
    printf '%s=%s ' "$name" "$out"
  done
  echo
}

health_snapshot() {
  local name status health
  for name in "${CONTAINERS[@]}"; do
    status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo missing)
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$name" 2>/dev/null || echo n/a)
    printf '%s=%s/%s ' "$name" "$status" "$health"
  done
  echo
}

mcp_call() {
  local url="$1" tool="$2" args="$3"
  local tag="${AGENT_ID:-0}.$$.$RANDOM"
  local out_file="$WORKDIR/out.$tag"
  local err_file="$WORKDIR/err.$tag"
  if uv run python "$MCP" --url "$url" --api-key "$MCP_API_KEY" --timeout "$TIMEOUT_S" \
      call "$tool" "$args" >"$out_file" 2>"$err_file"; then
    return 0
  fi
  # Soft-ok: concurrent index when already indexed / in progress
  if grep -Eiq 'already indexed|already being indexed|Indexing is running|Started background indexing' \
      "$out_file" "$err_file" 2>/dev/null; then
    return 0
  fi
  LAST_MCP_ERR=$(tr '\n' ' ' <"$err_file" 2>/dev/null | cut -c1-120)
  return 1
}

agent_loop() {
  local id="$1"
  AGENT_ID="$id"
  export AGENT_ID
  local end_ts=$(( $(date +%s) + DURATION_S ))
  local ok=0 fail=0 calls=0
  local last_err=""
  local LAST_MCP_ERR=""
  local queries=(
    'EntityRepository upload_text'
    'event bus factory'
    'CRM note RAG indexing'
    'PlatformElement useResource'
    'WorkItem crm_activity'
  )
  local q_idx=0

  while [[ $(date +%s) -lt $end_ts ]]; do
    calls=$((calls + 1))
    q="${queries[$((q_idx % ${#queries[@]}))]}"
    q_idx=$((q_idx + 1))
    LAST_MCP_ERR=""

    case $((calls % 5)) in
      0)
        if mcp_call "$CLAUDE_URL" get_indexing_status "{\"path\":\"$REPO\"}"; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
          last_err="get_indexing_status:$LAST_MCP_ERR"
        fi
        ;;
      1)
        if mcp_call "$CBM_URL" list_projects '{}'; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
          last_err="list_projects:$LAST_MCP_ERR"
        fi
        ;;
      2)
        if mcp_call "$CBM_URL" search_graph "{\"project\":\"$PROJECT\",\"query\":\"$q\",\"limit\":20}"; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
          last_err="search_graph:$LAST_MCP_ERR"
        fi
        ;;
      3)
        if mcp_call "$CLAUDE_URL" search_code "{\"path\":\"$REPO\",\"query\":\"$q\",\"limit\":5}"; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
          last_err="search_code:$LAST_MCP_ERR"
        fi
        ;;
      *)
        # Subagent-like: kick non-force index (must not wipe; must not crash stack).
        if mcp_call "$CLAUDE_URL" index_codebase "{\"path\":\"$REPO\",\"force\":false}"; then
          ok=$((ok + 1))
        else
          fail=$((fail + 1))
          last_err="index_codebase:$LAST_MCP_ERR"
        fi
        ;;
    esac
  done

  # last_err may contain tabs — sanitize
  last_err=${last_err//$'\t'/ }
  echo -e "$id\t$calls\t$ok\t$fail\t$last_err" >> "$RESULTS"
}

echo "=== concurrent load start $(date -Iseconds) agents=$AGENTS duration=${DURATION_S}s ==="
echo "workdir=$WORKDIR"
BEFORE_RESTARTS=$(restart_snapshot)
BEFORE_HEALTH=$(health_snapshot)
echo "before restarts: $BEFORE_RESTARTS"
echo "before health:   $BEFORE_HEALTH"

REINDEX_PID=""
if [[ "$TRIGGER_REINDEX" == "1" ]]; then
  echo "triggering background force reindex (claude only, non-blocking start)..."
  (
    uv run python "$MCP" --url "$CLAUDE_URL" --api-key "$MCP_API_KEY" --timeout 120 \
      call index_codebase "{\"path\":\"$REPO\",\"force\":true}" \
      >"$WORKDIR/reindex.out" 2>"$WORKDIR/reindex.err" || true
  ) &
  REINDEX_PID=$!
  sleep 2
fi

PIDS=()
for i in $(seq 1 "$AGENTS"); do
  agent_loop "$i" &
  PIDS+=($!)
done

MONITOR_END=$(( $(date +%s) + DURATION_S + 5 ))
while [[ $(date +%s) -lt $MONITOR_END ]]; do
  alive=0
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive=$((alive + 1))
    fi
  done
  echo "[monitor $(date +%H:%M:%S)] agents_alive=$alive restarts=$(restart_snapshot) health=$(health_snapshot)"
  if [[ $alive -eq 0 ]]; then
    break
  fi
  sleep 10
done

for pid in "${PIDS[@]}"; do
  wait "$pid" || true
done
if [[ -n "$REINDEX_PID" ]]; then
  wait "$REINDEX_PID" || true
fi

AFTER_RESTARTS=$(restart_snapshot)
AFTER_HEALTH=$(health_snapshot)
echo ""
echo "=== agent results ==="
column -t -s $'\t' "$RESULTS" 2>/dev/null || cat "$RESULTS"

TOTAL_OK=$(awk -F'\t' 'NR>1 {s+=$3} END {print s+0}' "$RESULTS")
TOTAL_FAIL=$(awk -F'\t' 'NR>1 {s+=$4} END {print s+0}' "$RESULTS")
TOTAL_CALLS=$(awk -F'\t' 'NR>1 {s+=$2} END {print s+0}' "$RESULTS")

echo ""
echo "=== summary ==="
echo "calls=$TOTAL_CALLS ok=$TOTAL_OK fail=$TOTAL_FAIL"
echo "before restarts: $BEFORE_RESTARTS"
echo "after  restarts: $AFTER_RESTARTS"
echo "before health:   $BEFORE_HEALTH"
echo "after  health:   $AFTER_HEALTH"
echo "stats: $(docker stats --no-stream --format '{{.Name}}: CPU={{.CPUPerc}} MEM={{.MemUsage}}' "${CONTAINERS[@]}" | tr '\n' ' | ')"

# Parse restart counts (order matches CONTAINERS)
pass=1
for name in "${CONTAINERS[@]}"; do
  before=$(echo "$BEFORE_RESTARTS" | tr ' ' '\n' | awk -F= -v n="$name" '$1==n {print $2}')
  after=$(echo "$AFTER_RESTARTS" | tr ' ' '\n' | awk -F= -v n="$name" '$1==n {print $2}')
  if [[ "$before" != "NA" && "$after" != "NA" && "$after" -gt "$before" ]]; then
    echo "FAIL: $name RestartCount $before -> $after"
    pass=0
  fi
  health=$(echo "$AFTER_HEALTH" | tr ' ' '\n' | awk -F= -v n="$name" '$1==n {print $2}')
  status=${health%%/*}
  hstate=${health##*/}
  if [[ "$status" != "running" ]]; then
    echo "FAIL: $name status=$status"
    pass=0
  fi
  if [[ "$hstate" != "healthy" && "$hstate" != "n/a" ]]; then
    echo "FAIL: $name health=$hstate"
    pass=0
  fi
done

echo "RESULTS_DIR=$WORKDIR"
if [[ $pass -eq 1 ]]; then
  echo "PASS: containers survived ${AGENTS} concurrent agents for ${DURATION_S}s (no restart / unhealthy)"
  exit 0
fi
echo "FAIL: container instability under concurrent load"
exit 1
