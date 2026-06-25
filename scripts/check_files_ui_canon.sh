#!/usr/bin/env bash
# CI gate: UI uploads only via platform/file_create; no per-service file_upload ops in apps.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

forbidden_ops=(
  "sync/file_upload"
  "flows/file_upload"
  "crm/file_upload"
  "worktracker/file_upload"
  "rag/file_upload"
)

for op in "${forbidden_ops[@]}"; do
  if rg -q "name: ['\"]${op}['\"]" apps/ 2>/dev/null; then
    echo "check_files_ui_canon: forbidden factory name ${op} in apps/" >&2
    fail=1
  fi
done

if ! rg -q "platform/file_create" core/frontend/static/lib/events/factories/platform-file-create.js 2>/dev/null; then
  echo "check_files_ui_canon: platform-file-create.js must define platform/file_create" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "check_files_ui_canon: FAIL" >&2
  exit 1
fi

echo "check_files_ui_canon: OK"
