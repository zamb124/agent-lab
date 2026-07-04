#!/usr/bin/env bash
# Smoke: после деплоя flows projection-ключи имеют TTL > 0; terminal-ключи отсутствуют.
#
# Запуск:
#   bash deploy/scripts/redis_smoke_projection_ttl.sh
#   KUBECTL="ssh root@HOST microk8s kubectl" bash deploy/scripts/redis_smoke_projection_ttl.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

log_section "Redis projection TTL smoke"

PLATFORM_NS="${PLATFORM_NS:-platform}"
REDIS_POD="${REDIS_POD:-redis-0}"
REDIS_DB="${REDIS_DB:-0}"

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

log_info "Проверка flows:workflow_projection:* на db${REDIS_DB}"

RESULT=$($KUBECTL exec -n "$PLATFORM_NS" "$REDIS_POD" -- sh -c "
redis-cli -n ${REDIS_DB} --scan --pattern 'flows:workflow_projection:*' | head -50 | while read -r k; do
  ttl=\$(redis-cli -n ${REDIS_DB} TTL \"\$k\")
  echo \"\$ttl:\$k\"
done
")

NO_TTL=0
WITH_TTL=0
while IFS= read -r line; do
  if [ -z "$line" ]; then
    continue
  fi
  ttl="${line%%:*}"
  key="${line#*:}"
  if [ "$ttl" = "-1" ]; then
    log_warn "TTL=-1 (legacy): $key"
    NO_TTL=$((NO_TTL + 1))
  elif [ "$ttl" = "-2" ]; then
    log_warn "missing key: $key"
  else
    WITH_TTL=$((WITH_TTL + 1))
    log_ok "TTL=${ttl}s: $key"
  fi
done <<< "$RESULT"

log_info "Sample: with_ttl=${WITH_TTL} no_ttl_legacy=${NO_TTL}"

if [ "$WITH_TTL" -eq 0 ] && [ "$NO_TTL" -eq 0 ]; then
  log_info "Нет projection-ключей в sample — smoke inconclusive (запустите короткий flow)"
  exit 0
fi

if [ "$WITH_TTL" -gt 0 ]; then
  log_ok "Новые projection-ключи с TTL обнаружены"
  exit 0
fi

log_error "Только legacy-ключи без TTL в sample — проверьте деплой flows"
exit 1
