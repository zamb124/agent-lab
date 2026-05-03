#!/usr/bin/env bash
# Идемпотентный bootstrap GPU worker ноды (188.246.224.228).
# Запускать ПОД ROOT.
#
# Что делает:
#   1. hostname → gpu-worker
#   2. NVIDIA driver (если нет) — autoinstall + EXIT 10 (нужен reboot)
#   3. nvidia-container-toolkit
#   4. snap install microk8s
#
# Не делает: join к кластеру (это для join-cluster.sh на master) и enable gpu
# (включается с master через join-cluster.sh, чтобы избежать гонки).
#
# Exit codes:
#   0  — всё применено / уже было применено
#   10 — установлен NVIDIA driver, нужен REBOOT, после reboot запустить снова

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_root || exit 1

GPU_HOSTNAME="${GPU_HOSTNAME:-gpu-worker}"
# Должен совпадать с master (одна minor-версия на весь кластер). См. `snap info microk8s`.
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.33/stable}"

log_section "Bootstrap GPU worker (hostname=$GPU_HOSTNAME)"

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

# 3. nvidia-container-toolkit
if dpkg -l | grep -qE '^ii\s+nvidia-container-toolkit\s'; then
  log_skip "nvidia-container-toolkit"
else
  log_do "Установка nvidia-container-toolkit"
  distribution="$(. /etc/os-release; echo "$ID$VERSION_ID")"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list" \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -qq
  apt-get install -y nvidia-container-toolkit
fi

# 4. MicroK8s
idempotent \
  "snap install microk8s ($MICROK8S_CHANNEL)" \
  "snap list microk8s 2>/dev/null | grep -q microk8s" \
  "snap install microk8s --classic --channel=$MICROK8S_CHANNEL"

# Группа для пользователя ubuntu (если есть)
if id ubuntu >/dev/null 2>&1; then
  idempotent \
    "пользователь ubuntu в группе microk8s" \
    "id -nG ubuntu | grep -qw microk8s" \
    "usermod -a -G microk8s ubuntu || true"
fi

# 5. wait-ready
log_info "microk8s status --wait-ready (до 5 мин)"
if ! microk8s status --wait-ready --timeout 300 >/dev/null 2>&1; then
  log_warn "microk8s ещё не ready — это ожидаемо до join к кластеру"
fi

print_summary

log_section "Следующий шаг"
cat <<EOF
GPU нода готова к join. На master:
  ssh ${SSH_USER}@${MASTER_HOST_IP}
  GPU_WORKER_HOST=${SSH_USER}@${GPU_HOST_IP} bash deploy/scripts/join-cluster.sh
EOF
