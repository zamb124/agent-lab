#!/usr/bin/env bash
# Драйвер NVIDIA + NVIDIA Container Toolkit для ноды с docker-compose-litserve.yaml.
# Идempotent: повторный запуск допустим после reboot.
#
# Выход 10 — после установки драйвера нужен reboot; выполните reboot и снова job deploy-litserve (без необходимости снова ставить toolkit).
#
# Вызывается CI при INSTALL_LITSERVE_GPU_STACK=true или вручную:
#   sudo bash deploy/bootstrap-litserve-node-gpu.sh

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "bootstrap-litserve-node-gpu: run as root" >&2
    exit 1
  fi
}

nv_smi_ok() {
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

install_driver_if_needed() {
  if nv_smi_ok; then
    echo "bootstrap-litserve-node-gpu: nvidia-smi уже доступен"
    return 0
  fi

  apt-get update -qq
  apt-get install -y -qq ubuntu-drivers-common ca-certificates curl gnupg

  ubuntu-drivers install

  if nv_smi_ok; then
    echo "bootstrap-litserve-node-gpu: драйвер установлен, nvidia-smi OK"
    return 0
  fi

  echo "bootstrap-litserve-node-gpu: требуется REBOOT; после перезагрузки запустите job ещё раз" >&2
  return 10
}

install_nvidia_container_toolkit() {
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list

  apt-get update -qq
  apt-get install -y -qq nvidia-container-toolkit

  if command -v nvidia-ctk >/dev/null 2>&1; then
    nvidia-ctk runtime configure --runtime=docker || true
  fi

  systemctl restart docker
}

main() {
  require_root

  drv_rc=0
  install_driver_if_needed || drv_rc=$?

  if [ "$drv_rc" -eq 10 ]; then
    exit 10
  fi
  if [ "$drv_rc" -ne 0 ]; then
    exit "$drv_rc"
  fi

  install_nvidia_container_toolkit

  echo "bootstrap-litserve-node-gpu: OK (driver + nvidia-container-toolkit, docker restarted)"
}

main "$@"
