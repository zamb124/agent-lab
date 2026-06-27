#!/usr/bin/env bash
set -euo pipefail

# Smoke-check после публикации semver release HumanitecAgent.
# Использование:
#   FRONTEND_BASE_URL=https://example.com ./scripts/agent_release_tag_smoke.sh

FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-http://127.0.0.1:9004}"

echo "Checking releases status..."
curl -fsS "${FRONTEND_BASE_URL}/frontend/api/agent/releases/status" | uv run python -c "import json,sys; b=json.load(sys.stdin); assert b.get('ready') is True, b"

echo "Checking download redirect..."
curl -fsSI "${FRONTEND_BASE_URL}/frontend/api/agent/download/macos-arm64" | rg -i '^location:'

echo "HumanitecAgent release smoke OK"
