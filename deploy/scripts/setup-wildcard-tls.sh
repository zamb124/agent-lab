#!/usr/bin/env bash
# Идемпотентная настройка wildcard TLS для *.humanitec.ru через flant/cert-manager-webhook-regru (DNS-01).
# Запускать локально или с master ноды (требуется kubectl с настроенным kubeconfig + helm).
#
# ВАЖНО: REG.RU API требует whitelist IP. Перед первым запуском в личном кабинете reg.ru
# (Настройки → API) добавьте IP master-ноды в белый список — иначе webhook получит
# ACCESS_DENIED_FROM_IP и Certificate не выпустится.
#
# ENV:
#   REGRU_USERNAME      — логин reg.ru (email из личного кабинета, обязательно)
#   REGRU_PASSWORD      — alt-пароль для API из личного кабинета reg.ru (обязательно)
#   LE_EMAIL            — контакт для Let's Encrypt (по умолчанию ops@humanitec.ru)
#   APEX_HOST           — humanitec.ru
#   WILDCARD_HOST       — *.humanitec.ru
#   PLATFORM_TLS_SECRET — platform-tls (имя Secret для wildcard-сертификата)
#   PLATFORM_NS         — platform
#   WEBHOOK_REPO_URL    — git URL flant/cert-manager-webhook-regru (для git clone)
#   WEBHOOK_CHART_DIR   — рабочий каталог для git clone (по умолчанию /var/lib/cert-manager-webhook-regru)
#
# Что делает (всё идемпотентно):
#   1. Проверяет наличие cert-manager в кластере.
#   2. git clone/pull flant/cert-manager-webhook-regru в WEBHOOK_CHART_DIR.
#   3. helm upgrade --install regru-webhook ./helm с set'ами issuer.user/password.
#   4. Применяет ClusterIssuer letsencrypt-prod-dns01 (solver dns01.webhook → groupName: acme.regru.ru).
#   5. Применяет Certificate platform-tls в namespace platform → выдаст Secret platform-tls (humanitec.ru + *.humanitec.ru).
#   6. Ждёт Ready=True (до 10 мин).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl 2>/dev/null || require_command microk8s || exit 1
if [ -z "${HELM:-}" ]; then
  log_error "Не найден helm (или microk8s). Установите: https://helm.sh/docs/intro/install/"
  exit 1
fi

if [ -z "${REGRU_USERNAME:-}" ] || [ -z "${REGRU_PASSWORD:-}" ]; then
  log_error "Нужны переменные REGRU_USERNAME и REGRU_PASSWORD"
  exit 1
fi

LE_EMAIL="${LE_EMAIL:-ops@humanitec.ru}"
APEX_HOST="${APEX_HOST:-humanitec.ru}"
WILDCARD_HOST="${WILDCARD_HOST:-*.humanitec.ru}"
PLATFORM_TLS_SECRET="${PLATFORM_TLS_SECRET:-platform-tls}"
WEBHOOK_REPO_URL="${WEBHOOK_REPO_URL:-https://github.com/flant/cert-manager-webhook-regru.git}"
# Дефолт под пользователей без root-доступа (CI runner). Хост может переопределить через ENV.
WEBHOOK_CHART_DIR="${WEBHOOK_CHART_DIR:-${TMPDIR:-/tmp}/cert-manager-webhook-regru}"
WEBHOOK_RELEASE="${WEBHOOK_RELEASE:-regru-webhook}"
WEBHOOK_GROUP_NAME="${WEBHOOK_GROUP_NAME:-acme.regru.ru}"
WEBHOOK_SOLVER_NAME="${WEBHOOK_SOLVER_NAME:-regru-dns}"
# Image flant/cluster-issuer-regru: latest tagged published is 1.2.0 (ghcr.io/flant).
# values.yaml chart'а не имеет дефолта (issuer.image=changeme) — задаём явно.
WEBHOOK_IMAGE="${WEBHOOK_IMAGE:-ghcr.io/flant/cluster-issuer-regru:1.2.0}"
CERT_MANAGER_NS="${CERT_MANAGER_NS:-cert-manager}"

