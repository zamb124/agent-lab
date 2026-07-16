#!/bin/sh
# Entrypoint CBM: safe writers (auto_watch=false) + mcp-proxy HTTP.
set -eu

: "${CBM_CACHE_DIR:=/cache}"
: "${CBM_AUTO_INDEX:=true}"
: "${CBM_AUTO_WATCH:=false}"
: "${MCP_API_KEY:?MCP_API_KEY is required}"
: "${REPO_ROOT:?REPO_ROOT is required}"

mkdir -p "$CBM_CACHE_DIR"
export CBM_CACHE_DIR
export CBM_ALLOWED_ROOT="$REPO_ROOT"
export CBM_SQLITE_MMAP_SIZE="${CBM_SQLITE_MMAP_SIZE:-0}"
export CBM_LOG_LEVEL="${CBM_LOG_LEVEL:-info}"
export CBM_MEM_BUDGET_MB="${CBM_MEM_BUDGET_MB:-8192}"
export CBM_WORKERS="${CBM_WORKERS:-4}"

# Конфиг пишется в CBM_CACHE_DIR — переживает рестарт контейнера.
codebase-memory-mcp config set auto_index "$CBM_AUTO_INDEX" >/dev/null
codebase-memory-mcp config set auto_watch "$CBM_AUTO_WATCH" >/dev/null

cd "$REPO_ROOT"

exec mcp-proxy \
  --host 0.0.0.0 \
  --port 9751 \
  --apiKey "$MCP_API_KEY" \
  --corsAddAllowedHeader X-API-Key \
  --server stream \
  --streamEndpoint /mcp \
  --requestTimeout 600000 \
  --connectionTimeout 120000 \
  --keepAliveTimeout 300000 \
  --gracefulShutdownTimeout 15000 \
  -- \
  codebase-memory-mcp
