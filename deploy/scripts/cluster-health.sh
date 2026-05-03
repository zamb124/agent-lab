#!/usr/bin/env bash
# Полная проверка здоровья платформы Humanitec.
# Запускать локально (с настроенным kubectl) или с master ноды.
#
# Возвращает exit 0 только если ВСЕ проверки прошли. Иначе exit 1 и список упавших.
#
# Запускается:
#   - из CI после `helm upgrade` (шаг "Verify rollout" в .github/workflows/deploy.yml);
#   - вручную: `bash deploy/scripts/cluster-health.sh` или `make k8s-health`.
#
# ENV:
#   PLATFORM_NS=platform                — namespace с подами платформы
#   APEX_HOST=humanitec.ru              — публичный апекс
#   GRAFANA_HOST=grafana.humanitec.ru   — Grafana (PUBLIC)
#   ONLYOFFICE_HOST=onlyoffice.humanitec.ru
#   LIVEKIT_HOST=livekit.humanitec.ru
#   CHECK_PUBLIC=1                      — проверить https://… через curl (требует DNS); 0 = только in-cluster

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl 2>/dev/null || require_command microk8s || exit 1

K="$KUBECTL"
APEX_HOST="${APEX_HOST:-humanitec.ru}"
GRAFANA_HOST="${GRAFANA_HOST:-grafana.humanitec.ru}"
ONLYOFFICE_HOST="${ONLYOFFICE_HOST:-onlyoffice.humanitec.ru}"
LIVEKIT_HOST="${LIVEKIT_HOST:-livekit.humanitec.ru}"
CHECK_PUBLIC="${CHECK_PUBLIC:-1}"

# Список ожидаемых деплойментов (соответствует values.yaml — applications + workers + external)
EXPECTED_DEPLOYMENTS=(
  flows frontend crm rag sync office scheduler-api voice
  flows-worker scheduler rag-worker sync-worker crm-worker idle-worker
  livekit livekit-egress onlyoffice grafana provider-litserve
)
EXPECTED_STATEFULSETS=(postgres redis loki tempo)
EXPECTED_DAEMONSETS=(coturn alloy)

log_section "Cluster Health Check"

# 1. Ноды Ready
log_section "1) Ноды кластера"
NODES_READY=$($K get nodes --no-headers 2>/dev/null | awk '$2 != "Ready" {print $1}')
if [ -z "$NODES_READY" ]; then
  log_ok "все ноды Ready"
  $K get nodes -o wide --no-headers | sed 's/^/    /'
else
  log_error "не Ready: $NODES_READY"
fi

# 2. GPU доступна на gpu-worker
log_section "2) GPU"
check_step \
  "node $GPU_NODE_NAME имеет nvidia.com/gpu в Allocatable" \
  "$K get node $GPU_NODE_NAME -o jsonpath='{.status.allocatable.nvidia\\.com/gpu}' | grep -qE '^[1-9]'"

# 3. Поды Running/Completed
log_section "3) Поды в namespace $PLATFORM_NS"
NOT_OK=$($K get pods -n "$PLATFORM_NS" --no-headers 2>/dev/null \
  | awk '$3 != "Running" && $3 != "Completed" {print $1, $3}')
if [ -z "$NOT_OK" ]; then
  log_ok "все поды Running/Completed"
else
  log_error "не Running:"
  printf '%s\n' "$NOT_OK" | sed 's/^/    /'
fi

