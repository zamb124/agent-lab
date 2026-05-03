#!/usr/bin/env bash
# Идемпотентный bootstrap GPU worker ноды (188.246.224.228). Запускать под root.
# Шаги: hostname=gpu-worker, NVIDIA driver, nvidia-container-toolkit, snap microk8s,
# nvidia-ctk drop-in /etc/containerd/conf.d/99-nvidia.toml + imports в containerd-template.
# Join к кластеру делает join-cluster.sh; nvidia-device-plugin DaemonSet ставит Helm-чарт.
#
# Exit codes:
#   0  — всё применено / уже было применено
#   10 — установлен NVIDIA driver, требуется REBOOT, после reboot запустить снова

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

GPU_HOSTNAME="${GPU_HOSTNAME:-gpu-worker}"
# Канал K8s единый на всех нодах кластера; должен совпадать с bootstrap-master.sh.
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.35/stable}"
CONTAINERD_DROPIN_DIR="${CONTAINERD_DROPIN_DIR:-/etc/containerd/conf.d}"

log_section "Bootstrap GPU worker (hostname=$GPU_HOSTNAME)"

disable_host_firewall

# 1. hostname
idempotent \
  "hostname = $GPU_HOSTNAME" \
  "[ \"$(hostname)\" = '$GPU_HOSTNAME' ]" \
  "hostnamectl set-hostname '$GPU_HOSTNAME'"

# 2. NVIDIA driver
log_info "Проверка NVIDIA driver"
if nvidia-smi >/dev/null 2>&1; then
  log_skip "NVIDIA driver установлен и работает"
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
else
  log_do "Установка NVIDIA driver через ubuntu-drivers autoinstall"
  apt-get update -qq
  apt-get install -y ubuntu-drivers-common
  if ! ubuntu-drivers autoinstall; then
    log_error "ubuntu-drivers autoinstall упал"
    exit 1
  fi
  log_warn "NVIDIA driver установлен. Требуется REBOOT перед продолжением."
  log_warn "После 'reboot': снова запустите этот скрипт."
  exit 10
fi

# 3. nvidia-container-toolkit из NVIDIA stable/deb.
if dpkg -l 2>/dev/null | grep -qE '^ii\s+nvidia-container-toolkit\s'; then
  log_skip "nvidia-container-toolkit"
else
  log_do "Установка nvidia-container-toolkit (NVIDIA stable/deb)"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -qq
  apt-get install -y nvidia-container-toolkit
fi

# 4. MicroK8s — установка / refresh на канал кластера.
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

# Группа для пользователя ubuntu (если есть)
if id ubuntu >/dev/null 2>&1; then
  idempotent \
    "пользователь ubuntu в группе microk8s" \
    "id -nG ubuntu | grep -qw microk8s" \
    "usermod -a -G microk8s ubuntu || true"
fi

# 5. wait-ready (до join — kubelet может ещё не быть Ready).
log_info "microk8s status --wait-ready (до 5 мин)"
if ! microk8s status --wait-ready --timeout 300 >/dev/null 2>&1; then
  log_warn "microk8s ещё не ready — ожидается до join к кластеру"
fi

# 6. NVIDIA runtime в containerd через drop-in.
# nvidia-ctk пишет drop-in в /etc/containerd/conf.d/99-nvidia.toml; в containerd-template
# добавляем imports = ["/etc/containerd/conf.d/*.toml"]; из drop-in убираем
# disabled_plugins (CRI нужен kubelet'у).
mkdir -p "$CONTAINERD_DROPIN_DIR"
DROPIN_FILE="$CONTAINERD_DROPIN_DIR/99-nvidia.toml"
TEMPLATE_FILE="/var/snap/microk8s/current/args/containerd-template.toml"

DROPIN_NEEDS_REGEN=1
if [ -s "$DROPIN_FILE" ] \
    && grep -q 'BinaryName.*nvidia-container-runtime' "$DROPIN_FILE" 2>/dev/null \
    && ! grep -qE '^[[:space:]]*disabled_plugins' "$DROPIN_FILE" 2>/dev/null; then
  log_skip "nvidia containerd drop-in $DROPIN_FILE (clean, без disabled_plugins)"
  DROPIN_NEEDS_REGEN=0
fi
if [ "$DROPIN_NEEDS_REGEN" = "1" ]; then
  log_do "nvidia-ctk runtime configure (drop-in $DROPIN_FILE)"
  nvidia-ctk runtime configure --runtime=containerd --set-as-default --cdi.enabled
  log_do "очистка drop-in от disabled_plugins (CRI plugin нужен kubelet'у)"
  sed -i '/^[[:space:]]*disabled_plugins[[:space:]]*=/d' "$DROPIN_FILE"
fi

if [ -f "$TEMPLATE_FILE" ]; then
  if grep -qE '^imports[[:space:]]*=' "$TEMPLATE_FILE"; then
    log_skip "imports в $TEMPLATE_FILE"
  else
    log_do "добавить imports = [\"$CONTAINERD_DROPIN_DIR/*.toml\"] в начало $TEMPLATE_FILE"
    sed -i "1i imports = [\"${CONTAINERD_DROPIN_DIR}/*.toml\"]" "$TEMPLATE_FILE"
  fi
else
  log_warn "$TEMPLATE_FILE отсутствует — microk8s ещё не запустился; повторите bootstrap после microk8s start"
fi

log_do "перезапуск snap.microk8s.daemon-containerd"
systemctl restart snap.microk8s.daemon-containerd
sleep 5

# 7. Проверка CRI plugin (`io.containerd.grpc.v1   cri   ...   ok`).
if microk8s ctr --address /var/snap/microk8s/common/run/containerd.sock plugins ls 2>/dev/null \
    | awk '$1 ~ /^io\.containerd\.grpc\.v1$/ && $2 == "cri" && $NF == "ok" {found=1} END {exit found?0:1}'; then
  log_ok "containerd CRI plugin: ok"
else
  log_warn "CRI plugin не в состоянии ok — проверьте journalctl -u snap.microk8s.daemon-containerd"
fi

print_summary

log_section "Следующий шаг"
cat <<EOF
GPU нода готова к join. На master:
  ssh ${SSH_USER}@${MASTER_HOST_IP}
  GPU_WORKER_HOST=${SSH_USER}@${GPU_HOST_IP} bash /root/agent-lab-deploy/scripts/join-cluster.sh

NVIDIA k8s-device-plugin DaemonSet ставится Helm-чартом agent-lab:
  make k8s-deploy IMAGE_TAG=<sha>
EOF
