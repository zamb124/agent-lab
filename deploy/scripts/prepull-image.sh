#!/usr/bin/env bash
# Pre-pull релизного образа на master-ноду ДО helm upgrade — rollout не ждёт скачивание с GHCR.
# Без этого шага старые поды терминируются, а новые висят в ImagePull (~25 мин на медленном egress).
#
# Запуск: bash deploy/scripts/prepull-image.sh ghcr.io/zamb124/agent-lab:<tag>
#   или   IMAGE_REF=... bash deploy/scripts/prepull-image.sh
# Вызывается из CI (.github/workflows/deploy.yml, шаг до "Helm upgrade --install") и make k8s-deploy.
# Идемпотентен: образ уже на ноде → pull-pod завершается за секунды. Провал → старые поды ещё живы.

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

K="$KUBECTL"
NS="${PLATFORM_NS:-platform}"
PULL_SECRET="${PREPULL_PULL_SECRET:-ghcr-agent-lab-pull}"
PULL_TIMEOUT_SEC="${PREPULL_TIMEOUT_SEC:-2700}"

IMAGE_REF="${1:-${IMAGE_REF:-}}"
if [ -z "${IMAGE_REF}" ]; then
  log_error "Нужен IMAGE_REF: bash prepull-image.sh ghcr.io/zamb124/agent-lab:<tag>"
  print_summary
  exit 1
fi

# Tag — DNS-1123-совместимый (sha); sanitize на случай ':'/'.' в нестандартных тегах.
POD_NAME="prepull-$(printf '%s' "${IMAGE_REF##*:}" | tr -c 'a-z0-9-' '-' | cut -c1-40)"

cleanup_pod() {
  $K delete pod "$POD_NAME" -n "$NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup_pod EXIT

log_section "Pre-pull ${IMAGE_REF} → ${MASTER_NODE_NAME}"

# Повторный запуск с тем же тегом: completed/failed pod может уже существовать.
$K delete pod "$POD_NAME" -n "$NS" --ignore-not-found --wait=true >/dev/null

$K apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
  namespace: ${NS}
spec:
  restartPolicy: Never
  nodeName: ${MASTER_NODE_NAME}
  imagePullSecrets:
    - name: ${PULL_SECRET}
  containers:
    - name: pull
      image: ${IMAGE_REF}
      imagePullPolicy: IfNotPresent
      command: ["true"]
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          memory: 64Mi
EOF

# kubectl wait --for=condition=Succeeded на Pod не работает: Succeeded — phase,
# не condition. Поллим phase; Failed/Unknown — мгновенный выход с диагностикой.
pod_phase() {
  $K get pod "$POD_NAME" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true
}

if ! wait_for \
  "Pod ${POD_NAME} terminal" \
  "phase=\$(pod_phase); [ \"\$phase\" = 'Succeeded' ] || [ \"\$phase\" = 'Failed' ] || [ \"\$phase\" = 'Unknown' ]" \
  "${PULL_TIMEOUT_SEC}" 10; then
  log_error "Pre-pull ${IMAGE_REF} не завершился за ${PULL_TIMEOUT_SEC}s (phase=$(pod_phase))"
  $K describe pod "$POD_NAME" -n "$NS" | tail -30 >&2 || true
  exit 1
fi

if [ "$(pod_phase)" != "Succeeded" ]; then
  log_error "Pre-pull pod ${POD_NAME}: phase=$(pod_phase)"
  $K describe pod "$POD_NAME" -n "$NS" | tail -30 >&2 || true
  exit 1
fi

log_do "образ на ноде: ${IMAGE_REF}"
print_summary
