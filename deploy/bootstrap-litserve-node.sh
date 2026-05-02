#!/usr/bin/env bash
# Первичная подготовка хоста только под provider_litserve (нода B).
# Запуск на целевом сервере: bash deploy/bootstrap-litserve-node.sh
# Переменные окружения:
#   MAIN_PLATFORM_HOST — IPv4 основного сервера (84.38.184.105), для ufw allow from.

set -euo pipefail

MAIN_PLATFORM_HOST="${MAIN_PLATFORM_HOST:-84.38.184.105}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-plugin ufw curl jq ca-certificates

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
