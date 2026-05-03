#!/usr/bin/env bash
# Идемпотентная настройка wildcard TLS для *.humanitec.ru через cert-manager-webhook-regru (DNS-01).
# Запускать локально или с master ноды (требуется kubectl с настроенным kubeconfig + helm).
#
# ENV:
#   REGRU_USERNAME      — логин reg.ru (обязательно)
#   REGRU_PASSWORD      — пароль reg.ru (обязательно)
#   LE_EMAIL            — контакт для Let's Encrypt (по умолчанию ops@humanitec.ru)
#   APEX_HOST           — humanitec.ru
#   WILDCARD_HOST       — *.humanitec.ru
#   PLATFORM_TLS_SECRET — platform-tls (имя Secret для wildcard-сертификата)
#   PLATFORM_NS         — platform
#
# Что делает (всё идемпотентно):
#   1. Проверяет наличие cert-manager в кластере.
#   2. helm install cert-manager-webhook-regru в namespace cert-manager (если нет).
#   3. Применяет Secret regru-credentials.
#   4. Применяет ClusterIssuer letsencrypt-prod-dns01.
#   5. Применяет Certificate platform-tls в namespace platform → выдаст Secret platform-tls.
#   6. Ждёт Ready=True (до 5 мин).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl || { require_command microk8s || exit 1; }
require_command helm || { log_error "Установите helm: https://helm.sh/docs/intro/install/"; exit 1; }

if [ -z "${REGRU_USERNAME:-}" ] || [ -z "${REGRU_PASSWORD:-}" ]; then
  log_error "Нужны переменные REGRU_USERNAME и REGRU_PASSWORD"
  exit 1
fi

LE_EMAIL="${LE_EMAIL:-ops@humanitec.ru}"
APEX_HOST="${APEX_HOST:-humanitec.ru}"
WILDCARD_HOST="${WILDCARD_HOST:-*.humanitec.ru}"
PLATFORM_TLS_SECRET="${PLATFORM_TLS_SECRET:-platform-tls}"
WEBHOOK_REPO="${WEBHOOK_REPO:-https://regru.github.io/cert-manager-webhook-regru}"

# Использовать $KUBECTL из _common.sh (kubectl или 'microk8s kubectl')
K="$KUBECTL"
H="${HELM:-helm}"

log_section "Wildcard TLS для $APEX_HOST + $WILDCARD_HOST"

# 1. Проверка cert-manager
if ! $K get namespace cert-manager >/dev/null 2>&1; then
  log_error "namespace cert-manager отсутствует. Запустите 'microk8s enable cert-manager' на master."
  exit 1
fi
log_ok "cert-manager установлен"

# 2. Helm webhook regru
if $H list -n cert-manager 2>/dev/null | grep -q '^cert-manager-webhook-regru'; then
  log_skip "helm release cert-manager-webhook-regru уже установлен"
else
  log_do "helm install cert-manager-webhook-regru"
  $H repo add regru "$WEBHOOK_REPO" 2>/dev/null || true
  $H repo update regru || true
  $H install cert-manager-webhook-regru regru/cert-manager-webhook-regru \
    --namespace cert-manager \
    --wait --timeout 5m
fi

# 3. Secret с креденшалами reg.ru
log_do "Secret regru-credentials в cert-manager"
$K create secret generic regru-credentials \
  --namespace cert-manager \
  --from-literal=username="$REGRU_USERNAME" \
  --from-literal=password="$REGRU_PASSWORD" \
  --dry-run=client -o yaml | $K apply -f -

# 4. ClusterIssuer
log_do "ClusterIssuer letsencrypt-prod-dns01"
cat <<EOF | $K apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod-dns01
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${LE_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-prod-dns01-account-key
    solvers:
      - dns01:
          webhook:
            groupName: acme.regru.ru
            solverName: regru
            config:
              usernameSecretRef:
                name: regru-credentials
                key: username
              passwordSecretRef:
                name: regru-credentials
                key: password
EOF

# 5. Namespace platform (если нет)
$K create namespace "$PLATFORM_NS" --dry-run=client -o yaml | $K apply -f -

# 6. Certificate
log_do "Certificate $PLATFORM_TLS_SECRET в $PLATFORM_NS"
cat <<EOF | $K apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${PLATFORM_TLS_SECRET}
  namespace: ${PLATFORM_NS}
spec:
  secretName: ${PLATFORM_TLS_SECRET}
  issuerRef:
    name: letsencrypt-prod-dns01
    kind: ClusterIssuer
  dnsNames:
    - ${APEX_HOST}
    - "${WILDCARD_HOST}"
EOF

# 7. Ждём Ready
wait_for \
  "Certificate $PLATFORM_TLS_SECRET Ready" \
  "[ \"\$($K get certificate $PLATFORM_TLS_SECRET -n $PLATFORM_NS -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}' 2>/dev/null)\" = 'True' ]" \
  600 15 \
  || {
    log_warn "Сертификат ещё не Ready. Проверьте:"
    log_warn "  $K describe certificate $PLATFORM_TLS_SECRET -n $PLATFORM_NS"
    log_warn "  $K get challenges -A"
    log_warn "  $K logs -n cert-manager deployment/cert-manager-webhook-regru"
    exit 1
  }

log_ok "Wildcard TLS готов: Secret $PLATFORM_TLS_SECRET в $PLATFORM_NS"
print_summary
