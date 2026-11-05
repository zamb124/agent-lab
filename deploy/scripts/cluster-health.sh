#!/usr/bin/env bash
# Полная проверка здоровья платформы Linnex.
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
#   APEX_HOST=linnex.io              — legacy single apex (если PLATFORM_APEX_HOSTS пуст)
#   PLATFORM_APEX_HOSTS="linnex.io linnex.io" — все brand apex для public checks
#   GRAFANA_HOST=grafana.linnex.io   — Grafana (PUBLIC)
#   ONLYOFFICE_HOST=onlyoffice.linnex.io
#   LIVEKIT_HOST=livekit.linnex.io
#   CHECK_PUBLIC=1                      — проверить https://… через curl (требует DNS); 0 = только in-cluster
#   PLATFORM_PUBLIC_IP=77.91.94.127     — ожидаемый A-record для apex/subdomain brand DNS (CHECK_PUBLIC=1)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if ! command -v kubectl >/dev/null 2>&1 && ! command -v microk8s >/dev/null 2>&1; then
  log_error "Нужен kubectl или microk8s"
  exit 1
fi

K="$KUBECTL"
APEX_HOST="${APEX_HOST:-linnex.io}"
PLATFORM_APEX_HOSTS="${PLATFORM_APEX_HOSTS:-linnex.io linnex.io}"
GRAFANA_HOST="${GRAFANA_HOST:-grafana.linnex.io}"
ONLYOFFICE_HOST="${ONLYOFFICE_HOST:-onlyoffice.linnex.io}"
LIVEKIT_HOST="${LIVEKIT_HOST:-livekit.linnex.io}"
CHECK_PUBLIC="${CHECK_PUBLIC:-1}"
PLATFORM_PUBLIC_IP="${PLATFORM_PUBLIC_IP:-77.91.94.127}"

if [ "$CHECK_PUBLIC" = "1" ]; then
  if ! command -v curl >/dev/null 2>&1; then
    log_error "CHECK_PUBLIC=1 требует curl в PATH"
    exit 1
  fi
  if ! command -v dig >/dev/null 2>&1; then
    log_error "CHECK_PUBLIC=1 требует dig в PATH (проверка brand DNS)"
    exit 1
  fi
fi

# Список ожидаемых деплойментов (дефолтный состав под Helm values.yaml + values-prod.yaml).
# При отключении компонента через Helm (*.enabled: false) уберите имя отсюда (см. deploy/README.md
# «Состав приложений: Helm и cluster-health»).
EXPECTED_DEPLOYMENTS=(
  flows frontend crm rag sync worktracker office wiki guest-runtime realtime scheduler-api voice browser search secrets capability-gateway code-runner-python code-runner-node code-runner-go code-runner-csharp shop geo
  flows-worker scheduler rag-worker sync-worker crm-worker crm-summary-worker idle-worker search-worker shop-worker geo-worker
  livekit livekit-egress onlyoffice grafana provider-litserve openfga centrifugo
)
EXPECTED_STATEFULSETS=(postgres redis redis-realtime loki tempo seaweedfs)
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

# 2. GPU на ноде LitServe
log_section "2) GPU"
LITSERVE_HOST=$($K get deploy provider-litserve -n "$PLATFORM_NS" \
  -o jsonpath='{.spec.template.spec.nodeSelector.kubernetes\.io/hostname}' 2>/dev/null || true)
if [ -n "$LITSERVE_HOST" ]; then
  check_step \
    "node $LITSERVE_HOST имеет nvidia.com/gpu в Allocatable" \
    "$K get node $LITSERVE_HOST -o jsonpath='{.status.allocatable.nvidia\\.com/gpu}' | grep -qE '^[1-9]'"
else
  log_info "LitServe без nodeSelector — проверка GPU по hostname пропущена"
fi

# 3. Поды Running / Completed / Terminating (старое поколение при rollout — не сбой)
log_section "3) Поды в namespace $PLATFORM_NS"
NOT_OK=$($K get pods -n "$PLATFORM_NS" --no-headers 2>/dev/null \
  | awk '$3 != "Running" && $3 != "Completed" && $3 != "Terminating" {print $1, $3}')
