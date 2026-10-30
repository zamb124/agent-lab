#!/usr/bin/env bash
# Идемпотентная настройка DNS A-записей для platform brand apex-доменов в Reg.ru.
#
# Использование:
#   REGRU_USERNAME=... REGRU_PASSWORD=... \
#   bash deploy/scripts/setup-brand-dns.sh [public_ip]
#
# По умолчанию: humanitec.ru и linnex.io (@, www, *, api, cdn, livekit, onlyoffice, grafana).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
# shellcheck source=_regru_api.sh
source "$SCRIPT_DIR/_regru_api.sh"

PUBLIC_IP="${1:-77.91.94.127}"
REGRU_API="https://api.reg.ru/api/regru2"

require_command curl || exit 1
require_command python3 || exit 1
regru_require_credentials

DOMAINS="${PLATFORM_BRAND_DOMAINS:-humanitec.ru linnex.io}"
# Нельзя `for x in $SUBDOMAINS` с literal `*` — bash glob развернёт файлы в cwd (ConfigMap mount).
if [ -n "${PLATFORM_BRAND_DNS_SUBDOMAINS:-}" ]; then
  IFS=',' read -r -a SUBDOMAINS_LIST <<< "${PLATFORM_BRAND_DNS_SUBDOMAINS}"
else
  SUBDOMAINS_LIST=( '@' 'www' '*' api cdn livekit onlyoffice grafana )
fi

log_section "Reg.ru API auth (nop)"
regru_nop
log_ok "Reg.ru API auth OK"

regru_add_a() {
  local domain="$1"
  local subdomain="$2"
  local ip="$3"
  log_do "Reg.ru: ${subdomain}.${domain} → $ip"
  local response
  if [ "$subdomain" = "www" ]; then
    # Reg.ru parking: add_alias не перезаписывает существующую A www → remove + add.
    response=$(regru_set_a_record "$domain" "$subdomain" "$ip")
  else
    response=$(regru_add_alias "$domain" "$subdomain" "$ip")
  fi
  regru_assert_success "${domain}/${subdomain}" "$response"
  log_ok "${subdomain}.${domain} → $ip"
}

log_section "DNS platform brands → $PUBLIC_IP"
for domain in $DOMAINS; do
  for subdomain in "${SUBDOMAINS_LIST[@]}"; do
    regru_add_a "$domain" "$subdomain" "$PUBLIC_IP"
  done
done

log_ok "DNS A-записи обновлены"
print_summary
