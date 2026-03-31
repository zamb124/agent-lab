#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -z "${PWA_LIGHTHOUSE_URL:-}" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/.env"
    set +a
  fi
fi
if [[ -z "${PWA_LIGHTHOUSE_URL:-}" ]]; then
  echo "Задайте PWA_LIGHTHOUSE_URL (например https://humanitec.ru/) или добавьте в mobile/.env" >&2
  exit 1
fi
export PWA_LIGHTHOUSE_URL
exec npx --no-install lhci autorun --config="$ROOT/lighthouserc.cjs"
