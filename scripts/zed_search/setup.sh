#!/usr/bin/env bash
# LEGACY: host Ollama + old Milvus compose.
# Канон: Docker Compose — bash scripts/zed_search/compose.sh up
echo "[zed-search] setup.sh устарел. Перенаправляю на Compose..."
exec bash "$(cd "$(dirname "$0")" && pwd)/compose.sh" up "$@"
