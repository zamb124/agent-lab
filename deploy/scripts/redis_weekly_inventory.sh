#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT="${REPO_ROOT}/deploy/scripts/redis_inventory_latest.txt"

bash "$SCRIPT_DIR/redis_key_inventory.sh" | tee "$OUT"
log_ok "Inventory saved to ${OUT}"
