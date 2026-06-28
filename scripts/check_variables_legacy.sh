#!/usr/bin/env bash
# Fail CI if legacy variables patterns reappear after secrets migration.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "check_variables_legacy: need ripgrep (rg)" >&2
  exit 1
fi

ERR=0
fail() { echo "check_variables_legacy: $1" >&2; ERR=1; }

GLOB_EXCLUDES=(
  --glob '!docs/openapi/**'
  --glob '!.cursor/plans/**'
  --glob '!scripts/check_variables_legacy.sh'
  --glob '!migrations/shared/versions/*drop_legacy_variables*'
  --glob '!core/frontend/static/assets/**'
)

PATTERNS=(
  'variable_repository'
  '/flows/api/v1/variables'
  "'flows/variables'"
  '"flows/variables"'
  'VariableCreateRequest'
  'VariableResponse'
  'VariableDefinition'
  'variable_models\.py'
  'models/variabledefinition\.json'
)

for pattern in "${PATTERNS[@]}"; do
  if rg -n "${GLOB_EXCLUDES[@]}" "$pattern" core apps tests scripts mk 2>/dev/null; then
    fail "forbidden pattern: $pattern"
  fi
done

if [[ "$ERR" -ne 0 ]]; then
  echo "check_variables_legacy: FAIL" >&2
  exit 1
fi

echo "check_variables_legacy: OK"