# Использовать $KUBECTL и $HELM из _common.sh (auto-detect kubectl/microk8s, helm/microk8s helm3).
K="$KUBECTL"
H="$HELM"

log_section "Wildcard TLS для $APEX_HOST + $WILDCARD_HOST"

# 1. Проверка cert-manager
if ! $K get namespace cert-manager >/dev/null 2>&1; then
  log_error "namespace cert-manager отсутствует. Запустите 'microk8s enable cert-manager' на master."
  exit 1
fi
log_ok "cert-manager установлен"

# 1b. Fast-path: если Certificate уже Ready и ClusterIssuer Ready — выходим без действий.
# При плановом продлении (~30 дней до expire) cert-manager сам инициирует новый Order через
# существующий webhook+ClusterIssuer — этот скрипт здесь не участвует. Долгое (5-15 мин)
# ожидание DNS-01 challenge происходит ровно один раз — при первом выпуске.
if $K get certificate "$PLATFORM_TLS_SECRET" -n "$PLATFORM_NS" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null \
    | grep -q '^True$' \
   && $K get clusterissuer letsencrypt-prod-dns01 \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null \
    | grep -q '^True$'; then
  EXPIRES=$($K get certificate "$PLATFORM_TLS_SECRET" -n "$PLATFORM_NS" \
    -o jsonpath='{.status.notAfter}' 2>/dev/null)
  log_skip "Certificate $PLATFORM_TLS_SECRET уже Ready (notAfter=$EXPIRES) — все шаги пропущены"
  print_summary
  exit 0
fi

# 2. Клонируем/обновляем chart flant/cert-manager-webhook-regru.
# Канал публикации flant — git+helm (нет GitHub Pages). Идемпотентно: clone если нет, иначе fetch+reset.
require_command git || { log_error "git не установлен"; exit 1; }
if [ -d "$WEBHOOK_CHART_DIR/.git" ]; then
  log_skip "git clone $WEBHOOK_REPO_URL → $WEBHOOK_CHART_DIR"
  log_do "git fetch + reset --hard origin/master"
  git -C "$WEBHOOK_CHART_DIR" fetch --depth=1 origin master >/dev/null
  git -C "$WEBHOOK_CHART_DIR" reset --hard origin/master >/dev/null
else
  log_do "git clone $WEBHOOK_REPO_URL → $WEBHOOK_CHART_DIR"
  rm -rf "$WEBHOOK_CHART_DIR"
  git clone --depth=1 "$WEBHOOK_REPO_URL" "$WEBHOOK_CHART_DIR" >/dev/null
fi

# 3. Helm install/upgrade webhook (chart лежит в подкаталоге ./helm).
log_do "helm upgrade --install $WEBHOOK_RELEASE (chart $WEBHOOK_CHART_DIR/helm)"
$H upgrade --install "$WEBHOOK_RELEASE" "$WEBHOOK_CHART_DIR/helm" \
  --namespace "$CERT_MANAGER_NS" \
  --set "issuer.image=$WEBHOOK_IMAGE" \
  --set "issuer.user=$REGRU_USERNAME" \
  --set "issuer.password=$REGRU_PASSWORD" \
  --set "groupName.name=$WEBHOOK_GROUP_NAME" \
  --set "certManager.namespace=$CERT_MANAGER_NS" \
  --set "certManager.serviceAccountName=cert-manager" \
  --wait --timeout 5m

# 4. ClusterIssuer (DNS-01 через webhook). Secret regru-password создаётся helm chart'ом автоматически.
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
            groupName: ${WEBHOOK_GROUP_NAME}
            solverName: ${WEBHOOK_SOLVER_NAME}
            config:
              regruPasswordSecretRef:
                name: regru-password
                key: REGRU_PASSWORD
EOF

# 5. Namespace platform — создаём, если нет (скрипт идёт перед helm install в CI).
if $K get namespace "$PLATFORM_NS" >/dev/null 2>&1; then
  log_skip "namespace $PLATFORM_NS"
else
  log_do "kubectl create namespace $PLATFORM_NS"
  $K create namespace "$PLATFORM_NS"
fi

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
