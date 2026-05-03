#!/usr/bin/env bash
# Идемпотентный bootstrap master ноды MicroK8s.
# Запускать ПОД ROOT на хосте 84.38.184.105.
# Повторный запуск проверяет каждый шаг и пропускает уже сделанное.
#
# Что делает:
#   1. hostname → master
#   2. snap install microk8s --classic --channel=${MICROK8S_CHANNEL}
#   3. usermod ubuntu в группу microk8s (если есть пользователь ubuntu)
#   4. microk8s enable: dns, hostpath-storage, ingress, cert-manager
#   5. wait-ready
#   6. печатает kubeconfig в base64 для GitHub Secret KUBECONFIG_B64
#
# Не делает: join, GPU аддон (это для bootstrap-gpu-worker.sh + join-cluster.sh).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

MASTER_HOSTNAME="${MASTER_HOSTNAME:-master}"
# Канал K8s одинаков на всех нодах кластера (инвариант).
# Latest stable: см. `snap info microk8s` колонка `latest/stable`.
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.35/stable}"
ADDONS=(dns hostpath-storage ingress cert-manager)

log_section "Bootstrap master ноды (hostname=$MASTER_HOSTNAME)"

# 0. UFW off — kubelet 10250 / apiserver 16443 / dqlite 19001 / VXLAN Calico должны
# свободно ходить между нодами; security — через CNI NetworkPolicies, не host UFW.
disable_host_firewall

# 1. hostname
idempotent \
  "hostname = $MASTER_HOSTNAME" \
  "[ \"$(hostname)\" = '$MASTER_HOSTNAME' ]" \
  "hostnamectl set-hostname '$MASTER_HOSTNAME'"

# 2. snap MicroK8s — установка / refresh на канал кластера (общий для master и gpu-worker).
if snap list microk8s 2>/dev/null | grep -q microk8s; then
  CURRENT_CHANNEL="$(snap list microk8s 2>/dev/null | awk 'NR==2{print $4}')"
  if [ "$CURRENT_CHANNEL" != "$MICROK8S_CHANNEL" ]; then
    log_do "snap refresh microk8s $CURRENT_CHANNEL → $MICROK8S_CHANNEL"
    snap refresh microk8s --channel="$MICROK8S_CHANNEL"
  else
    log_skip "microk8s already on $MICROK8S_CHANNEL"
  fi
else
  log_do "snap install microk8s ($MICROK8S_CHANNEL)"
  snap install microk8s --classic --channel="$MICROK8S_CHANNEL"
fi

# 3. Группы для пользователя ubuntu (если есть). Не падаем, если пользователя нет.
if id ubuntu >/dev/null 2>&1; then
  idempotent \
    "пользователь ubuntu в группе microk8s" \
    "id -nG ubuntu | grep -qw microk8s" \
    "usermod -a -G microk8s ubuntu && chown -f -R ubuntu /home/ubuntu/.kube || true"
fi

# 4. wait-ready перед enable аддонов
log_info "microk8s status --wait-ready (до 5 мин)"
if ! microk8s status --wait-ready --timeout 300 >/dev/null 2>&1; then
  log_error "microk8s не вышел в ready"
  microk8s status || true
  exit 1
fi
log_ok "microk8s ready"

# 5. Аддоны (microk8s enable идемпотентен — повторный enable выводит "is already enabled")
for addon in "${ADDONS[@]}"; do
  if microk8s status --addon "$addon" 2>/dev/null | grep -q enabled; then
    log_skip "addon: $addon"
  else
    log_do "addon: $addon"
    if ! microk8s enable "$addon"; then
      log_error "Не удалось включить addon: $addon"
      exit 1
    fi
  fi
done

# 6. Повторный wait-ready после enable
log_info "microk8s status --wait-ready после enable"
microk8s status --wait-ready --timeout 180 >/dev/null 2>&1 || true

# 7. Sanity: kubectl видит ноду
NODE_STATUS=$(microk8s kubectl get node "$MASTER_HOSTNAME" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
if [ "$NODE_STATUS" = "True" ]; then
  log_ok "node $MASTER_HOSTNAME Ready"
else
  log_warn "node $MASTER_HOSTNAME не показывает Ready — проверьте 'microk8s kubectl get nodes'"
fi

print_summary

log_section "Следующий шаг"
cat <<EOF
1) На GPU-ноде:  ssh ${SSH_USER}@${GPU_HOST_IP} bash deploy/scripts/bootstrap-gpu-worker.sh
2) Затем здесь: GPU_WORKER_HOST=${SSH_USER}@${GPU_HOST_IP} bash $SCRIPT_DIR/join-cluster.sh
3) Сохранить kubeconfig в GitHub Secret KUBECONFIG_B64. Напечатано ниже:

${C_DIM}--- BEGIN KUBECONFIG_B64 ---${C_RESET}
$(microk8s config | base64)
${C_DIM}--- END KUBECONFIG_B64 ---${C_RESET}

Скопируйте между маркерами (без них) и положите в GitHub:
  Settings → Secrets and variables → Actions → New repository secret
  Name: KUBECONFIG_B64
EOF
