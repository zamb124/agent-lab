#!/usr/bin/env bash
# Выполнить на основном сервере (нода A), где крутится docker-compose-prod.
# Открывает Postgres и Redis только для IP ноды litserve (после публикации портов в compose).
#
#   export LITSERVE_NODE_IP=188.246.224.228
#   sudo bash deploy/firewall-main-platform-for-litserve-node.sh
#
# Требуется ufw; при другом фаерволе перенесите правила вручную.

set -euo pipefail

LITSERVE_NODE_IP="${LITSERVE_NODE_IP:?set LITSERVE_NODE_IP to litserve host IPv4}"

ufw allow from "${LITSERVE_NODE_IP}" to any port 5432 proto tcp
ufw allow from "${LITSERVE_NODE_IP}" to any port 6379 proto tcp
ufw reload || true

echo "firewall-main-platform-for-litserve-node: OK (5432, 6379 from ${LITSERVE_NODE_IP})"
