#!/usr/bin/env bash
# Перенос release-образов master → gpu-worker по LAN.
#
# gpu-worker тянет ghcr.io ~1 час на 5 GiB (containerd log: Pulled ... in 1h0m16s).
# master тянет минуты; scp+import по LAN — минуты. Helm --wait не должен ждать GHCR с GPU.
#
# Запуск (SSH на master обязателен):
#   IMAGE_APP=ghcr.io/zamb124/agent-lab:<tag> \
#   IMAGE_GPU=ghcr.io/zamb124/agent-lab-gpu:<tag> \
#   bash deploy/scripts/gpu_sync_release_images.sh
#
# Или: make k8s-gpu-sync IMAGE_TAG=<tag>
#
# Если образа нет на master — поднимает pull-pod на master (imagePullSecret ghcr-agent-lab-pull).

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

require_command ssh
require_command kubectl

NS="${PLATFORM_NS:-platform}"
IMAGE_APP="${IMAGE_APP:-}"
IMAGE_GPU="${IMAGE_GPU:-}"
MASTER_SSH="${MASTER_SSH:-${SSH_USER}@${MASTER_HOST_IP}}"
GPU_SSH_FROM_MASTER="${GPU_SSH_FROM_MASTER:-${SSH_USER}@${GPU_HOST_IP}}"
PULL_SECRET="${GPU_SYNC_PULL_SECRET:-ghcr-agent-lab-pull}"
PULL_TIMEOUT_SEC="${GPU_SYNC_PULL_TIMEOUT_SEC:-600}"

if [ -z "${IMAGE_APP}" ] || [ -z "${IMAGE_GPU}" ]; then
  log_error "Нужны IMAGE_APP и IMAGE_GPU (ghcr.io/...:<immutable-tag>)"
  print_summary
  exit 1
fi

K="$KUBECTL"
log_section "GPU sync ${IMAGE_APP} + ${IMAGE_GPU} (master → ${GPU_NODE_NAME})"

node_has_image() {
  local ssh_target="$1"
  local image_ref="$2"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$ssh_target" \
    "microk8s.ctr --namespace k8s.io images ls | awk '{print \$1}' | grep -Fx '${image_ref}'" >/dev/null 2>&1
}

pull_on_master() {
  local image_ref="$1"
  local pod_name="$2"
  if node_has_image "$MASTER_SSH" "$image_ref"; then
    log_skip "master уже имеет ${image_ref}"
    return 0
  fi
  log_do "pull ${image_ref} на master через pod ${pod_name}"
  $K delete pod "$pod_name" -n "$NS" --ignore-not-found --wait=true >/dev/null
  $K apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${pod_name}
  namespace: ${NS}
spec:
  restartPolicy: Never
  nodeName: ${MASTER_NODE_NAME}
  imagePullSecrets:
    - name: ${PULL_SECRET}
  containers:
    - name: pull
      image: ${image_ref}
      imagePullPolicy: IfNotPresent
      command: ["true"]
EOF
  if ! $K wait pod/"$pod_name" -n "$NS" --for=condition=Succeeded --timeout="${PULL_TIMEOUT_SEC}s"; then
    $K describe pod "$pod_name" -n "$NS" | tail -30 >&2
    $K delete pod "$pod_name" -n "$NS" --ignore-not-found >/dev/null
    log_error "master не смог pull ${image_ref} за ${PULL_TIMEOUT_SEC}s"
    return 1
  fi
  $K delete pod "$pod_name" -n "$NS" --ignore-not-found --wait=true >/dev/null
  if ! node_has_image "$MASTER_SSH" "$image_ref"; then
    log_error "после pull-pod образа ${image_ref} нет в containerd master"
    return 1
  fi
  log_ok "master имеет ${image_ref}"
}

sync_to_gpu() {
  local image_ref="$1"
  local tar_name="$2"
  if ssh -o BatchMode=yes -o ConnectTimeout=10 "$MASTER_SSH" \
    "ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new ${GPU_SSH_FROM_MASTER} \"microk8s.ctr --namespace k8s.io images ls | awk '{print \\\$1}' | grep -Fx '${image_ref}'\"" \
    >/dev/null 2>&1; then
    log_skip "gpu-worker уже имеет ${image_ref}"
    return 0
  fi
  log_do "export/scp/import ${image_ref} master → gpu-worker"
  ssh -o BatchMode=yes -o ConnectTimeout=15 "$MASTER_SSH" "set -euo pipefail
    microk8s ctr images export /tmp/${tar_name} '${image_ref}'
    scp -o StrictHostKeyChecking=accept-new /tmp/${tar_name} ${GPU_SSH_FROM_MASTER}:/tmp/${tar_name}
    ssh -o StrictHostKeyChecking=accept-new ${GPU_SSH_FROM_MASTER} \"set -euo pipefail; microk8s ctr images import /tmp/${tar_name}; rm -f /tmp/${tar_name}; microk8s.ctr --namespace k8s.io images ls | awk '{print \\\$1}' | grep -Fx '${image_ref}'\"
    rm -f /tmp/${tar_name}
  "
  log_ok "gpu-worker имеет ${image_ref}"
}

if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "$MASTER_SSH" "true"; then
  log_error "нет SSH ${MASTER_SSH} (BatchMode). Скрипт гоняется с машины, где есть ключ на master."
  print_summary
  exit 1
fi

pull_on_master "$IMAGE_APP" "gpu-sync-pull-app"
pull_on_master "$IMAGE_GPU" "gpu-sync-pull-gpu"
sync_to_gpu "$IMAGE_APP" "agent-lab-app-sync.tar"
sync_to_gpu "$IMAGE_GPU" "agent-lab-gpu-sync.tar"

print_summary
