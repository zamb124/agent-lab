#!/bin/sh
# Периодический incremental reindex (без wipe).
# force=true только если REINDEX_FORCE=true — иначе индексы в volume не трогаем целиком.
# REINDEX_INTERVAL_SEC=0 — idle (рекомендуемый дефолт: индексы живут в named volumes).
set -eu

INTERVAL="${REINDEX_INTERVAL_SEC:-0}"
if [ "$INTERVAL" = "0" ]; then
  echo "[zed-search-reindex] REINDEX_INTERVAL_SEC=0 — idle (кэш в volumes, полный reindex только через make zed-search-reindex)"
  while true; do sleep 3600; done
fi

REPO_ROOT="${REPO_ROOT:?}"
MCP_API_KEY="${MCP_API_KEY:?}"
CBM_URL="${CBM_URL:-http://cbm:9751/mcp}"
CLAUDE_URL="${CLAUDE_URL:-http://claude-context:9752/mcp}"
REINDEX_FORCE="${REINDEX_FORCE:-false}"

HELPER="/mcp_http.py"
if [ ! -f "$HELPER" ]; then
  echo "[zed-search-reindex] нет $HELPER — только sleep (reindex через make zed-search-reindex)"
  while true; do sleep "$INTERVAL"; done
fi

FORCE_JSON="false"
if [ "$REINDEX_FORCE" = "true" ] || [ "$REINDEX_FORCE" = "1" ]; then
  FORCE_JSON="true"
fi

echo "[zed-search-reindex] interval=${INTERVAL}s force=${FORCE_JSON} repo=$REPO_ROOT"
sleep 60
while true; do
  echo "[zed-search-reindex] $(date -u +%Y-%m-%dT%H:%M:%SZ) tick force=${FORCE_JSON}"
  # claude-context: force=false → «already indexed» / incremental, без wipe snapshot+milvus
  python3 "$HELPER" --url "$CLAUDE_URL" --api-key "$MCP_API_KEY" \
    call index_codebase "{\"path\":\"$REPO_ROOT\",\"force\":${FORCE_JSON}}" || true
  # CBM: index_repository без wipe — дописывает/обновляет граф в /cache volume
  python3 "$HELPER" --url "$CBM_URL" --api-key "$MCP_API_KEY" \
    call index_repository "{\"repo_path\":\"$REPO_ROOT\"}" || true
  sleep "$INTERVAL"
done
