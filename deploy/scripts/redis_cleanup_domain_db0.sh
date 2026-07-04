#!/usr/bin/env bash
# Одноразовая очистка легаси-ключей на db0 (DATABASE__REDIS_URL).
#
# Удаляет:
#   - flows:workflow_projection:* (disposable cache; источник истины — Postgres ledger)
#   - platform_schedules:* на db0 (orphan; scheduler живёт на db1)
#
# Запуск:
#   DRY_RUN=1 bash deploy/scripts/redis_cleanup_domain_db0.sh   # только подсчёт
#   bash deploy/scripts/redis_cleanup_domain_db0.sh             # apply

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

log_section "Redis db0 legacy cleanup"

PLATFORM_NS="${PLATFORM_NS:-platform}"
REDIS_POD="${REDIS_POD:-redis-0}"
REDIS_DB="${REDIS_DB:-0}"
DRY_RUN="${DRY_RUN:-0}"
BATCH_SIZE="${BATCH_SIZE:-500}"

if [ -z "${KUBECTL:-}" ]; then
  if command -v microk8s >/dev/null 2>&1; then
    KUBECTL="microk8s kubectl"
  elif command -v kubectl >/dev/null 2>&1; then
    KUBECTL="kubectl"
  else
    log_error "Нужен kubectl или microk8s"
    exit 1
  fi
fi

check_step "redis pod Running" \
  "$KUBECTL get pod -n \"$PLATFORM_NS\" \"$REDIS_POD\" -o jsonpath='{.status.phase}' | grep -qx Running"

_cleanup_pattern() {
  local pattern="$1"
  local label="$2"
  log_info "Pattern: ${pattern} (${label})"

  if [ "$DRY_RUN" = "1" ]; then
    COUNT=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- \
      redis-cli -n "$REDIS_DB" --scan --pattern "$pattern" | wc -l | tr -d ' ')
    log_info "DRY_RUN: would delete ${COUNT} keys"
    $KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- \
      redis-cli -n "$REDIS_DB" --scan --pattern "$pattern" | head -10
    return 0
  fi

  DELETED=0
  while true; do
    BATCH=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- \
      redis-cli -n "$REDIS_DB" --scan --pattern "$pattern" | head -"${BATCH_SIZE}")
    if [ -z "$BATCH" ]; then
      break
    fi
    # shellcheck disable=SC2086
    $KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- redis-cli -n "$REDIS_DB" DEL $BATCH >/dev/null
    BATCH_COUNT=$(echo "$BATCH" | wc -l | tr -d ' ')
    DELETED=$((DELETED + BATCH_COUNT))
    log_do "deleted batch ${BATCH_COUNT} (${label}), total=${DELETED}"
  done
  log_ok "${label}: deleted ${DELETED} keys"
}

_cleanup_pattern 'flows:workflow_projection:*' "workflow_projection"
_cleanup_pattern 'platform_schedules:*' "orphan_platform_schedules_db0"

log_ok "db0 cleanup finished (DRY_RUN=${DRY_RUN})"
