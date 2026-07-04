#!/usr/bin/env bash
# Одноразовый XTRIM TaskIQ streams на db1 (TASKS__BROKER_URL).
#
# Политика (агрессивная):
#   search=50000, idle=20000, crm=20000, rag=20000, flows_worker=10000
#
# Запуск:
#   DRY_RUN=1 bash deploy/scripts/redis_trim_taskiq_streams.sh
#   bash deploy/scripts/redis_trim_taskiq_streams.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

log_section "TaskIQ stream XTRIM (db1)"

PLATFORM_NS="${PLATFORM_NS:-platform}"
REDIS_POD="${REDIS_POD:-redis-0}"
REDIS_DB="${REDIS_DB:-1}"
DRY_RUN="${DRY_RUN:-0}"

# stream_name maxlen (bash 3 compatible)
STREAMS="search:50000 idle:20000 crm:20000 rag:20000 flows_worker:10000"

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

log_info "Memory before:"
$KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- redis-cli INFO memory | grep used_memory_human || true

for entry in $STREAMS; do
  stream="${entry%%:*}"
  maxlen="${entry##*:}"
  before=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- redis-cli -n "$REDIS_DB" XLEN "$stream" 2>/dev/null || echo 0)
  log_info "${stream}: XLEN before=${before}, target maxlen≈${maxlen}"
  if [ "$DRY_RUN" = "1" ]; then
    log_skip "DRY_RUN: skip XTRIM ${stream}"
    continue
  fi
  removed=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- \
    redis-cli -n "$REDIS_DB" XTRIM "$stream" MAXLEN "$maxlen")
  log_ok "${stream}: XTRIM removed≈${removed} entries"
  now=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- redis-cli -n "$REDIS_DB" XLEN "$stream" 2>/dev/null || echo 0)
  log_info "${stream}: XLEN after=${now}"
done

log_info "Memory after:"
$KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- redis-cli INFO memory | grep used_memory_human || true

log_ok "TaskIQ stream trim finished (DRY_RUN=${DRY_RUN})"
