#!/usr/bin/env bash
# Выпуск и автоматическое продление wildcard-сертификата *.{domain}
# через acme.sh + reg.ru DNS API.
#
# Что делает:
#   1. Устанавливает acme.sh на сервере (если нет)
#   2. Выпускает *.{domain} + {domain} через DNS-01 (TXT-запись reg.ru добавляется автоматически)
#   3. Устанавливает сертификат как Kubernetes Secret
#   4. Настраивает cron для автопродления
#   5. Обновляет Ingress-ресурсы чтобы использовать wildcard-сертификат
#
# Требования:
#   - В conf.local.json: selectel.ip, selectel.login, ingress.domain
#   - REGRU_API_USERNAME и REGRU_API_PASSWORD (reg.ru → Профиль → API)
#     Передаются как переменные окружения ИЛИ берутся из conf.local.json:
#     "ingress": { "regru_api_user": "...", "regru_api_password": "..." }
#
# Запуск:
#   REGRU_API_USERNAME=user REGRU_API_PASSWORD=pass bash deploy/wildcard-tls.sh
#   ИЛИ добавьте regru_api_user/regru_api_password в conf.local.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONF_LOCAL_JSON="${CONF_LOCAL_JSON:-${PROJECT_ROOT}/conf.local.json}"

log() { printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Не найдена команда: $1" >&2; exit 1; }
}

require_cmd jq
require_cmd ssh

[[ -f "${CONF_LOCAL_JSON}" ]] || { echo "Не найден: ${CONF_LOCAL_JSON}" >&2; exit 1; }

IP="$(jq -er '.selectel.ip' "${CONF_LOCAL_JSON}")"
LOGIN="$(jq -er '.selectel.login' "${CONF_LOCAL_JSON}")"
SSH_PORT="$(jq -r '.selectel.ssh_port // "22"' "${CONF_LOCAL_JSON}")"
DOMAIN="$(jq -er '.ingress.domain' "${CONF_LOCAL_JSON}")"
EMAIL="$(jq -er '.ingress.email' "${CONF_LOCAL_JSON}")"

# Берём credentials из env или conf.local.json
REGRU_USER="${REGRU_API_USERNAME:-$(jq -r '.ingress.regru_api_user // ""' "${CONF_LOCAL_JSON}")}"
REGRU_PASS="${REGRU_API_PASSWORD:-$(jq -r '.ingress.regru_api_password // ""' "${CONF_LOCAL_JSON}")}"

if [[ -z "${REGRU_USER}" || -z "${REGRU_PASS}" ]]; then
  echo "ОШИБКА: Укажите REGRU_API_USERNAME и REGRU_API_PASSWORD." >&2
  echo "  Получить в reg.ru: Профиль → Настройки → API → Пароль для API" >&2
  echo "" >&2
  echo "  Вариант 1 (env):" >&2
  echo "    REGRU_API_USERNAME=user REGRU_API_PASSWORD=pass bash deploy/wildcard-tls.sh" >&2
  echo "" >&2
  echo "  Вариант 2 (conf.local.json):" >&2
  echo '    "ingress": { ..., "regru_api_user": "user", "regru_api_password": "pass" }' >&2
  exit 1
fi

log "Домен: ${DOMAIN} (wildcard: *.${DOMAIN})"
log "Сервер: ${LOGIN}@${IP}:${SSH_PORT}"

SSH="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10 -p ${SSH_PORT} ${LOGIN}@${IP}"

WILDCARD_SECRET="$(echo "${DOMAIN}" | tr '.' '-')-wildcard-tls"

# 1. Устанавливаем acme.sh если нет
log "Проверяем acme.sh"
${SSH} "which acme.sh >/dev/null 2>&1 || curl -fsSL https://get.acme.sh | sh -s email=${EMAIL}"

# 2. Выпускаем wildcard сертификат через DNS-01 reg.ru
log "Выпускаем *.${DOMAIN} через DNS-01 (reg.ru API)..."
${SSH} "
  export REGRU_API_USERNAME='${REGRU_USER}'
  export REGRU_API_PASSWORD='${REGRU_PASS}'

  ~/.acme.sh/acme.sh --issue \
    --dns dns_regru \
    -d '*.${DOMAIN}' \
    -d '${DOMAIN}' \
    --server letsencrypt \
    --force \
    || echo 'Сертификат уже актуален или ошибка выпуска'
