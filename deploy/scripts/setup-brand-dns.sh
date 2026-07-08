#!/usr/bin/env bash
# Идемпотентная настройка DNS A-записей для platform brand apex-доменов в Reg.ru.
#
# Использование:
#   REGRU_USERNAME=... REGRU_PASSWORD=... \
#   bash deploy/scripts/setup-brand-dns.sh [public_ip]
#
# По умолчанию: humanitec.ru и linnex.io (@, *, api, cdn, livekit, onlyoffice, grafana).

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
SUBDOMAINS="${PLATFORM_BRAND_DNS_SUBDOMAINS:-@ * api cdn livekit onlyoffice grafana}"
REGRU_API="https://api.reg.ru/api/regru2"

require_command curl || exit 1
require_command python3 || exit 1

regru_post() {
  local method="$1"
  local input_data="$2"
  curl -fsS --max-time 30 \
    -X POST "${REGRU_API}/${method}" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "username=${REGRU_USERNAME}" \
    --data-urlencode "password=${REGRU_PASSWORD}" \
    --data-urlencode "input_format=json" \
    --data-urlencode "input_data=${input_data}"
}

regru_assert_success() {
  local context="$1"
  local response="$2"
  python3 -c "
import json, sys
body = json.loads(sys.argv[1])
if body.get('result') != 'success':
    print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)
" "$response" || {
    log_error "Reg.ru API error для ${context}: ${response}"
    return 1
  }
}

log_section "Reg.ru API auth (nop)"
NOP_RESPONSE=$(regru_post "nop" '{"output_content_type":"plain"}')
regru_assert_success "nop" "$NOP_RESPONSE"
log_ok "Reg.ru API auth OK"

regru_add_a() {
  local domain="$1"
  local subdomain="$2"
  local ip="$3"
  log_do "Reg.ru: ${subdomain}.${domain} → $ip"
  local input_data response
  input_data=$(python3 -c "
import json
print(json.dumps({
    'domains': [{'dname': '${domain}'}],
    'subdomain': '${subdomain}',
    'ipaddr': '${ip}',
    'output_content_type': 'plain',
}))
")
  response=$(regru_post "zone/add_alias" "$input_data")
  regru_assert_success "${domain}/${subdomain}" "$response"
  log_ok "${subdomain}.${domain} → $ip"
}

log_section "DNS platform brands → $PUBLIC_IP"
for domain in $DOMAINS; do
  for subdomain in $SUBDOMAINS; do
    regru_add_a "$domain" "$subdomain" "$PUBLIC_IP"
  done
done

log_ok "DNS A-записи обновлены"
print_summary
