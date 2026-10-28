#!/usr/bin/env bash
# Отчёт: файлы UI с кириллицей (строковые литералы — ориентир для i18n).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== apps/*/ui/**/*.ts ==="
rg -l '[а-яА-ЯёЁ]' "$ROOT/apps" --glob '**/ui/**/*.ts' 2>/dev/null | wc -l | tr -d ' '
echo "files"
rg -c '[а-яА-ЯёЁ]' "$ROOT/apps" --glob '**/ui/**/*.ts' 2>/dev/null | awk -F: '{s+=$2} END {print s " total line matches"}'
echo ""
echo "=== core/frontend/static/lib/**/*.ts ==="
rg -l '[а-яА-ЯёЁ]' "$ROOT/core/frontend/static/lib" --glob '*.ts' 2>/dev/null | wc -l | tr -d ' '
echo "files"
