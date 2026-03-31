#!/usr/bin/env bash
set -euo pipefail
# Инициализация проекта Bubblewrap TWA в mobile/android/twa-project
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${TWA_PROJECT_DIR:-$ROOT/android/twa-project}"
MANIFEST="${PWA_MANIFEST_URL:-}"
if [[ -z "$MANIFEST" ]] && [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
  MANIFEST="${PWA_MANIFEST_URL:-}"
fi
if [[ -z "$MANIFEST" ]]; then
  echo "Задайте PWA_MANIFEST_URL (например https://humanitec.ru/manifest.json)" >&2
  exit 1
fi
mkdir -p "$OUT"
cd "$OUT"
exec npx bubblewrap init --manifest="$MANIFEST"
