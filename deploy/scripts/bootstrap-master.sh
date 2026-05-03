#!/usr/bin/env bash
# Идемпотентный bootstrap master ноды MicroK8s. Запускать под root на 84.38.184.105.
# Шаги: hostname=master, snap microk8s, аддоны (dns, hostpath-storage, ingress,
# cert-manager, community/portainer), kubeconfig в base64 для GitHub Secret KUBECONFIG_B64.
# Не делает join GPU-ноды — см. join-cluster.sh.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

MASTER_HOSTNAME="${MASTER_HOSTNAME:-master}"
# Канал K8s единый на всех нодах кластера.
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.35/stable}"
ADDONS_CORE=(dns hostpath-storage ingress cert-manager)
# portainer: NodePort http://<master>:30777, https 30779.
ADDONS_COMMUNITY=(portainer)

log_section "Bootstrap master ноды (hostname=$MASTER_HOSTNAME)"

disable_host_firewall

# 1. hostname
idempotent \
  "hostname = $MASTER_HOSTNAME" \
  "[ \"$(hostname)\" = '$MASTER_HOSTNAME' ]" \
  "hostnamectl set-hostname '$MASTER_HOSTNAME'"

# 2. snap MicroK8s — установка / refresh на канал кластера.
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

# 5. Core-аддоны.
for addon in "${ADDONS_CORE[@]}"; do
  if microk8s status --addon "$addon" 2>/dev/null | grep -q enabled; then
    log_skip "core addon: $addon"
  else
    log_do "core addon: $addon"
    if ! microk8s enable "$addon"; then
      log_error "Не удалось включить core addon: $addon"
      exit 1
    fi
  fi
done

# 5b. Community repository + community-аддоны.
if microk8s status --addon community 2>/dev/null | grep -q enabled; then
  log_skip "community repository"
else
  log_do "microk8s enable community (для community-аддонов)"
  microk8s enable community
fi
for addon in "${ADDONS_COMMUNITY[@]}"; do
  if microk8s status --addon "$addon" 2>/dev/null | grep -q enabled; then
    log_skip "community addon: $addon"
  else
    log_do "community addon: $addon"
    if ! microk8s enable "$addon"; then
      log_warn "Не удалось включить community addon: $addon (пропускаем — не критично)"
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
