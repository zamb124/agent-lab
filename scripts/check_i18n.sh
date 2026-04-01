#!/usr/bin/env bash
# Проверка JSON переводов: парсинг и парность ru/en по именам файлов (кроме _prefix).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RU="$ROOT/core/i18n/translations/ru"
EN="$ROOT/core/i18n/translations/en"

if [[ ! -d "$RU" ]] || [[ ! -d "$EN" ]]; then
  echo "check_i18n: directories missing: $RU / $EN" >&2
  exit 1
fi

while IFS= read -r -d '' f; do
  base=$(basename "$f")
  [[ "$base" == _* ]] && continue
  uv run python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$f"
done < <(find "$RU" -maxdepth 1 -name '*.json' -print0)

while IFS= read -r -d '' f; do
  base=$(basename "$f")
  [[ "$base" == _* ]] && continue
  uv run python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$f"
done < <(find "$EN" -maxdepth 1 -name '*.json' -print0)

while IFS= read -r -d '' f; do
  base=$(basename "$f")
  [[ "$base" == _* ]] && continue
  other="$EN/$base"
  if [[ ! -f "$other" ]]; then
    echo "check_i18n: missing EN counterpart for ru/$base" >&2
    exit 1
  fi
done < <(find "$RU" -maxdepth 1 -name '*.json' -print0)

while IFS= read -r -d '' f; do
  base=$(basename "$f")
  [[ "$base" == _* ]] && continue
  other="$RU/$base"
  if [[ ! -f "$other" ]]; then
    echo "check_i18n: missing RU counterpart for en/$base" >&2
    exit 1
  fi
done < <(find "$EN" -maxdepth 1 -name '*.json' -print0)

echo "check_i18n: OK"
