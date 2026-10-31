#!/usr/bin/env bash
# Обновляет DNS A-записи linnex.io на IP новой ноды и переезжает hostNetwork-сервисам.
# Нужен при переносе livekit/coturn на другую ноду (они слушают на real IP хоста).
#
# Использование:
#   REGRU_USERNAME=... REGRU_PASSWORD=... \
#   bash deploy/scripts/rebind-public-node.sh <new_node_name> <new_node_public_ip>
#
# Аргументы:
#   new_node_name      — kubernetes.io/hostname новой ноды (например master или gpu-worker)
#   new_node_public_ip — публичный IPv4 новой ноды
#
# Требования:
#   - curl (для Reg.ru API)
#   - kubectl (или microk8s kubectl)
#   - helm (или microk8s helm3)
#   - REGRU_USERNAME, REGRU_PASSWORD (Reg.ru API credentials)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

NEW_NODE="${1:-}"
NEW_IP="${2:-}"

if [ -z "$NEW_NODE" ] || [ -z "$NEW_IP" ]; then
  echo "Использование: $0 <new_node_name> <new_node_public_ip>"
  echo "  Переменные окружения: REGRU_USERNAME, REGRU_PASSWORD"
  exit 1
fi

REGRU_USERNAME="${REGRU_USERNAME:-}"
REGRU_PASSWORD="${REGRU_PASSWORD:-}"

if [ -z "$REGRU_USERNAME" ] || [ -z "$REGRU_PASSWORD" ]; then
  log_error "Требуются REGRU_USERNAME и REGRU_PASSWORD"
  exit 1
fi

REGRU_API="https://api.reg.ru/api/regru2"
# shellcheck source=_regru_api.sh
source "$SCRIPT_DIR/_regru_api.sh"

require_command curl || exit 1
require_command python3 || exit 1

log_section "Обновление DNS $DOMAIN → $NEW_IP (через Reg.ru API)"

regru_update_a() {
  local subdomain="$1"
  local ip="$2"
  log_do "Reg.ru: ${subdomain}.${DOMAIN} → $ip"
  local response
  response=$(regru_add_alias "$DOMAIN" "$subdomain" "$ip")
  regru_assert_success "${DOMAIN}/${subdomain}" "$response"
  log_ok "${subdomain}.${DOMAIN} → $ip"
}

PLATFORM_NS="${PLATFORM_NS:-platform}"
HELM_CHART="${HELM_CHART:-./deploy/helm/agent-lab}"
HELM_RELEASE="${HELM_RELEASE:-agent-lab}"
DOMAIN="${DOMAIN:-linnex.io}"
DNS_TTL=300

K="$KUBECTL"
H="$HELM"

# Обновляем A-записи: apex + wildcard + livekit
regru_update_a "@" "$NEW_IP"
regru_update_a "*" "$NEW_IP"
regru_update_a "livekit" "$NEW_IP"

log_info "DNS TTL = ${DNS_TTL}s. Ждём распространения..."
sleep "$DNS_TTL"

log_section "Helm upgrade: перенос hostNetwork-сервисов → $NEW_NODE"
log_do "helm upgrade --reuse-values --set livekit.nodeName=$NEW_NODE --set livekitEgress.nodeName=$NEW_NODE --set coturn.nodeName=$NEW_NODE"
$H upgrade --install "$HELM_RELEASE" "$HELM_CHART" \
  --namespace "$PLATFORM_NS" \
  --reuse-values \
  --set "livekit.nodeName=${NEW_NODE}" \
  --set "livekitEgress.nodeName=${NEW_NODE}" \
  --set "coturn.nodeName=${NEW_NODE}" \
  --wait --timeout 10m

log_section "Финальная проверка"
log_do "cluster-health.sh"
bash "$SCRIPT_DIR/cluster-health.sh"

log_ok "hostNetwork-сервисы перенесены на ноду $NEW_NODE (IP: $NEW_IP)"
