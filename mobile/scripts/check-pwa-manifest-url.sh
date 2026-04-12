#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${PWA_MANIFEST_URL:-}"
if [[ -z "$URL" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/.env"
    set +a
  fi
  URL="${PWA_MANIFEST_URL:-}"
fi
if [[ -z "$URL" ]]; then
  echo "Задайте PWA_MANIFEST_URL или создайте mobile/.env из config/env.example" >&2
  exit 1
fi
curl -fsS -o /dev/null --head "$URL"
echo "OK: $URL"
