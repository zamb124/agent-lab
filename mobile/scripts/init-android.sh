#!/usr/bin/env bash
set -euo pipefail
# Первичная генерация Capacitor Android проекта в mobile/android.
# Идемпотентно: если каталог уже есть, делает npx cap sync.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d "$ROOT/android" ]]; then
  echo "android/ уже существует — выполняется npx cap sync android"
  exec npx cap sync android
fi

exec npx cap add android
