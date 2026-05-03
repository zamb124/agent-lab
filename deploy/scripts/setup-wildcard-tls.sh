#!/usr/bin/env bash
# Идемпотентная настройка wildcard TLS для humanitec.ru + *.humanitec.ru через
# flant/cert-manager-webhook-regru (DNS-01) и Let's Encrypt.
# Шаги: git clone webhook-чарта, helm upgrade --install regru-webhook, ClusterIssuer
# letsencrypt-prod-dns01, Certificate platform-tls в namespace platform, wait Ready.
# Fast-path: если Certificate и ClusterIssuer уже Ready — выходит без действий.
#
# REG.RU API требует whitelist IP master-ноды (Настройки → API в личном кабинете).
#
# ENV: REGRU_USERNAME / REGRU_PASSWORD (обязательны), LE_EMAIL, APEX_HOST,
#      WILDCARD_HOST, PLATFORM_TLS_SECRET, PLATFORM_NS, WEBHOOK_REPO_URL, WEBHOOK_CHART_DIR.

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
WEBHOOK_CHART_DIR="${WEBHOOK_CHART_DIR:-${TMPDIR:-/tmp}/cert-manager-webhook-regru}"
WEBHOOK_RELEASE="${WEBHOOK_RELEASE:-regru-webhook}"
WEBHOOK_GROUP_NAME="${WEBHOOK_GROUP_NAME:-acme.regru.ru}"
WEBHOOK_SOLVER_NAME="${WEBHOOK_SOLVER_NAME:-regru-dns}"
# values.yaml chart'а не имеет дефолта для issuer.image — задаём явно.
WEBHOOK_IMAGE="${WEBHOOK_IMAGE:-ghcr.io/flant/cluster-issuer-regru:1.2.0}"
CERT_MANAGER_NS="${CERT_MANAGER_NS:-cert-manager}"

K="$KUBECTL"
H="$HELM"

log_section "Wildcard TLS для $APEX_HOST + $WILDCARD_HOST"

# 1. Проверка cert-manager
if ! $K get namespace cert-manager >/dev/null 2>&1; then
  log_error "namespace cert-manager отсутствует. Запустите 'microk8s enable cert-manager' на master."
  exit 1
fi
log_ok "cert-manager установлен"

# 1b. Fast-path: Certificate + ClusterIssuer Ready → выходим. Renewal cert-manager делает сам.
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

# 2. Клонируем/обновляем chart flant/cert-manager-webhook-regru (без Helm-репозитория, только git).
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

# 3. Helm install/upgrade webhook (chart в подкаталоге ./helm).
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

# 4. ClusterIssuer (DNS-01 через webhook). Secret regru-password создаётся helm chart'ом.
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

# 5. Namespace platform — создаём, если нет (скрипт идёт перед helm install).
if $K get namespace "$PLATFORM_NS" >/dev/null 2>&1; then
  log_skip "namespace $PLATFORM_NS"
else
  log_do "kubectl create namespace $PLATFORM_NS"
  $K create namespace "$PLATFORM_NS"
fi

# 5b. Канонизация: на кластере мог остаться предыдущий релиз чарта с аннотациями
# `cert-manager.io/cluster-issuer: letsencrypt-prod` на Ingress-объектах. cert-manager
# Ingress-shim создаёт по такой аннотации Certificate с `ownerRef = Ingress` и
# issuerRef из аннотации. После этого `kubectl apply` НЕ может переопределить
# ownerReferences и issuerRef → наш Certificate бесконечно болтается в Issuing.
# Чистим: убираем аннотацию `cert-manager.io/cluster-issuer` на ингрессах в
# namespace, удаляем orphan-Certificates (issuerRef != letsencrypt-prod-dns01
# ИЛИ ownerRef.kind=Ingress) вместе с их CertificateRequests/Orders.
ANNOT_KEY="cert-manager.io/cluster-issuer"
for ing in $($K get ingress -n "$PLATFORM_NS" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null); do
  if $K get ingress "$ing" -n "$PLATFORM_NS" -o jsonpath="{.metadata.annotations.${ANNOT_KEY//./\\.}}" 2>/dev/null | grep -q .; then
    log_do "kubectl annotate ingress $ing ${ANNOT_KEY}-"
    $K annotate ingress "$ing" -n "$PLATFORM_NS" "${ANNOT_KEY}-" >/dev/null
  fi
done

for cert in $($K get certificate -n "$PLATFORM_NS" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null); do
  ISSUER=$($K get certificate "$cert" -n "$PLATFORM_NS" -o jsonpath='{.spec.issuerRef.name}' 2>/dev/null)
  OWNER_KIND=$($K get certificate "$cert" -n "$PLATFORM_NS" -o jsonpath='{.metadata.ownerReferences[0].kind}' 2>/dev/null)
  if [ "$ISSUER" != "letsencrypt-prod-dns01" ] || [ "$OWNER_KIND" = "Ingress" ]; then
    log_do "delete orphan Certificate $cert (issuer=$ISSUER, owner=$OWNER_KIND)"
    $K delete certificate "$cert" -n "$PLATFORM_NS" --wait=false >/dev/null 2>&1 || true
  fi
done
$K delete certificaterequest -n "$PLATFORM_NS" --all --wait=false >/dev/null 2>&1 || true
$K delete order -n "$PLATFORM_NS" --all --wait=false >/dev/null 2>&1 || true

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
