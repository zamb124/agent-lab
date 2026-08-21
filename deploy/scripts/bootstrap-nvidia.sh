#!/usr/bin/env bash
# NVIDIA driver + nvidia-container-toolkit + containerd drop-in для MicroK8s.
# Запускать под root на master (GPU на той же машине). Вызывает bootstrap-master.sh.
#
# Exit codes:
#   0  — применено / уже было
#   10 — driver поставлен, нужен REBOOT, после reboot запустить снова

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

CONTAINERD_DROPIN_DIR="${CONTAINERD_DROPIN_DIR:-/etc/containerd/conf.d}"

log_section "NVIDIA driver + container toolkit"

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
  log_warn "После reboot: снова bash deploy/scripts/bootstrap-master.sh"
  exit 10
fi

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

mkdir -p "$CONTAINERD_DROPIN_DIR"
DROPIN_FILE="$CONTAINERD_DROPIN_DIR/99-nvidia.toml"
TEMPLATE_FILE="/var/snap/microk8s/current/args/containerd-template.toml"

if [ ! -f "$TEMPLATE_FILE" ]; then
  log_info "$TEMPLATE_FILE ещё нет — drop-in после установки MicroK8s (повторный вызов этого скрипта)"
  exit 0
fi

DROPIN_NEEDS_REGEN=1
if [ -s "$DROPIN_FILE" ] \
    && grep -q 'BinaryName.*nvidia-container-runtime' "$DROPIN_FILE" 2>/dev/null \
    && ! grep -qE '^[[:space:]]*disabled_plugins' "$DROPIN_FILE" 2>/dev/null; then
  log_skip "nvidia containerd drop-in $DROPIN_FILE"
  DROPIN_NEEDS_REGEN=0
fi
if [ "$DROPIN_NEEDS_REGEN" = "1" ]; then
  log_do "nvidia-ctk runtime configure (drop-in $DROPIN_FILE)"
  nvidia-ctk runtime configure --runtime=containerd --set-as-default --cdi.enabled
  log_do "очистка drop-in от disabled_plugins"
  sed -i '/^[[:space:]]*disabled_plugins[[:space:]]*=/d' "$DROPIN_FILE"
fi

if grep -qE '^imports[[:space:]]*=' "$TEMPLATE_FILE"; then
  log_skip "imports в $TEMPLATE_FILE"
else
  log_do "добавить imports = [\"$CONTAINERD_DROPIN_DIR/*.toml\"] в начало $TEMPLATE_FILE"
  sed -i "1i imports = [\"${CONTAINERD_DROPIN_DIR}/*.toml\"]" "$TEMPLATE_FILE"
fi

log_do "перезапуск snap.microk8s.daemon-containerd"
systemctl restart snap.microk8s.daemon-containerd
sleep 5

if microk8s ctr --address /var/snap/microk8s/common/run/containerd.sock plugins ls 2>/dev/null \
    | awk '$1 ~ /^io\.containerd\.grpc\.v1$/ && $2 == "cri" && $NF == "ok" {found=1} END {exit found?0:1}'; then
  log_ok "containerd CRI plugin: ok"
else
  log_warn "CRI plugin не в состоянии ok — journalctl -u snap.microk8s.daemon-containerd"
fi
