#!/usr/bin/env bash
# Снести старые ghcr.io/zamb124/agent-lab{,-gpu}:* на master.
# kubelet image GC при usage>=85% удаляет слои во время pull и дедлочит деплой.
#
# Оставляет образы Running/Pending подов и KEEP_TAGS последних тегов.
#
#   bash deploy/scripts/gpu_prune_release_images.sh
#   make k8s-gpu-prune

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

require_command ssh
require_command kubectl

KEEP_TAGS="${GPU_PRUNE_KEEP_TAGS:-3}"
GPU_SSH="${GPU_SSH:-${SSH_USER}@${MASTER_HOST_IP}}"
NS="${PLATFORM_NS:-platform}"
K="$KUBECTL"
KEEP_REMOTE="/tmp/gpu-prune-keep.txt"

if ! [[ "$KEEP_TAGS" =~ ^[1-9][0-9]*$ ]]; then
  log_error "GPU_PRUNE_KEEP_TAGS должен быть положительным целым, сейчас ${KEEP_TAGS}"
  print_summary
  exit 1
fi

log_section "GPU prune (keep ${KEEP_TAGS} tags + in-use)"

if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "$GPU_SSH" "true"; then
  log_error "нет SSH ${GPU_SSH}"
  print_summary
  exit 1
fi

IN_USE="$($K get pods -n "$NS" --field-selector spec.nodeName="${GPU_NODE_NAME}" -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{range .spec.initContainers[*]}{.image}{"\n"}{end}{end}')"
IN_USE="$(printf '%s\n' "${IN_USE}" | awk 'NF' | sort -u)"
if [ -z "${IN_USE}" ]; then
  log_error "на ${GPU_NODE_NAME} нет подов — prune без in-use списка запрещён"
  print_summary
  exit 1
fi

log_info "in-use на ${GPU_NODE_NAME}:"
printf '%s\n' "${IN_USE}" | sed 's/^/    /'

printf '%s\n' "${IN_USE}" | ssh -o BatchMode=yes -o ConnectTimeout=15 "$GPU_SSH" "cat > ${KEEP_REMOTE}"

ssh -o BatchMode=yes -o ConnectTimeout=15 "$GPU_SSH" "KEEP_TAGS=${KEEP_TAGS} KEEP_FILE=${KEEP_REMOTE} bash -s" <<'REMOTE'
set -euo pipefail
if [ ! -s "${KEEP_FILE}" ]; then
  echo "gpu_prune: empty keep file" >&2
  exit 1
fi
prune_repo() {
  local repo="$1"
  local tags
  tags=$(microk8s.ctr --namespace k8s.io images ls | awk -v r="${repo}:" '$1 ~ "^"r {print $1}' | sort)
  if [ -z "${tags}" ]; then
    return 0
  fi
  local keep
  keep=$(printf '%s\n' "${tags}" | tail -n "${KEEP_TAGS}")
  local ref
  for ref in ${tags}; do
    if grep -Fxq "${ref}" "${KEEP_FILE}"; then
      continue
    fi
    if printf '%s\n' "${keep}" | grep -Fxq "${ref}"; then
      continue
    fi
    echo "gpu_prune: remove ${ref}"
    microk8s ctr images rm "${ref}"
  done
}
prune_repo "ghcr.io/zamb124/agent-lab"
prune_repo "ghcr.io/zamb124/agent-lab-gpu"
rm -f "${KEEP_FILE}"
df -h / | tail -1
REMOTE

log_ok "prune завершён"
print_summary
