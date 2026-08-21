#!/usr/bin/env bash
# Reg.ru API принимает запросы только с whitelist IP (master egress 31.192.111.33).
# GitHub Actions runner и локальный Mac — другие IP → ACCESS_DENIED_FROM_IP.
#
# CI/local deploy: выполняем setup-brand-dns.sh с egress master.
# Предпочтение — kubectl exec в уже Running pod на master (не создаёт новый Pod:
# при больном kubelet Job/Pod зависают в Pending и валят весь Deploy).
# Fallback — one-shot Job с образом платформы (curl+python3 уже в image).
#
#   REGRU_USERNAME=... REGRU_PASSWORD=... bash deploy/scripts/setup-brand-dns-via-master-job.sh [public_ip]
#
# Опционально:
#   BRAND_DNS_EXEC_DEPLOYMENT=frontend   # deployment для exec (default: frontend)
#   BRAND_DNS_IMAGE=ghcr.io/...:tag      # образ Job fallback (default: текущий image frontend)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
# shellcheck source=_regru_api.sh
source "$SCRIPT_DIR/_regru_api.sh"

PUBLIC_IP="${1:-31.192.111.33}"
PLATFORM_NS="${PLATFORM_NS:-platform}"
MASTER_NODE="${MASTER_NODE_NAME:-master}"
CM_NAME="regru-brand-dns-scripts"
SECRET_NAME="regru-brand-dns-credentials"
JOB_NAME="regru-brand-dns-$(date +%s)"
EXEC_DEPLOYMENT="${BRAND_DNS_EXEC_DEPLOYMENT:-frontend}"
SCRIPTS_MOUNT="/tmp/regru-brand-dns-scripts"

if [ -z "${KUBECTL:-}" ]; then
  log_error "kubectl недоступен — нужен KUBECONFIG (CI: KUBECONFIG_B64)"
  exit 1
fi

K="$KUBECTL"
regru_require_credentials

log_section "Reg.ru brand DNS через master (${MASTER_NODE}) → ${PUBLIC_IP}"

if ! $K get namespace "$PLATFORM_NS" >/dev/null 2>&1; then
  log_error "namespace ${PLATFORM_NS} не существует — deploy должен создать его до DNS-шага"
  exit 1
fi

log_do "ConfigMap ${CM_NAME}"
$K create configmap "$CM_NAME" -n "$PLATFORM_NS" \
  --from-file=_common.sh="$SCRIPT_DIR/_common.sh" \
  --from-file=_regru_api.sh="$SCRIPT_DIR/_regru_api.sh" \
  --from-file=setup-brand-dns.sh="$SCRIPT_DIR/setup-brand-dns.sh" \
  --dry-run=client -o yaml | $K apply -f -

log_do "Secret ${SECRET_NAME}"
$K create secret generic "$SECRET_NAME" -n "$PLATFORM_NS" \
  --from-literal=REGRU_USERNAME="$REGRU_USERNAME" \
  --from-literal=REGRU_PASSWORD="$REGRU_PASSWORD" \
  --dry-run=client -o yaml | $K apply -f -

