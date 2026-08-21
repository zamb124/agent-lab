#!/usr/bin/env bash
# Идемпотентный bootstrap единственной ноды кластера (hostname=master, GPU на ней же).
# Шаги: harden-ssh, NVIDIA, snap microk8s, аддоны, лейбл accelerator=nvidia-gpu.
# Taint dedicated=gpu не ставится — иначе не-GPU поды не встанут.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

MASTER_HOSTNAME="${MASTER_HOSTNAME:-master}"
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.35/stable}"
ADDONS_CORE=(dns hostpath-storage ingress cert-manager)
ADDONS_COMMUNITY=(portainer)

log_section "Bootstrap master (hostname=$MASTER_HOSTNAME)"

bash "$SCRIPT_DIR/harden-ssh.sh" || exit 1

disable_host_firewall

idempotent \
  "hostname = $MASTER_HOSTNAME" \
  "[ \"$(hostname)\" = '$MASTER_HOSTNAME' ]" \
  "hostnamectl set-hostname '$MASTER_HOSTNAME'"
idempotent \
  "/etc/hosts содержит $MASTER_HOSTNAME" \
  "grep -qE '[[:space:]]${MASTER_HOSTNAME}([[:space:]]|$)' /etc/hosts" \
  "if grep -q '^127.0.1.1' /etc/hosts; then sed -i 's/^127.0.1.1.*/127.0.1.1 ${MASTER_HOSTNAME}/' /etc/hosts; else printf '127.0.1.1 %s\n' '${MASTER_HOSTNAME}' >> /etc/hosts; fi"

bash "$SCRIPT_DIR/bootstrap-nvidia.sh"
nvidia_rc=$?
if [ "$nvidia_rc" -eq 10 ]; then
  exit 10
fi
if [ "$nvidia_rc" -ne 0 ]; then
  exit "$nvidia_rc"
fi

if ! grep -q '^precedence ::ffff:0:0/96  100' /etc/gai.conf 2>/dev/null; then
  log_do "IPv4 precedence in /etc/gai.conf (registry.k8s.io CloudFront IPv6 hang)"
  echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf
else
  log_skip "IPv4 precedence в /etc/gai.conf"
fi

if ! command -v snap >/dev/null 2>&1; then
  log_do "apt-get install snapd"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y snapd
  systemctl enable --now snapd
  if [ ! -e /snap ]; then
    ln -s /var/lib/snapd/snap /snap
  fi
  export PATH="/snap/bin:${PATH}"
fi

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
export PATH="/snap/bin:${PATH}"

if id ubuntu >/dev/null 2>&1; then
  idempotent \
    "пользователь ubuntu в группе microk8s" \
    "id -nG ubuntu | grep -qw microk8s" \
    "usermod -a -G microk8s ubuntu && chown -f -R ubuntu /home/ubuntu/.kube || true"
fi

log_info "microk8s status --wait-ready (до 5 мин)"
if ! microk8s status --wait-ready --timeout 300 >/dev/null 2>&1; then
  log_error "microk8s не вышел в ready"
  microk8s status || true
  exit 1
fi
log_ok "microk8s ready"

bash "$SCRIPT_DIR/bootstrap-nvidia.sh" || exit 1

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

if microk8s status --addon community 2>/dev/null | grep -q enabled; then
  log_skip "community repository"
else
  log_do "microk8s enable community"
  microk8s enable community
fi
for addon in "${ADDONS_COMMUNITY[@]}"; do
  if microk8s status --addon "$addon" 2>/dev/null | grep -q enabled; then
    log_skip "community addon: $addon"
  else
    log_do "community addon: $addon"
    if ! microk8s enable "$addon"; then
      log_warn "Не удалось включить community addon: $addon"
    fi
  fi
done

log_info "microk8s status --wait-ready после enable"
microk8s status --wait-ready --timeout 180 >/dev/null 2>&1 || true

NODE_STATUS=$(microk8s kubectl get node "$MASTER_HOSTNAME" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
if [ "$NODE_STATUS" = "True" ]; then
  log_ok "node $MASTER_HOSTNAME Ready"
else
  log_warn "node $MASTER_HOSTNAME не показывает Ready — microk8s kubectl get nodes"
fi

log_do "label node $MASTER_HOSTNAME ${GPU_NODE_LABEL_KEY}=${GPU_NODE_LABEL_VALUE}"
microk8s kubectl label node "$MASTER_HOSTNAME" \
  "${GPU_NODE_LABEL_KEY}=${GPU_NODE_LABEL_VALUE}" --overwrite

print_summary

log_section "Следующий шаг"
cat <<EOF
Kubeconfig для CI (server = https://${MASTER_HOST_IP}:16443, не 127.0.0.1):

  bash deploy/scripts/kubeconfig-for-github-actions.sh
  gh secret set KUBECONFIG_B64 --body "\$(bash deploy/scripts/kubeconfig-for-github-actions.sh)"

Не печатать kubeconfig в чат. Затем: make k8s-secrets-sync && make k8s-deploy IMAGE_TAG=<sha>
EOF
