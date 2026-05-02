#!/usr/bin/env bash
# Первичная подготовка хоста только под provider_litserve (нода B).
# Запуск на целевом сервере: bash deploy/bootstrap-litserve-node.sh
# Job GitHub Actions deploy-litserve вызывает скрипт автоматически, если на хосте нет docker.
# Переменные окружения:
#   MAIN_PLATFORM_HOST — IPv4 основного сервера (84.38.184.105), для ufw allow from.

set -euo pipefail

MAIN_PLATFORM_HOST="${MAIN_PLATFORM_HOST:-84.38.184.105}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw jq

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

mkdir -p /opt/agent-lab/data/provider_litserve
mkdir -p /opt/agent-lab/data/hf_cache
mkdir -p /opt/agent-lab/deploy/observability
mkdir -p /opt/agent-lab/migrations/postgres

ufw allow 22/tcp
ufw allow from "${MAIN_PLATFORM_HOST}" to any port 8014 proto tcp
ufw --force enable

systemctl enable docker
systemctl start docker

echo "bootstrap-litserve-node: OK (docker + ufw 8014 from ${MAIN_PLATFORM_HOST})"
echo "Для GPU на этой машине см. deploy/LITSERVE_GPU_HOST.md и deploy/bootstrap-litserve-node-gpu.sh (или GitHub Deploy: install_litserve_gpu_stack)"
