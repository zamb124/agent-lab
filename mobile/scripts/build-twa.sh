#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${TWA_PROJECT_DIR:-$ROOT/android/twa-project}"
if [[ ! -d "$DIR" ]]; then
  echo "Нет каталога TWA: $DIR. Сначала: npm run twa:bootstrap" >&2
  exit 1
fi
cd "$DIR"
exec npx bubblewrap build
