#!/usr/bin/env bash
# Идемпотентная настройка DNS A-записей для platform brand apex-доменов в Reg.ru.
#
# Использование:
#   REGRU_USERNAME=... REGRU_PASSWORD=... \
#   bash deploy/scripts/setup-brand-dns.sh [public_ip]
#
# По умолчанию: humanitec.ru и linnex.io (@, *, livekit, onlyoffice, grafana).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

PUBLIC_IP="${1:-84.38.184.105}"
REGRU_USERNAME="${REGRU_USERNAME:-}"
REGRU_PASSWORD="${REGRU_PASSWORD:-}"

if [ -z "$REGRU_USERNAME" ] || [ -z "$REGRU_PASSWORD" ]; then
  log_error "Требуются REGRU_USERNAME и REGRU_PASSWORD"
  exit 1
fi

DOMAINS="${PLATFORM_BRAND_DOMAINS:-humanitec.ru linnex.io}"
SUBDOMAINS="${PLATFORM_BRAND_DNS_SUBDOMAINS:-@ * livekit onlyoffice grafana}"
DNS_TTL="${DNS_TTL:-300}"
REGRU_API="https://api.reg.ru/api/regru2"

require_command curl || exit 1

regru_update_a() {
  local domain="$1"
  local subdomain="$2"
  local ip="$3"
  log_do "Reg.ru: ${subdomain}.${domain} → $ip"
  local response
  response=$(curl -fsS --max-time 30 \
    -X POST "${REGRU_API}/zone/update_record" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"${REGRU_USERNAME}\",
      \"password\": \"${REGRU_PASSWORD}\",
      \"domains\": [{\"dname\": \"${domain}\"}],
      \"subdomain\": \"${subdomain}\",
      \"record_type\": \"A\",
      \"content\": \"${ip}\"
    }")
  if echo "$response" | grep -q '"result":"success"'; then
    log_ok "${subdomain}.${domain} → $ip"
  else
    log_error "Reg.ru API error для ${domain}/${subdomain}: $response"
    return 1
  fi
}

log_section "DNS platform brands → $PUBLIC_IP"
for domain in $DOMAINS; do
  for subdomain in $SUBDOMAINS; do
    regru_update_a "$domain" "$subdomain" "$PUBLIC_IP"
  done
done

log_ok "DNS A-записи обновлены (TTL=${DNS_TTL}s)"
print_summary
