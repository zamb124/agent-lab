#!/usr/bin/env bash
# Load-test zed-search stack: alternate CBM + Claude-context + make zed-search-check
set -euo pipefail

REPO="/Users/sombrero/power/agent-lab"
COMPOSE_FILE="$REPO/scripts/zed_search/docker/docker-compose.yml"
cd "$REPO"

# Load MCP_API_KEY without printing
set -a
# shellcheck disable=SC1090
source <(docker compose -f "$COMPOSE_FILE" exec -T cbm printenv MCP_API_KEY | sed 's/^/MCP_API_KEY=/')
set +a

PROJECT="Users-sombrero-power-agent-lab"
MCP="scripts/zed_search/mcp_http.py"
CBM="http://127.0.0.1:9751/mcp"
CLAUDE="http://127.0.0.1:9752/mcp"

CONTAINERS=(zed-search-cbm zed-search-claude-context zed-search-milvus)
if [[ "${OLLAMA_MODE:-metal}" == "docker" ]]; then
  CONTAINERS+=(zed-search-ollama)
fi
DURATION_S=180
INTERVAL_S=15
START_TS=$(date +%s)
END_TS=$((START_TS + DURATION_S))
ITER=0

RESULTS_FILE=$(mktemp /tmp/zed-search-loadtest-XXXXXX.tsv)
echo -e "iter\ttimestamp\tcheck_exit\tcbm_list\tcbm_search\tclaude_search\tcbm_restarts\tclaude_restarts\tcpu_mem" > "$RESULTS_FILE"

get_restart_count() {
  local name=$1
  docker inspect --format='{{.RestartCount}}' "$name" 2>/dev/null || echo "NA"
}

run_mcp() {
  local url=$1 tool=$2 args=$3
  local out rc
  out=$(uv run python "$MCP" --url "$url" --api-key "$MCP_API_KEY" --timeout 120 call "$tool" "$args" 2>&1) && rc=0 || rc=$?
  # Summarize output without dumping full results
  local summary
  if [[ $rc -eq 0 ]]; then
    local lines
    lines=$(echo "$out" | wc -l | tr -d ' ')
    local chars
    chars=${#out}
    summary="ok lines=${lines} chars=${chars}"
  else
    summary="FAIL rc=${rc} $(echo "$out" | head -1 | cut -c1-120)"
  fi
  echo "$rc|$summary"
}

echo "=== zed-search load test start $(date -Iseconds) duration=${DURATION_S}s interval=${INTERVAL_S}s ==="

while [[ $(date +%s) -lt $END_TS ]]; do
  ITER=$((ITER + 1))
  TS=$(date -Iseconds)
  echo ""
  echo "--- iteration $ITER @ $TS ---"

  # 1. make zed-search-check
  check_out=$(mktemp)
  check_rc=0
  make zed-search-check >"$check_out" 2>&1 || check_rc=$?
  check_summary=$(grep -E '\[zed-search-check\]|OK|FAIL|WARN' "$check_out" | tail -3 | tr '\n' '; ')
  rm -f "$check_out"
  echo "  check: exit=$check_rc $check_summary"

  # 2. CBM list_projects
  cbm_list=$(run_mcp "$CBM" list_projects '{}')
  cbm_list_rc=${cbm_list%%|*}
  cbm_list_sum=${cbm_list#*|}
  echo "  cbm list_projects: $cbm_list_sum"

  # 3. CBM search_graph
  cbm_search=$(run_mcp "$CBM" search_graph "{\"project\":\"$PROJECT\",\"query\":\"EventBus\",\"limit\":50}")
  cbm_search_rc=${cbm_search%%|*}
  cbm_search_sum=${cbm_search#*|}
  echo "  cbm search_graph: $cbm_search_sum"

  # 4. Claude search_code
  claude_search=$(run_mcp "$CLAUDE" search_code "{\"path\":\"$REPO\",\"query\":\"event bus factory\",\"limit\":5}")
  claude_search_rc=${claude_search%%|*}
  claude_search_sum=${claude_search#*|}
  echo "  claude search_code: $claude_search_sum"

  # 5. docker stats
  stats_line=$(docker stats --no-stream --format "{{.Name}}: CPU={{.CPUPerc}} MEM={{.MemUsage}}" "${CONTAINERS[@]}" 2>/dev/null | tr '\n' ' | ')
  echo "  stats: $stats_line"

  # 6. RestartCount
  cbm_restarts=$(get_restart_count zed-search-cbm)
  claude_restarts=$(get_restart_count zed-search-claude-context)
  echo "  restarts: cbm=$cbm_restarts claude=$claude_restarts"

  echo -e "$ITER\t$TS\t$check_rc\t$cbm_list_rc\t$cbm_search_rc\t$claude_search_rc\t$cbm_restarts\t$claude_restarts\t$stats_line" >> "$RESULTS_FILE"

  remaining=$((END_TS - $(date +%s)))
  if [[ $remaining -le 0 ]]; then
    break
  fi
  sleep_s=$INTERVAL_S
  if [[ $remaining -lt $sleep_s ]]; then
    sleep_s=$remaining
  fi
  sleep "$sleep_s"
done

echo ""
echo "=== load test complete $(date -Iseconds) iterations=$ITER ==="
echo "RESULTS_FILE=$RESULTS_FILE"
cat "$RESULTS_FILE"
