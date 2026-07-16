#!/bin/sh
# Entrypoint claude-context: single writer behind mcp-proxy.
# BACKGROUND_SYNC=true — автосинк merkle→Milvus; полный wipe только через force reindex.
set -eu

: "${MCP_API_KEY:?MCP_API_KEY is required}"
: "${REPO_ROOT:?REPO_ROOT is required}"
: "${OLLAMA_HOST:=http://host.docker.internal:11434}"
: "${MILVUS_ADDRESS:=milvus:19530}"
: "${EMBEDDING_PROVIDER:=Ollama}"
: "${EMBEDDING_MODEL:=nomic-embed-text}"
: "${EMBEDDING_DIMENSION:=768}"
: "${EMBEDDING_BATCH_SIZE:=2}"
: "${HYBRID_MODE:=true}"
: "${CLAUDE_CONTEXT_BACKGROUND_SYNC:=true}"
: "${CLAUDE_CONTEXT_TRIGGER_WATCHER:=true}"
: "${CUSTOM_IGNORE_PATTERNS:=.search-comparison/**,.cursor/debug-*.log,documentation-dist/**,artifacts/**,test-results/**,*.map}"

export EMBEDDING_PROVIDER EMBEDDING_MODEL EMBEDDING_DIMENSION EMBEDDING_BATCH_SIZE
export OLLAMA_HOST MILVUS_ADDRESS HYBRID_MODE
export CLAUDE_CONTEXT_BACKGROUND_SYNC CLAUDE_CONTEXT_TRIGGER_WATCHER
export CUSTOM_IGNORE_PATTERNS
# Совместимость: некоторые сборки читают OLLAMA_MODEL вместо EMBEDDING_MODEL.
export OLLAMA_MODEL="${OLLAMA_MODEL:-$EMBEDDING_MODEL}"

mkdir -p /data/.context
cd "$REPO_ROOT"

exec mcp-proxy \
  --host 0.0.0.0 \
  --port 9752 \
  --apiKey "$MCP_API_KEY" \
  --corsAddAllowedHeader X-API-Key \
  --server stream \
  --streamEndpoint /mcp \
  --requestTimeout 600000 \
  --connectionTimeout 120000 \
  --keepAliveTimeout 300000 \
  --gracefulShutdownTimeout 15000 \
  -- \
  claude-context-mcp
