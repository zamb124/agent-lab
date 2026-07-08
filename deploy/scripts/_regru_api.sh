#!/usr/bin/env bash
# Общие helper'ы для Reg.ru API v2 (form-urlencoded + input_data JSON).

regru_require_credentials() {
  REGRU_USERNAME="${REGRU_USERNAME:-}"
  REGRU_PASSWORD="${REGRU_PASSWORD:-}"
  if [ -z "$REGRU_USERNAME" ] || [ -z "$REGRU_PASSWORD" ]; then
    log_error "Требуются REGRU_USERNAME и REGRU_PASSWORD"
    exit 1
  fi
}

regru_post() {
  local method="$1"
  local input_data="$2"
  curl -fsS --max-time 30 \
    -X POST "${REGRU_API}/$method" \
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
    code = body.get('error_code', '')
    if code == 'ACCESS_DENIED_FROM_IP':
        print('Reg.ru: ACCESS_DENIED_FROM_IP — API доступен только с IP из whitelist.', file=sys.stderr)
        print('Личный кабинет Reg.ru → Настройки → API → разрешённые IP (или отключить ограничение).', file=sys.stderr)
    print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)
" "$response" || {
    log_error "Reg.ru API error для ${context}: ${response}"
    return 1
  }
}

regru_nop() {
  local response
  response=$(regru_post "nop" '{"output_content_type":"plain"}')
  regru_assert_success "nop" "$response"
}

regru_get_resource_records() {
  local domains_csv="$1"
  python3 -c "
import json, sys
domains = [{'dname': d.strip()} for d in sys.argv[1].split(',') if d.strip()]
print(json.dumps({
    'domains': domains,
    'output_content_type': 'plain',
}))
" "$domains_csv"
}

regru_add_alias() {
  local domain="$1"
  local subdomain="$2"
  local ipaddr="$3"
  local input_data
  input_data=$(python3 -c "
import json
print(json.dumps({
    'domains': [{'dname': '${domain}'}],
    'subdomain': '${subdomain}',
    'ipaddr': '${ipaddr}',
    'output_content_type': 'plain',
}))
")
  regru_post "zone/add_alias" "$input_data"
}