if [ -z "$NOT_OK" ]; then
  log_ok "все поды Running/Completed или Terminating (drain после rollout)"
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

POSTGRES_PVC_USE=$($K exec -n "$PLATFORM_NS" postgres-0 -- \
  df -P /var/lib/postgresql/data 2>/dev/null | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
if ! printf '%s' "$POSTGRES_PVC_USE" | grep -Eq '^[0-9]+$'; then
  log_warn "не удалось прочитать заполнение PVC postgres"
elif [ "$POSTGRES_PVC_USE" -ge 90 ]; then
  log_error "PVC postgres заполнен на ${POSTGRES_PVC_USE}% (>= 90)"
elif [ "$POSTGRES_PVC_USE" -ge 70 ]; then
  log_warn "PVC postgres заполнен на ${POSTGRES_PVC_USE}% (>= 70)"
else
  log_ok "PVC postgres заполнен на ${POSTGRES_PVC_USE}%"
fi

# 8. Ingress address
log_section "8) Ingress"
INGRESS_LIST=$($K get ingress -n "$PLATFORM_NS" --no-headers -o custom-columns=NAME:.metadata.name,HOST:.spec.rules[*].host,ADDRESS:.status.loadBalancer.ingress[*].ip 2>/dev/null)
if [ -n "$INGRESS_LIST" ]; then
  log_ok "Ingress объекты есть"
  printf '%s\n' "$INGRESS_LIST" | sed 's/^/    /'
else
  log_error "Ingress объектов нет"
fi
# Монолитный Ingress platform (до split на platform-services/frontend) не содержит /worktracker:
# Traefik матчит /worktracker на catch-all frontend → WS 403 (health видит как fail, не 401/101).
if $K get ingress platform -n "$PLATFORM_NS" >/dev/null 2>&1 \
  && $K get ingress platform-services -n "$PLATFORM_NS" >/dev/null 2>&1; then
  check_step \
    "нет устаревшего Ingress platform (удалить: kubectl delete ingress platform -n $PLATFORM_NS)" \
    "false"
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
  "[ \"$($K get pod loki-0 -n $PLATFORM_NS -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)\" = 'true' ]"
check_step \
  "Tempo ready" \
  "[ \"$($K get pod tempo-0 -n $PLATFORM_NS -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)\" = 'true' ]"

# 12b. TLS Certificate SAN покрывает все brand apex (in-cluster, без curl)
log_section "12b) platform-tls Certificate dnsNames"
CURRENT_CERT_DNS=$($K get certificate platform-tls -n "$PLATFORM_NS" \
  -o jsonpath='{.spec.dnsNames[*]}' 2>/dev/null || true)
for apex in $PLATFORM_APEX_HOSTS; do
  check_step \
    "Certificate platform-tls dnsNames содержит ${apex}" \
    "case ' ${CURRENT_CERT_DNS} ' in *' ${apex} '*) exit 0;; *) exit 1;; esac"
  check_step \
    "Certificate platform-tls dnsNames содержит *.${apex}" \
    "case ' ${CURRENT_CERT_DNS} ' in *' *.${apex} '*) exit 0;; *) exit 1;; esac"
done

# 12c. Brand apex DNS указывает на кластер (CHECK_PUBLIC=1)
if [ "$CHECK_PUBLIC" = "1" ]; then
  log_section "12c) Brand apex DNS → ${PLATFORM_PUBLIC_IP}"
  for apex in $PLATFORM_APEX_HOSTS; do
    check_step \
      "dig ${apex} A → ${PLATFORM_PUBLIC_IP}" \
      "[ \"\$(dig +short ${apex} A | head -1)\" = '${PLATFORM_PUBLIC_IP}' ]"
    check_step \
      "dig www.${apex} A → ${PLATFORM_PUBLIC_IP}" \
      "[ \"\$(dig +short www.${apex} A | head -1)\" = '${PLATFORM_PUBLIC_IP}' ]"
  done
fi

# 13. Health-endpoints через ingress (если есть DNS)
if [ "$CHECK_PUBLIC" = "1" ]; then
  log_section "13) Public health endpoints (через Ingress)"
  for apex in $PLATFORM_APEX_HOSTS; do
    for path in "/flows/health" "/crm/health" "/sync/health" "/worktracker/health" "/secrets/health" "/wiki/health"; do
      check_step \
        "https://${apex}${path}" \
        "curl -fsS --max-time 10 https://${apex}${path} >/dev/null"
    done
    check_step \
      "https://grafana.${apex}/api/health" \
      "curl -fsS --max-time 10 https://grafana.${apex}/api/health >/dev/null"
  done
fi

# 14. User WebSocket — Centrifugo /realtime (не Granian сервисов)
if [ "$CHECK_PUBLIC" = "1" ]; then
  log_section "14) WebSocket upgrade Centrifugo /realtime"
  for apex in $PLATFORM_APEX_HOSTS; do
    check_step \
      "WS upgrade https://${apex}/realtime/connection/websocket (401 или 101, не 500)" \
      "code=\$(curl -sS --http1.1 -o /dev/null -w '%{http_code}' --max-time 10 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' 'https://${apex}/realtime/connection/websocket'); [ \"\$code\" = '401' ] || [ \"\$code\" = '101' ]"
    check_step \
      "Centrifugo /realtime/health" \
      "curl -fsS --max-time 10 https://${apex}/realtime/health >/dev/null"
    check_step \
      "realtime bus /realtime/api (401 или 404, не 500)" \
      "code=\$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 'https://${apex}/realtime/api/v1/events/missing'); [ \"\$code\" = '401' ] || [ \"\$code\" = '404' ] || [ \"\$code\" = '403' ]"
  done
fi

# 15. Запрет serversscheme h2c на app Service (ломает WS upgrade)
log_section "15) Traefik backend-hop (no h2c on app Service)"
check_step \
  "нет Service с traefik serversscheme=h2c в $PLATFORM_NS" \
  "! $K get svc -n $PLATFORM_NS -o jsonpath='{range .items[*]}{.metadata.annotations.traefik\\.ingress\\.kubernetes\\.io/service\\.serversscheme}{\"\\n\"}{end}' 2>/dev/null | grep -q '^h2c$'"

# 16. Provider Litserve (in-cluster: runtime + embedding smoke)
log_section "16) Provider Litserve (runtime + embedding smoke)"
LITSERVE_POD=$($K get pod -n "$PLATFORM_NS" -l app=provider-litserve \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$LITSERVE_POD" ]; then
  log_warn "под provider-litserve не найден — секция пропущена"
else
  # GPU-образ provider-litserve кладёт runtime Python в venv, но не создаёт /usr/bin/python.
  check_step_with_output \
    "litserve GET /v1/health/inference is healthy (in-cluster)" \
    "$K exec -n $PLATFORM_NS $LITSERVE_POD -- \
      curl -fsS --max-time 15 http://127.0.0.1:8014/v1/health/inference >/dev/null"
  check_step_with_output \
    "litserve GET /v1/models is healthy (in-cluster)" \
    "$K exec -n $PLATFORM_NS $LITSERVE_POD -- \
      curl -fsS --max-time 15 http://127.0.0.1:8014/v1/models >/dev/null"
  check_step_with_output \
    "litserve POST /v1/embeddings returns an embedding (in-cluster)" \
    "$K exec -n $PLATFORM_NS $LITSERVE_POD -- sh -lc 'PY=/opt/venv/bin/python; MODEL=\$(\"\$PY\" -c \"from apps.provider_litserve.config import get_provider_litserve_settings as g; print(g().provider_litserve.infra.embedding_openai_model_id)\"); curl -fsS --max-time 300 -H \"Content-Type: application/json\" -d \"{\\\"model\\\":\\\"\${MODEL}\\\",\\\"input\\\":\\\"litserve healthcheck\\\"}\" http://127.0.0.1:8014/v1/embeddings | \"\$PY\" -c \"import json, sys; body=json.load(sys.stdin); vec=body[\\\"data\\\"][0][\\\"embedding\\\"]; assert isinstance(vec, list) and len(vec) > 0\"'"
fi

# 17. Platform brand API (multi-apex)
if [ "$CHECK_PUBLIC" = "1" ]; then
  log_section "17) Platform brand API (multi-apex)"
  for apex in $PLATFORM_APEX_HOSTS; do
    check_step \
      "https://${apex}/frontend/api/platform/brand base_domain=${apex}" \
      "curl -fsS --max-time 10 https://${apex}/frontend/api/platform/brand | python3 -c \"import json,sys; b=json.load(sys.stdin); assert b.get('base_domain')=='${apex}', b\""
  done
fi

# 18. Browser runtime (in-cluster: CDP sidecar + app readiness + рестарты)
log_section "18) Browser runtime (CDP + рестарты)"
BROWSER_POD=$($K get pod -n "$PLATFORM_NS" -l app=browser \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$BROWSER_POD" ]; then
  log_warn "под browser не найден — секция пропущена"
else
  check_step_with_output \
    "chromium-cdp GET /json/version (in-cluster)" \
    "$K exec -n $PLATFORM_NS $BROWSER_POD -c chromium-cdp -- \
      wget -q -O- http://127.0.0.1:9222/json/version >/dev/null"
  check_step_with_output \
    "browser app GET /browser/api/v1/health/cdp (in-cluster)" \
    "$K exec -n $PLATFORM_NS $BROWSER_POD -c browser -- \
      curl -fsS --max-time 15 http://127.0.0.1:8009/browser/api/v1/health/cdp >/dev/null"
  # Высокий счётчик рестартов = death-loop (OOM app / segfault Chromium). Порог 5.
  for c in browser chromium-cdp; do
    RESTARTS=$($K get pod "$BROWSER_POD" -n "$PLATFORM_NS" \
      -o jsonpath="{.status.containerStatuses[?(@.name=='$c')].restartCount}" 2>/dev/null || echo "")
    if [ -z "$RESTARTS" ]; then
      log_error "browser pod: контейнер $c не найден"
    elif [ "$RESTARTS" -le 5 ]; then
      log_ok "контейнер $c рестартов: $RESTARTS (<= 5)"
    else
      log_error "контейнер $c рестартов: $RESTARTS (> 5 — death-loop?)"
    fi
  done
fi

# 18. Code runner python (рестарты / OOM)
log_section "18) Code runner python (рестарты / OOM)"
CODE_RUNNER_PYTHON_POD=$($K get pod -n "$PLATFORM_NS" -l app=code-runner-python \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$CODE_RUNNER_PYTHON_POD" ]; then
  log_warn "под code-runner-python не найден — секция пропущена"
else
  RESTARTS=$($K get pod "$CODE_RUNNER_PYTHON_POD" -n "$PLATFORM_NS" \
    -o jsonpath="{.status.containerStatuses[?(@.name=='code-runner-python')].restartCount}" 2>/dev/null || echo "")
  LAST_REASON=$($K get pod "$CODE_RUNNER_PYTHON_POD" -n "$PLATFORM_NS" \
    -o jsonpath="{.status.containerStatuses[?(@.name=='code-runner-python')].lastState.terminated.reason}" 2>/dev/null || echo "")
  if [ -z "$RESTARTS" ]; then
    log_error "code-runner-python pod: контейнер code-runner-python не найден"
  elif [ "$RESTARTS" -le 3 ]; then
    log_ok "code-runner-python рестартов: $RESTARTS (<= 3)"
  else
    log_error "code-runner-python рестартов: $RESTARTS (> 3 — death-loop?)"
  fi
  if [ -n "$LAST_REASON" ] && [ "$LAST_REASON" = "OOMKilled" ]; then
    log_error "code-runner-python lastState: OOMKilled"
  elif [ -n "$LAST_REASON" ]; then
    log_warn "code-runner-python lastState reason: $LAST_REASON"
  else
    log_ok "code-runner-python lastState: clean"
  fi
  check_step_with_output \
    "code-runner-python GET /health (in-cluster)" \
    "$K exec -n $PLATFORM_NS $CODE_RUNNER_PYTHON_POD -- \
      curl -fsS --max-time 15 http://127.0.0.1:8017/health >/dev/null"
fi

# 19. TaskIQ workers: K8s Ready маскирует внутренний process-manager death-loop и OOM.
log_section "19) TaskIQ workers (рестарты / OOM / death-loop)"
check_taskiq_worker_pod() {
  local app_name="$1"
  local max_restarts="$2"
  local worker_pod
  worker_pod=$($K get pod -n "$PLATFORM_NS" -l "app=${app_name}" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -z "$worker_pod" ]; then
    log_error "${app_name}: под не найден"
    return 1
  fi
  local restarts last_reason
  restarts=$($K get pod "$worker_pod" -n "$PLATFORM_NS" \
    -o jsonpath="{.status.containerStatuses[0].restartCount}" 2>/dev/null || echo "")
  last_reason=$($K get pod "$worker_pod" -n "$PLATFORM_NS" \
    -o jsonpath="{.status.containerStatuses[0].lastState.terminated.reason}" 2>/dev/null || echo "")
  if [ -z "$restarts" ]; then
    log_error "${app_name}: restartCount недоступен"
  elif [ "$restarts" -le "$max_restarts" ]; then
    log_ok "${app_name} рестартов: $restarts (<= ${max_restarts})"
  else
    log_error "${app_name} рестартов: $restarts (> ${max_restarts})"
  fi
  if [ -n "$last_reason" ] && [ "$last_reason" = "OOMKilled" ]; then
    log_error "${app_name} lastState: OOMKilled"
  elif [ -n "$last_reason" ]; then
    log_warn "${app_name} lastState reason: $last_reason"
  else
    log_ok "${app_name} lastState: clean"
  fi
}

check_taskiq_worker_pod idle-worker 3
check_taskiq_worker_pod search-worker 3

# Guest runtime: docker executor + host docker.sock на ноде, где крутится guest-runtime.
log_section "20) Guest runtime docker executor"
GUEST_POD=$($K get pod -n "$PLATFORM_NS" -l app=guest-runtime \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$GUEST_POD" ]; then
  log_error "guest-runtime: под не найден"
else
  GUEST_EXECUTOR=$($K exec -n "$PLATFORM_NS" "$GUEST_POD" -- printenv GUEST_RUNTIME__EXECUTOR)
  if [ "$GUEST_EXECUTOR" != "docker" ]; then
    log_error "guest-runtime executor must be docker, got ${GUEST_EXECUTOR:-empty}"
  else
    log_ok "guest-runtime executor=docker"
  fi
  if $K exec -n "$PLATFORM_NS" "$GUEST_POD" -- test -S /var/run/docker.sock; then
    log_ok "guest-runtime docker.sock смонтирован"
  else
    log_error "guest-runtime: /var/run/docker.sock отсутствует"
  fi
  if $K exec -n "$PLATFORM_NS" "$GUEST_POD" -- docker info >/dev/null; then
    log_ok "guest-runtime docker info"
  else
    log_error "guest-runtime: docker info внутри пода не отвечает (нет Docker Engine на host?)"
  fi
fi

SEARCH_WORKER_POD=$($K get pod -n "$PLATFORM_NS" -l app=search-worker \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "$SEARCH_WORKER_POD" ]; then
  log_error "search-worker: под не найден для проверки логов"
else
  SEARCH_WORKER_LOGS=$($K logs -n "$PLATFORM_NS" "$SEARCH_WORKER_POD" --since=5m --tail=200 2>/dev/null || true)
  if printf '%s\n' "$SEARCH_WORKER_LOGS" | grep -q 'worker-0 is dead'; then
    log_error "search-worker: TaskIQ worker-0 is dead за последние 5 мин"
  elif printf '%s\n' "$SEARCH_WORKER_LOGS" | grep -q 'enqueue: вне request-скоупа'; then
    log_error "search-worker: enqueue без background_kind на startup"
  else
    log_ok "search-worker: нет death-loop в логах за 5 мин"
  fi
fi

# Итог
print_summary