# 4. Все ожидаемые Deployments присутствуют и avail
log_section "4) Ожидаемые Deployments"
for d in "${EXPECTED_DEPLOYMENTS[@]}"; do
  AVAIL=$($K get deployment "$d" -n "$PLATFORM_NS" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo 0)
  DESIRED=$($K get deployment "$d" -n "$PLATFORM_NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)
  if [ -n "$AVAIL" ] && [ "$AVAIL" = "$DESIRED" ] && [ "$AVAIL" != "0" ]; then
    log_ok "$d ($AVAIL/$DESIRED ready)"
  else
    __FAIL_COUNT=$((__FAIL_COUNT + 1))
    log_error "$d: available=$AVAIL desired=$DESIRED"
  fi
done

# 5. StatefulSets
log_section "5) StatefulSets"
for s in "${EXPECTED_STATEFULSETS[@]}"; do
  READY=$($K get statefulset "$s" -n "$PLATFORM_NS" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)
  DESIRED=$($K get statefulset "$s" -n "$PLATFORM_NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)
  if [ -n "$READY" ] && [ "$READY" = "$DESIRED" ] && [ "$READY" != "0" ]; then
    log_ok "$s ($READY/$DESIRED ready)"
  else
    __FAIL_COUNT=$((__FAIL_COUNT + 1))
    log_error "$s: ready=$READY desired=$DESIRED"
  fi
done

# 6. DaemonSets
log_section "6) DaemonSets"
for ds in "${EXPECTED_DAEMONSETS[@]}"; do
  READY=$($K get daemonset "$ds" -n "$PLATFORM_NS" -o jsonpath='{.status.numberReady}' 2>/dev/null || echo 0)
  DESIRED=$($K get daemonset "$ds" -n "$PLATFORM_NS" -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || echo 0)
  if [ -n "$READY" ] && [ "$READY" = "$DESIRED" ] && [ "$READY" != "0" ]; then
    log_ok "$ds ($READY/$DESIRED ready)"
  else
    __FAIL_COUNT=$((__FAIL_COUNT + 1))
    log_error "$ds: ready=$READY desired=$DESIRED"
  fi
done

# 7. PVC bound
log_section "7) PVC"
NOT_BOUND=$($K get pvc -n "$PLATFORM_NS" --no-headers 2>/dev/null \
  | awk '$2 != "Bound" {print $1, $2}')
if [ -z "$NOT_BOUND" ]; then
  log_ok "все PVC Bound"
else
  log_error "не Bound:"
  printf '%s\n' "$NOT_BOUND" | sed 's/^/    /'
fi

# 8. Ingress address
log_section "8) Ingress"
INGRESS_LIST=$($K get ingress -n "$PLATFORM_NS" --no-headers -o custom-columns=NAME:.metadata.name,HOST:.spec.rules[*].host,ADDRESS:.status.loadBalancer.ingress[*].ip 2>/dev/null)
if [ -n "$INGRESS_LIST" ]; then
  log_ok "Ingress объекты есть"
  printf '%s\n' "$INGRESS_LIST" | sed 's/^/    /'
else
  __FAIL_COUNT=$((__FAIL_COUNT + 1))
  log_error "Ingress объектов нет"
fi

# 9. TLS сертификаты cert-manager
log_section "9) Certificates"
if $K get certificate -n "$PLATFORM_NS" >/dev/null 2>&1; then
  CERT_NOT_READY=$($K get certificate -n "$PLATFORM_NS" --no-headers 2>/dev/null \
    | awk '$2 != "True" {print $1, $2}')
  if [ -z "$CERT_NOT_READY" ]; then
    log_ok "все Certificate Ready"
    $K get certificate -n "$PLATFORM_NS" --no-headers \
      -o custom-columns='NAME:.metadata.name,READY:.status.conditions[*].status,NOT-AFTER:.status.notAfter' \
      | sed 's/^/    /'
  else
    log_error "не Ready:"
    printf '%s\n' "$CERT_NOT_READY" | sed 's/^/    /'
  fi
else
  log_warn "cert-manager Certificate CRD не найден (или нет Certificate в platform)"
fi

# 10. Postgres alive
log_section "10) Postgres"
check_step_with_output \
  "pg_isready на postgres-0" \
  "$K exec -n $PLATFORM_NS postgres-0 -- pg_isready -U platform_user -d postgres"

# 11. Redis alive
log_section "11) Redis"
check_step_with_output \
  "redis-cli ping на redis-0" \
  "$K exec -n $PLATFORM_NS redis-0 -- redis-cli ping"

# 12. Loki / Tempo readiness
log_section "12) Loki / Tempo"
check_step \
  "Loki ready" \
  "$K exec -n $PLATFORM_NS loki-0 -- wget -q -O - http://localhost:3100/ready 2>/dev/null | grep -q ready"
check_step \
  "Tempo ready" \
  "$K exec -n $PLATFORM_NS tempo-0 -- wget -q -O - http://localhost:3200/ready 2>/dev/null | grep -q ready"

# 13. Health endpoints через ingress (если есть DNS)
if [ "$CHECK_PUBLIC" = "1" ] && command -v curl >/dev/null 2>&1; then
  log_section "13) Public health endpoints (через Ingress)"
  for path in "/flows/health" "/crm/health" "/rag/health" "/sync/health" "/litserve/health"; do
    check_step \
      "https://${APEX_HOST}${path}" \
      "curl -fsS --max-time 10 https://${APEX_HOST}${path} >/dev/null"
  done
  check_step \
    "https://${GRAFANA_HOST}/api/health" \
    "curl -fsSI --max-time 10 https://${GRAFANA_HOST}/api/health >/dev/null"
else
  log_info "Пропуск public-проверок (CHECK_PUBLIC=0 или нет curl)"
fi

# Итог
print_summary