"

# 3. Устанавливаем в Kubernetes Secret
log "Устанавливаем wildcard-сертификат в Kubernetes (secret: ${WILDCARD_SECRET})"
${SSH} "
  CERT_DIR=~/.acme.sh/\$(ls -t ~/.acme.sh/ | grep '^\*\.' | head -1)
  if [[ -z \"\$CERT_DIR\" ]]; then
    CERT_DIR=\"\$(ls -dt ~/.acme.sh/*${DOMAIN}* 2>/dev/null | head -1)\"
  fi

  if [[ -z \"\$CERT_DIR\" ]]; then
    echo 'ОШИБКА: сертификат не найден в ~/.acme.sh/' >&2
    exit 1
  fi

  echo \"Сертификат: \$CERT_DIR\"

  microk8s kubectl create secret tls ${WILDCARD_SECRET} \
    --cert=\$CERT_DIR/fullchain.cer \
    --key=\$CERT_DIR/${DOMAIN}.key \
    -n default \
    --dry-run=client -o yaml | microk8s kubectl apply -f -

  echo 'Wildcard Secret установлен'
"

# 4. Настраиваем cron для автопродления + обновление Kubernetes Secret
log "Настраиваем автопродление"
${SSH} "
  RENEW_SCRIPT='/usr/local/bin/acme-renew-k8s.sh'
  cat > \$RENEW_SCRIPT << 'SCRIPT'
#!/bin/bash
export REGRU_API_USERNAME='${REGRU_USER}'
export REGRU_API_PASSWORD='${REGRU_PASS}'

~/.acme.sh/acme.sh --renew -d '*.${DOMAIN}' --server letsencrypt || exit 0

CERT_DIR=\"\$(ls -dt ~/.acme.sh/*${DOMAIN}* 2>/dev/null | head -1)\"
microk8s kubectl create secret tls ${WILDCARD_SECRET} \
  --cert=\$CERT_DIR/fullchain.cer \
  --key=\$CERT_DIR/${DOMAIN}.key \
  -n default \
  --dry-run=client -o yaml | microk8s kubectl apply -f -

echo \"[\$(date)] Wildcard cert renewed and updated in K8s\" >> /var/log/acme-renew.log
SCRIPT
  chmod +x \$RENEW_SCRIPT

  # Cron: проверка обновления каждый день в 3:30
  (crontab -l 2>/dev/null | grep -v 'acme-renew-k8s'; echo '30 3 * * * /usr/local/bin/acme-renew-k8s.sh') | crontab -
  echo 'Cron настроен (проверка ежедневно в 03:30)'
"

# 5. Обновляем все Ingress чтобы использовали wildcard-сертификат
log "Обновляем Ingress для использования wildcard-сертификата"

# Обновляем humanitec-ingress
${SSH} "microk8s kubectl patch ingress humanitec-ingress -n default --type='json' -p='[
  {\"op\": \"replace\", \"path\": \"/spec/tls/0/secretName\", \"value\": \"${WILDCARD_SECRET}\"},
  {\"op\": \"replace\", \"path\": \"/spec/tls/0/hosts/0\", \"value\": \"${DOMAIN}\"}
]' 2>/dev/null || true"

# Обновляем livekit-ingress если существует
${SSH} "
  if microk8s kubectl get ingress livekit-ingress -n default >/dev/null 2>&1; then
    microk8s kubectl patch ingress livekit-ingress -n default --type='json' -p='[
      {\"op\": \"replace\", \"path\": \"/spec/tls/0/secretName\", \"value\": \"${WILDCARD_SECRET}\"}
    ]' && echo 'livekit-ingress обновлён'
  fi
"

echo
echo "======================================"
echo " Wildcard TLS настроен"
echo "======================================"
echo " Secret: ${WILDCARD_SECRET}"
echo " Покрывает: *.${DOMAIN} и ${DOMAIN}"
echo " Автопродление: cron 03:30 каждый день"
echo "======================================"
${SSH} "microk8s kubectl get secret ${WILDCARD_SECRET} -n default"
echo
echo "Следующий шаг: добавьте в conf.local.json:"
echo "  \"ingress\": { ..., \"livekit_tls_secret\": \"${WILDCARD_SECRET}\" }"
echo "И добавьте в GitHub Secrets:"
echo "  LIVEKIT_PUBLIC_URL = wss://livekit.${DOMAIN}"
