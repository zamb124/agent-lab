#!/usr/bin/env bash
# Локальная проверка Reg.ru API перед deploy (read-only + опциональный write).
#
# Использование:
#   REGRU_USERNAME=... REGRU_PASSWORD=... bash deploy/scripts/test-regru-api.sh
#   REGRU_USERNAME=... REGRU_PASSWORD=... bash deploy/scripts/test-regru-api.sh --apply linnex.io @ 84.38.184.105
#
# Без --apply только читает: nop + get_resource_records, сверяет A-записи с EXPECTED_IP.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
# shellcheck source=_regru_api.sh
source "$SCRIPT_DIR/_regru_api.sh"

REGRU_API="https://api.reg.ru/api/regru2"
DOMAINS="${PLATFORM_BRAND_DOMAINS:-humanitec.ru linnex.io}"
SUBDOMAINS="${PLATFORM_BRAND_DNS_SUBDOMAINS:-@ www * api cdn livekit onlyoffice grafana}"
EXPECTED_IP="${PLATFORM_PUBLIC_IP:-84.38.184.105}"

require_command curl || exit 1
require_command python3 || exit 1
regru_require_credentials

APPLY=0
APPLY_DOMAIN=""
APPLY_SUBDOMAIN=""
APPLY_IP=""

if [ "${1:-}" = "--apply" ]; then
  if [ "$#" -ne 4 ]; then
    log_error "Использование: $0 --apply <domain> <subdomain> <ip>"
    exit 1
  fi
  APPLY=1
  APPLY_DOMAIN="$2"
  APPLY_SUBDOMAIN="$3"
  APPLY_IP="$4"
fi

log_section "1) Reg.ru API auth (nop)"
regru_nop
log_ok "auth OK (username=${REGRU_USERNAME})"

log_section "2) zone/get_resource_records"
DOMAINS_CSV=$(echo "$DOMAINS" | tr ' ' ',')
INPUT_DATA=$(regru_get_resource_records "$DOMAINS_CSV")
RECORDS_RESPONSE=$(regru_post "zone/get_resource_records" "$INPUT_DATA")
regru_assert_success "get_resource_records" "$RECORDS_RESPONSE"

python3 - "$RECORDS_RESPONSE" "$SUBDOMAINS" "$EXPECTED_IP" <<'PY'
import json
import sys

body = json.loads(sys.argv[1])
subdomains = sys.argv[2].split()
expected_ip = sys.argv[3]

domains = body.get("answer", {}).get("domains", [])
if not domains:
    print("ERROR: пустой answer.domains", file=sys.stderr)
    sys.exit(1)

mismatches = 0
for domain_block in domains:
    dname = domain_block.get("dname", "?")
    if domain_block.get("result") != "success":
        print(f"FAIL {dname}: {domain_block.get('error_code')} {domain_block.get('error_text')}")
        mismatches += 1
        continue

    a_by_sub = {}
    for rr in domain_block.get("rrs") or []:
        if rr.get("rectype") != "A":
            continue
        subname = rr.get("subname") or rr.get("subdomain") or "@"
        a_by_sub[subname] = rr.get("content")

    wildcard_ip = a_by_sub.get("*")

    print(f"\n{dname}:")
    for sub in subdomains:
        current = a_by_sub.get(sub)
        if current == expected_ip:
            print(f"  OK  {sub:12} A → {current}")
            continue
        if sub != "@" and current is None and wildcard_ip == expected_ip:
            print(f"  OK  {sub:12} A → {expected_ip} (via *)")
            continue
        if current is None:
            print(f"  MISS {sub:11} A — нет записи (ожидается {expected_ip})")
            mismatches += 1
        else:
            print(f"  BAD {sub:12} A → {current} (ожидается {expected_ip})")
            mismatches += 1

if mismatches:
    print(f"\nИтого: {mismatches} расхождений с {expected_ip}", file=sys.stderr)
    sys.exit(1)
print(f"\nИтого: все проверяемые A-записи → {expected_ip}")
PY

log_ok "DNS records match ${EXPECTED_IP}"

if [ "$APPLY" = "1" ]; then
  log_section "3) zone/add_alias (write test)"
  log_do "${APPLY_SUBDOMAIN}.${APPLY_DOMAIN} → ${APPLY_IP}"
  APPLY_RESPONSE=$(regru_add_alias "$APPLY_DOMAIN" "$APPLY_SUBDOMAIN" "$APPLY_IP")
  regru_assert_success "${APPLY_DOMAIN}/${APPLY_SUBDOMAIN}" "$APPLY_RESPONSE"
  log_ok "add_alias OK"
fi

print_summary
