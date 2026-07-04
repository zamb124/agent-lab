#!/usr/bin/env bash
# Инвентаризация ключей Redis (db0 доменный кэш, db1 TaskIQ broker).
# Идемпотентен: только чтение, без изменений в кластере.
#
# Запуск:
#   bash deploy/scripts/redis_key_inventory.sh
#   PLATFORM_NS=platform REDIS_POD=redis-0 bash deploy/scripts/redis_key_inventory.sh
#
# Требует: kubectl (или microk8s), pod redis-0 Running в namespace platform.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

log_section "Redis key inventory"

if [ -z "$KUBECTL" ]; then
  log_error "Нужен kubectl или microk8s"
  exit 1
fi

PLATFORM_NS="${PLATFORM_NS:-platform}"
REDIS_POD="${REDIS_POD:-redis-0}"

check_step "redis pod Running" \
  "$KUBECTL get pod -n \"$PLATFORM_NS\" \"$REDIS_POD\" -o jsonpath='{.status.phase}' | grep -qx Running"

export PLATFORM_NS REDIS_POD KUBECTL
cd "$REPO_ROOT"
uv run python deploy/scripts/redis_key_inventory.py

print_summary
