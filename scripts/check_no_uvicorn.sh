#!/usr/bin/env bash
# uvicorn запрещён в core/ и apps/ — HTTP-сервер платформы строго granian
# (см. core/app/server.py). CI ловит регрессии перед merge.

set -euo pipefail

cd "$(dirname "$0")/.."

matches=$(rg -n --type py '^\s*(import\s+uvicorn|from\s+uvicorn)\b' core apps || true)
if [ -n "$matches" ]; then
  echo "ERROR: запрещён import uvicorn в core/ и apps/. Используй granian (core/app/server.py)." >&2
  echo "$matches" >&2
  exit 1
fi