find_running_pod_on_master() {
  local deployment="$1"
  $K get pods -n "$PLATFORM_NS" \
    -l "app=${deployment}" \
    --field-selector="status.phase=Running,spec.nodeName=${MASTER_NODE}" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

run_dns_via_exec() {
  local pod_name="$1"
  log_do "kubectl exec ${pod_name} (Running на ${MASTER_NODE})"

  $K exec -n "$PLATFORM_NS" "$pod_name" -- \
    /bin/sh -c "rm -rf '${SCRIPTS_MOUNT}' && mkdir -p '${SCRIPTS_MOUNT}'"

  $K cp -n "$PLATFORM_NS" \
    "${SCRIPT_DIR}/_common.sh" \
    "${pod_name}:${SCRIPTS_MOUNT}/_common.sh"
  $K cp -n "$PLATFORM_NS" \
    "${SCRIPT_DIR}/_regru_api.sh" \
    "${pod_name}:${SCRIPTS_MOUNT}/_regru_api.sh"
  $K cp -n "$PLATFORM_NS" \
    "${SCRIPT_DIR}/setup-brand-dns.sh" \
    "${pod_name}:${SCRIPTS_MOUNT}/setup-brand-dns.sh"

  # Credentials из Secret — app-pod их не имеет; передаём в remote bash.
  local username password
  username="$($K get secret "$SECRET_NAME" -n "$PLATFORM_NS" -o jsonpath='{.data.REGRU_USERNAME}' | base64 -d)"
  password="$($K get secret "$SECRET_NAME" -n "$PLATFORM_NS" -o jsonpath='{.data.REGRU_PASSWORD}' | base64 -d)"
  if [ -z "$username" ] || [ -z "$password" ]; then
    log_error "Secret ${SECRET_NAME}: пустые REGRU_USERNAME/REGRU_PASSWORD"
    return 1
  fi

  $K exec -n "$PLATFORM_NS" "$pod_name" -- /bin/bash -c "
    set -euo pipefail
    export REGRU_USERNAME=$(printf '%q' "$username")
    export REGRU_PASSWORD=$(printf '%q' "$password")
    cd $(printf '%q' "$SCRIPTS_MOUNT")
    chmod +x _common.sh _regru_api.sh setup-brand-dns.sh
    bash setup-brand-dns.sh $(printf '%q' "$PUBLIC_IP")
  "
}

resolve_job_image() {
  if [ -n "${BRAND_DNS_IMAGE:-}" ]; then
    printf '%s\n' "$BRAND_DNS_IMAGE"
    return 0
  fi
  local from_deploy
  from_deploy="$($K get deploy "$EXEC_DEPLOYMENT" -n "$PLATFORM_NS" \
    -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  if [ -n "$from_deploy" ]; then
    printf '%s\n' "$from_deploy"
    return 0
  fi
  log_error "Не задан BRAND_DNS_IMAGE и нет image у deploy/${EXEC_DEPLOYMENT}"
  return 1
}

run_dns_via_job() {
  local image
  image="$(resolve_job_image)"
  log_warn "Running pod на ${MASTER_NODE} не найден — fallback Job image=${image}"

  log_do "Job ${JOB_NAME}"
  cat <<EOF | $K apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${PLATFORM_NS}
spec:
  ttlSecondsAfterFinished: 600
  backoffLimit: 0
  activeDeadlineSeconds: 540
  template:
    spec:
      nodeName: ${MASTER_NODE}
      restartPolicy: Never
      containers:
        - name: regru-brand-dns
          image: ${image}
          imagePullPolicy: IfNotPresent
          command: ["/bin/bash", "-c"]
          args:
            - |
              set -euo pipefail
              cd /scripts
              bash setup-brand-dns.sh ${PUBLIC_IP}
          envFrom:
            - secretRef:
                name: ${SECRET_NAME}
          volumeMounts:
            - name: scripts
              mountPath: /scripts
              readOnly: true
      imagePullSecrets:
        - name: ghcr-agent-lab-pull
      volumes:
        - name: scripts
          configMap:
            name: ${CM_NAME}
            defaultMode: 0555
EOF

  cleanup_job() {
    $K delete job "$JOB_NAME" -n "$PLATFORM_NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  }
  trap cleanup_job EXIT

  # Ждём появления Pod — иначе Complete никогда не наступит (kubelet Pending).
  if ! wait_for \
    "Job ${JOB_NAME} has Pod" \
    "[ -n \"\$($K get pods -n ${PLATFORM_NS} -l job-name=${JOB_NAME} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)\" ]" \
    120 5; then
    log_error "Job ${JOB_NAME}: Pod не создался за 120s (kubelet/master?)"
    $K describe job "$JOB_NAME" -n "$PLATFORM_NS" || true
    $K get pods -n "$PLATFORM_NS" -l "job-name=${JOB_NAME}" -o wide || true
    exit 1
  fi

  local job_pod
  job_pod="$($K get pods -n "$PLATFORM_NS" -l "job-name=${JOB_NAME}" -o jsonpath='{.items[0].metadata.name}')"
  if ! wait_for \
    "Pod ${job_pod} Running|Succeeded" \
    "phase=\$($K get pod ${job_pod} -n ${PLATFORM_NS} -o jsonpath='{.status.phase}' 2>/dev/null); [ \"\$phase\" = 'Running' ] || [ \"\$phase\" = 'Succeeded' ]" \
    180 5; then
    log_error "Pod ${job_pod} не стартовал (phase=$($K get pod "$job_pod" -n "$PLATFORM_NS" -o jsonpath='{.status.phase}' 2>/dev/null || echo unknown))"
    $K describe pod "$job_pod" -n "$PLATFORM_NS" || true
    exit 1
  fi

  if ! wait_for \
    "Job ${JOB_NAME} complete" \
    "[ \"\$($K get job ${JOB_NAME} -n ${PLATFORM_NS} -o jsonpath='{.status.conditions[?(@.type==\"Complete\")].status}' 2>/dev/null)\" = 'True' ]" \
    480 5; then
    log_error "Job ${JOB_NAME} не завершился успешно"
    $K describe job "$JOB_NAME" -n "$PLATFORM_NS" || true
    $K logs "job/${JOB_NAME}" -n "$PLATFORM_NS" || true
    exit 1
  fi

  $K logs "job/${JOB_NAME}" -n "$PLATFORM_NS"
}

EXEC_POD="$(find_running_pod_on_master "$EXEC_DEPLOYMENT")"
if [ -z "$EXEC_POD" ]; then
  # Любой Running app-pod на master с curl/python3.
  EXEC_POD="$($K get pods -n "$PLATFORM_NS" \
    --field-selector="status.phase=Running,spec.nodeName=${MASTER_NODE}" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null \
    | while read -r candidate; do
        [ -z "$candidate" ] && continue
        case "$candidate" in
          postgres-*|redis-*|loki-*|tempo-*|alloy-*|coturn-*|livekit*|onlyoffice-*|grafana-*)
            continue
            ;;
        esac
        if $K exec -n "$PLATFORM_NS" "$candidate" -- /bin/sh -c 'command -v curl >/dev/null && command -v python3 >/dev/null && command -v bash >/dev/null' 2>/dev/null; then
          printf '%s\n' "$candidate"
          break
        fi
      done)"
fi

if [ -n "$EXEC_POD" ]; then
  run_dns_via_exec "$EXEC_POD"
else
  run_dns_via_job
fi

log_ok "Reg.ru brand DNS применён с master (${PUBLIC_IP})"
print_summary
