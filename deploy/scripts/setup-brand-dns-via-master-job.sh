#!/usr/bin/env bash
# Reg.ru API принимает запросы только с whitelist IP (master egress 84.38.184.105).
# GitHub Actions runner и локальный Mac — другие IP → ACCESS_DENIED_FROM_IP.
#
# CI/local deploy: one-shot Job на nodeName=master, внутри — setup-brand-dns.sh.
#
#   REGRU_USERNAME=... REGRU_PASSWORD=... bash deploy/scripts/setup-brand-dns-via-master-job.sh [public_ip]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
# shellcheck source=_regru_api.sh
source "$SCRIPT_DIR/_regru_api.sh"

PUBLIC_IP="${1:-84.38.184.105}"
PLATFORM_NS="${PLATFORM_NS:-platform}"
MASTER_NODE="${MASTER_NODE_NAME:-master}"
CM_NAME="regru-brand-dns-scripts"
SECRET_NAME="regru-brand-dns-credentials"
JOB_NAME="regru-brand-dns-$(date +%s)"

if [ -z "${KUBECTL:-}" ]; then
  log_error "kubectl недоступен — нужен KUBECONFIG (CI: KUBECONFIG_B64)"
  exit 1
fi

K="$KUBECTL"
regru_require_credentials

log_section "Reg.ru brand DNS через Job на node ${MASTER_NODE} → ${PUBLIC_IP}"

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
  template:
    spec:
      nodeName: ${MASTER_NODE}
      restartPolicy: Never
      containers:
        - name: regru-brand-dns
          image: python:3.14-slim-bookworm
          command: ["/bin/bash", "-c"]
          args:
            - |
              set -euo pipefail
              export DEBIAN_FRONTEND=noninteractive
              apt-get update -qq
              apt-get install -qq -y --no-install-recommends curl ca-certificates >/dev/null
              cd /scripts
              bash setup-brand-dns.sh ${PUBLIC_IP}
          envFrom:
            - secretRef:
                name: ${SECRET_NAME}
          volumeMounts:
            - name: scripts
              mountPath: /scripts
              readOnly: true
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

if ! wait_for \
  "Job ${JOB_NAME} complete" \
  "[ \"\$($K get job ${JOB_NAME} -n ${PLATFORM_NS} -o jsonpath='{.status.conditions[?(@.type==\"Complete\")].status}' 2>/dev/null)\" = 'True' ]" \
  600 5; then
  log_error "Job ${JOB_NAME} не завершился успешно"
  $K describe job "$JOB_NAME" -n "$PLATFORM_NS" || true
  $K logs "job/${JOB_NAME}" -n "$PLATFORM_NS" || true
  exit 1
fi

$K logs "job/${JOB_NAME}" -n "$PLATFORM_NS"
log_ok "Reg.ru brand DNS применён с master (${PUBLIC_IP})"
print_summary
