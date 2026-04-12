#!/usr/bin/env bash
# Настройка MicroK8s Ingress + cert-manager (Let's Encrypt) на сервере.
#
# Архитектура:
#   domain.com/            → frontend  (8002)
#   domain.com/documentation → тот же frontend (8002), статика Fumadocs; отдельный path в ingress не нужен
#   domain.com/agents      → agents    (8001)
#   domain.com/crm         → crm       (8003)
#   domain.com/rag         → rag       (8004)
#   domain.com/sync        → sync      (8005, websocket)
#   domain.com/provider-litserve → provider_litserve (8014)
#   domain.com/documents   → office    (8008, BFF «Документы» + OnlyOffice BFF)
#   onlyoffice.domain.com  → onlyoffice (порт публикации DS на хосте, обычно 8088)
#   Весь трафик DS идёт на субдомен — нет проблем с /{semver}-{hex}/... путями,
#   не нужны отдельные Prefix /web-apps, /cache, /fonts, /sdkjs на основном домене.
#   OFFICE__DOCUMENT_SERVER_PUBLIC_URL = https://onlyoffice.domain.com
#   Локально (без ingress): DevInterServiceProxy прокси на document_server_dev_upstream_url.
#   *.domain.com/*         → те же правила (поддомены компаний)
#
# OnlyOffice: браузер грузит api.js и всю статику/co-editing с субдомена onlyoffice.{domain}.
# Iframe редактора указывает на onlyoffice.{domain} — все пути DS одним ingress-правилом.
#
# Конфиг в conf.local.json:
#   "selectel": { "ip": "...", "login": "...", "ssh_port": "22" }
#   "ingress": {
#     "domain": "humanitec.ru",
#     "email": "admin@humanitec.ru",
#     "services": [
#       {"name": "frontend", "port": 8002, "path": "/",         "websocket": false},
#       {"name": "agents",   "port": 8001, "path": "/flows",   "websocket": false},
#       {"name": "crm",      "port": 8003, "path": "/crm",     "websocket": false},
#       {"name": "rag",      "port": 8004, "path": "/rag",     "websocket": false},
#       {"name": "sync",     "port": 8005, "path": "/sync",    "websocket": true},
#       {"name": "provider_litserve", "port": 8014, "path": "/provider-litserve", "websocket": false},
#       {"name": "office",   "port": 8008, "path": "/documents","websocket": false}
#     ],
#     "onlyoffice_port": 8088,
#     "wildcard_tls_secret": "humanitec-ru-wildcard-tls"
#   }
#   wildcard_tls_secret — опционально; иначе ищется секрет *-wildcard-tls в namespace default.
#
# Запуск: bash deploy/ingress.sh

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
require_cmd scp

[[ -f "${CONF_LOCAL_JSON}" ]] || { echo "Не найден: ${CONF_LOCAL_JSON}" >&2; exit 1; }

IP="$(jq -er '.selectel.ip' "${CONF_LOCAL_JSON}")"
LOGIN="$(jq -er '.selectel.login' "${CONF_LOCAL_JSON}")"
SSH_PORT="$(jq -r '.selectel.ssh_port // "22"' "${CONF_LOCAL_JSON}")"
DOMAIN="$(jq -er '.ingress.domain' "${CONF_LOCAL_JSON}")"
EMAIL="$(jq -er '.ingress.email' "${CONF_LOCAL_JSON}")"

log "Домен: ${DOMAIN}"
log "Сервер: ${LOGIN}@${IP}:${SSH_PORT}"

if ! jq -e '.ingress.services | map(.path) | index("/documents") != null' "${CONF_LOCAL_JSON}" >/dev/null 2>&1; then
  echo "ПРЕДУПРЕЖДЕНИЕ: в ingress.services нет office с path /documents — https://${DOMAIN}/documents уйдёт во frontend (404)." >&2
  echo "Добавьте: {\"name\":\"office\",\"port\":8008,\"path\":\"/documents\",\"websocket\":false}" >&2
fi

ONLYOFFICE_PORT="$(jq -r '.ingress.onlyoffice_port // "8088"' "${CONF_LOCAL_JSON}")"
if jq -e '.ingress.services | map(.path) | index("/documents") != null' "${CONF_LOCAL_JSON}" >/dev/null 2>&1; then
  if [[ "${ONLYOFFICE_PORT}" == "null" ]] || [[ -z "${ONLYOFFICE_PORT}" ]]; then
    echo "ПРЕДУПРЕЖДЕНИЕ: есть /documents (office), но ingress.onlyoffice_port не задан — субдомен onlyoffice.${DOMAIN} не будет создан." >&2
  fi
fi

REMOTE_DIR="$(jq -r '.selectel.remote_dir // "/opt/agent-lab"' "${CONF_LOCAL_JSON}")"
SSH="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10 -p ${SSH_PORT} ${LOGIN}@${IP}"

# Получаем IP хоста на сервере
HOST_IP="$(${SSH} "ip -4 addr show scope global | awk '/inet / {print \$2}' | awk -F/ '{print \$1}' | head -1")"
log "IP хоста: ${HOST_IP}"

# ─── Подготовка статики ──────────────────────────────────────────────────────
# Копируем UI файлы из apps/*/ui/ в единую структуру static/ для nginx ingress
log "Подготовка статики для ingress"

# Передаём REMOTE_DIR и CONF_LOCAL_JSON в скрипт
export REMOTE_DIR
export CONF_LOCAL_JSON="${CONF_LOCAL_JSON}"
${SSH} "REMOTE_DIR=${REMOTE_DIR} && cd \${REMOTE_DIR} && bash -s" < "${SCRIPT_DIR}/prepare-static.sh"

# i18n генерация встроена внутрь prepare-static.sh выше

# ─── Включаем snippet annotations в ingress controller ──────────────────────
# С nginx ingress controller v1.9+ server-snippet и configuration-snippet
# отключены по умолчанию из соображений безопасности.
# Без этого все location blocks в server-snippet тихо игнорируются.
log "Включаем snippet annotations в ingress controller"

# Определяем имя ConfigMap (в MicroK8s может быть разным)
_CM_NAME=""
for _candidate in "nginx-load-balancer-microk8s-conf" "nginx-ingress-microk8s-controller"; do
  if ${SSH} "microk8s kubectl -n ingress get configmap ${_candidate} >/dev/null 2>&1"; then
    _CM_NAME="${_candidate}"
    break
  fi
done

if [[ -z "${_CM_NAME}" ]]; then
  log "WARNING: ConfigMap ingress controller не найден — snippet annotations не включены"
else
  log "ConfigMap: ${_CM_NAME}"
  _SNIPPETS_ENABLED="$(${SSH} "microk8s kubectl -n ingress get configmap ${_CM_NAME} -o yaml | grep -c 'allow-snippet-annotations' || true")"
  if [[ "${_SNIPPETS_ENABLED}" -gt 0 ]]; then
    log "snippet annotations уже включены"
  else
    log "Включаем allow-snippet-annotations и annotations-risk-level=Critical"
    ${SSH} "microk8s kubectl -n ingress patch configmap ${_CM_NAME} --type=merge -p '{\"data\":{\"allow-snippet-annotations\":\"true\",\"annotations-risk-level\":\"Critical\"}}'"
    log "Перезапускаем ingress controller для применения ConfigMap"
    ${SSH} "microk8s kubectl -n ingress rollout restart daemonset nginx-ingress-microk8s-controller"
    ${SSH} "microk8s kubectl -n ingress rollout status daemonset nginx-ingress-microk8s-controller --timeout=120s"
  fi
fi

# cert-manager
log "Проверяем cert-manager"
${SSH} "microk8s kubectl get namespace cert-manager >/dev/null 2>&1 || (microk8s enable cert-manager && microk8s kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=120s)"

# ClusterIssuer: не перезаписываем существующий — иначе сбрасываются DNS-01 / доп. solvers для wildcard.
if ${SSH} "microk8s kubectl get clusterissuer letsencrypt >/dev/null 2>&1"; then
  log "ClusterIssuer letsencrypt уже есть — не трогаем (wildcard/DNS-01 сохраняются)"
else
  log "ClusterIssuer (Let's Encrypt, только HTTP-01 — для apex)"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    email: ${EMAIL}
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: letsencrypt-account-key
    solvers:
    - http01:
        ingress:
          class: public
EOF
fi

# Services + Endpoints для каждого сервиса
log "Создаём Services и Endpoints"
while IFS= read -r entry; do
  name="$(echo "${entry}" | jq -r '.name')"
  port="$(echo "${entry}" | jq -r '.port')"
  svc="${name}-svc"

  log "  ${svc} -> ${HOST_IP}:${port}"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${svc}
  namespace: default
spec:
  ports:
  - port: ${port}
    targetPort: ${port}
    protocol: TCP
---
apiVersion: v1
kind: Endpoints
metadata:
  name: ${svc}
  namespace: default
subsets:
- addresses:
  - ip: ${HOST_IP}
  ports:
  - port: ${port}
EOF
done < <(jq -c '.ingress.services[]' "${CONF_LOCAL_JSON}")

# ─── Статический nginx сервер ────────────────────────────────────────────────
# root/alias запрещены в nginx ingress snippets (PR #8624 kubernetes/ingress-nginx).
# Правильное решение: отдельный nginx pod с hostPath монтирующий /opt/agent-lab/static.
# Ingress направляет /static/*, /crm/ui/static/ и т.д. на этот pod.

log "Создаём static-server (nginx pod для раздачи статики)"
${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: static-server-conf
  namespace: default
data:
  default.conf: |
    server {
        listen 80;
        # MIME типы для JS модулей — браузер отказывается исполнять .mjs с application/octet-stream
        types {
            text/html                             html htm shtml;
            text/css                              css;
            application/javascript                js mjs;
            application/json                      json;
            application/wasm                      wasm;
            image/svg+xml                         svg svgz;
            image/png                             png;
            image/jpeg                            jpg jpeg;
            image/gif                             gif;
            image/webp                            webp;
            image/x-icon                          ico;
            font/woff                             woff;
            font/woff2                            woff2;
            font/ttf                              ttf;
            font/otf                              otf;
            application/octet-stream              bin exe;
        }
        location = /api/i18n/ru {
            alias /srv/static/i18n/ru.json;
            default_type application/json;
            add_header Cache-Control "public, max-age=3600" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location = /api/i18n/en {
            alias /srv/static/i18n/en.json;
            default_type application/json;
            add_header Cache-Control "public, max-age=3600" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /static/core/ {
            alias /srv/static/core/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /static/frontend/ {
            alias /srv/static/frontend/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /crm/ui/static/ {
            alias /srv/static/crm/ui/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /crm/ui/vendor/ {
            alias /srv/static/crm/ui/vendor/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /sync/ui/static/ {
            alias /srv/static/sync/ui/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /rag/ui/static/ {
            alias /srv/static/rag/ui/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /documents/ui/static/ {
            alias /srv/static/documents/ui/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
        location /flows/static/ {
            alias /srv/static/flows/ui/;
            add_header Cache-Control "public, max-age=31536000, immutable" always;
            add_header Access-Control-Allow-Origin "*" always;
        }
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: static-server
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: static-server
  template:
    metadata:
      labels:
        app: static-server
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        volumeMounts:
        - name: nginx-conf
          mountPath: /etc/nginx/conf.d
        - name: static-files
          mountPath: /srv/static
          readOnly: true
      volumes:
      - name: nginx-conf
        configMap:
          name: static-server-conf
      - name: static-files
        hostPath:
          path: ${REMOTE_DIR}/static
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: static-server-svc
  namespace: default
spec:
  selector:
    app: static-server
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
EOF

log "Перезапускаем static-server (подхватывает новый ConfigMap с MIME типами)"
${SSH} "microk8s kubectl rollout restart deployment/static-server -n default"
${SSH} "microk8s kubectl rollout status deployment/static-server -n default --timeout=60s"

# Генерируем paths для ingress — статика идёт на static-server-svc, остальное на сервисы
build_paths() {
  # Сначала пути к статике (более специфичные → матчатся раньше)
  # /api/i18n/ обрабатывается внутри static-server через exact location match
  cat <<STATICPATHS
      - path: /api/i18n
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /static/core/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /static/frontend/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /crm/ui/static/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /crm/ui/vendor/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /sync/ui/static/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /rag/ui/static/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /documents/ui/static/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
      - path: /flows/static/
        pathType: Prefix
        backend:
          service:
            name: static-server-svc
            port:
              number: 80
STATICPATHS

  # Динамические сервисы (из conf.local.json)
  jq -r '
    .ingress.services
    | sort_by(.path | length)
    | reverse
    | .[]
    | "      - path: \(.path)\n        pathType: Prefix\n        backend:\n          service:\n            name: \(.name)-svc\n            port:\n              number: \(.port)"
  ' "${CONF_LOCAL_JSON}"
}

PATHS="$(build_paths)"

# Ingress TLS: apex + опционально wildcard для *.domain (тот же секрет, что вручную или DNS-01).
# Раньше в манифесте был только apex — kubectl apply затирал второй tls-блок и ломал поддомены.
# Wildcard: см. deploy/wildcard-tls.sh / DNS-01; имя секрета — ingress.wildcard_tls_secret или авто-поиск.
TLS_SECRET="$(echo "${DOMAIN}" | tr '.' '-')-tls"
WILDCARD_TLS_SECRET="$(jq -r '.ingress.wildcard_tls_secret // empty' "${CONF_LOCAL_JSON}" 2>/dev/null || true)"
if [[ -z "${WILDCARD_TLS_SECRET}" ]]; then
  _DOMAIN_DASH_TLS="$(echo "${DOMAIN}" | tr '.' '-')"
  for _cand in "${_DOMAIN_DASH_TLS}-wildcard-tls" "wildcard-${_DOMAIN_DASH_TLS}-tls" "${_DOMAIN_DASH_TLS}-star-tls"; do
    if ${SSH} "microk8s kubectl get secret ${_cand} -n default >/dev/null 2>&1"; then
      WILDCARD_TLS_SECRET="${_cand}"
      break
    fi
  done
fi

if [[ -n "${WILDCARD_TLS_SECRET}" ]]; then
  log "Ingress TLS: apex ${TLS_SECRET} + wildcard *.${DOMAIN} → ${WILDCARD_TLS_SECRET}"
  TLS_SPEC=$(cat <<EOFTLS
  tls:
  - hosts:
    - ${DOMAIN}
    secretName: ${TLS_SECRET}
  - hosts:
    - "*.${DOMAIN}"
    secretName: ${WILDCARD_TLS_SECRET}
EOFTLS
)
else
  log "Ingress TLS: только apex ${TLS_SECRET} (wildcard-секрет в default не найден — поддомены без отдельного TLS)"
  TLS_SPEC=$(cat <<EOFTLS
  tls:
  - hosts:
    - ${DOMAIN}
    secretName: ${TLS_SECRET}
EOFTLS
)
fi

log "Создаём Ingress для ${DOMAIN} и *.${DOMAIN}"
log "Kubectl apply Ingress..."
${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: humanitec-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
spec:
  ingressClassName: public
${TLS_SPEC}
  rules:
  - host: ${DOMAIN}
    http:
      paths:
${PATHS}
  - host: "*.${DOMAIN}"
    http:
      paths:
${PATHS}
EOF

log "✅ Ingress создан"

if ${SSH} "microk8s kubectl get secret ${TLS_SECRET} -n default >/dev/null 2>&1"; then
  log "Certificate ${TLS_SECRET} уже существует — пропускаем"
else
  log "Certificate (Let's Encrypt HTTP-01, только apex ${DOMAIN})"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${TLS_SECRET}
  namespace: default
spec:
  secretName: ${TLS_SECRET}
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer
  dnsNames:
  - ${DOMAIN}
EOF
  log "Ожидаем сертификат (~60 сек)"
  sleep 60
fi

# ─── LiveKit: отдельный Ingress на поддомене livekit.{domain} ──────────────────
# Браузеры требуют WSS — LiveKit должен быть доступен через HTTPS/WSS.
#
# TLS-секрет для LiveKit определяется так (приоритет):
#   1. ingress.livekit_tls_secret в conf.local.json — задай имя wildcard-секрета явно
#   2. Если в кластере найден любой секрет с wildcard-именем — используем его
#   3. Иначе создаём новый HTTP-01 сертификат для livekit.{domain}
#
# Пример conf.local.json для wildcard:
#   "ingress": { ..., "livekit_tls_secret": "humanitec-ru-wildcard-tls" }
LIVEKIT_SUBDOMAIN="livekit.${DOMAIN}"
LIVEKIT_PORT=7880
LIVEKIT_SPECIFIC_SECRET="$(echo "${LIVEKIT_SUBDOMAIN}" | tr '.' '-')-tls"

# Приоритет 1: явная настройка в conf.local.json
_CONFIGURED_SECRET="$(jq -r '.ingress.livekit_tls_secret // empty' "${CONF_LOCAL_JSON}" 2>/dev/null || true)"
if [[ -n "${_CONFIGURED_SECRET}" ]]; then
  LIVEKIT_TLS_SECRET="${_CONFIGURED_SECRET}"
  log "LiveKit TLS: использует настроенный секрет ${LIVEKIT_TLS_SECRET} (wildcard)"
else
  # Приоритет 2: найти wildcard-секрет на кластере (имена по распространённым паттернам)
  _DOMAIN_DASH="$(echo "${DOMAIN}" | tr '.' '-')"
  _FOUND_WILDCARD=""
  for _candidate in "${_DOMAIN_DASH}-wildcard-tls" "wildcard-${_DOMAIN_DASH}-tls" "${_DOMAIN_DASH}-star-tls"; do
    if ${SSH} "microk8s kubectl get secret ${_candidate} -n default >/dev/null 2>&1"; then
      _FOUND_WILDCARD="${_candidate}"
      break
    fi
  done

  if [[ -n "${_FOUND_WILDCARD}" ]]; then
    LIVEKIT_TLS_SECRET="${_FOUND_WILDCARD}"
    log "LiveKit TLS: найден wildcard-сертификат ${LIVEKIT_TLS_SECRET} — используем его, новый не создаём"
  else
    LIVEKIT_TLS_SECRET="${LIVEKIT_SPECIFIC_SECRET}"
    log "LiveKit TLS: wildcard не найден, будет использован ${LIVEKIT_TLS_SECRET}"
  fi
fi

log "Создаём Service и Endpoints для LiveKit (${LIVEKIT_SUBDOMAIN}:${LIVEKIT_PORT})"
${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: livekit-svc
  namespace: default
spec:
  ports:
  - port: ${LIVEKIT_PORT}
    targetPort: ${LIVEKIT_PORT}
    protocol: TCP
---
apiVersion: v1
kind: Endpoints
metadata:
  name: livekit-svc
  namespace: default
subsets:
- addresses:
  - ip: ${HOST_IP}
  ports:
  - port: ${LIVEKIT_PORT}
EOF

log "Создаём Ingress для ${LIVEKIT_SUBDOMAIN} (TLS: ${LIVEKIT_TLS_SECRET})"
${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: livekit-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
spec:
  ingressClassName: public
  tls:
  - hosts:
    - ${LIVEKIT_SUBDOMAIN}
    secretName: ${LIVEKIT_TLS_SECRET}
  rules:
  - host: ${LIVEKIT_SUBDOMAIN}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: livekit-svc
            port:
              number: ${LIVEKIT_PORT}
EOF

# Создаём новый сертификат только если секрет ещё не существует в кластере
if ${SSH} "microk8s kubectl get secret ${LIVEKIT_TLS_SECRET} -n default >/dev/null 2>&1"; then
  log "Секрет ${LIVEKIT_TLS_SECRET} уже есть в кластере — сертификат не создаём"
else
  log "Создаём Certificate (Let's Encrypt HTTP-01) для ${LIVEKIT_SUBDOMAIN}"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${LIVEKIT_TLS_SECRET}
  namespace: default
spec:
  secretName: ${LIVEKIT_TLS_SECRET}
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer
  dnsNames:
  - ${LIVEKIT_SUBDOMAIN}
EOF
  log "Ожидаем сертификат LiveKit (~60 сек)"
  sleep 60
fi

# ─── OnlyOffice Document Server: отдельный Ingress на поддомене onlyoffice.{domain} ────
# Весь трафик DS (web-apps, sdkjs, fonts, doc, cache, downloadfile и версионные пути)
# уходит на один хост — не нужны отдельные Prefix в основном ingress.
# OFFICE__DOCUMENT_SERVER_PUBLIC_URL = https://onlyoffice.{domain}
ONLYOFFICE_SUBDOMAIN="onlyoffice.${DOMAIN}"

if [[ -n "${ONLYOFFICE_PORT}" ]] && [[ "${ONLYOFFICE_PORT}" != "null" ]]; then
  log "Создаём Service и Endpoints для OnlyOffice DS (${ONLYOFFICE_SUBDOMAIN}:${ONLYOFFICE_PORT})"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: onlyoffice-svc
  namespace: default
spec:
  ports:
  - port: ${ONLYOFFICE_PORT}
    targetPort: ${ONLYOFFICE_PORT}
    protocol: TCP
---
apiVersion: v1
kind: Endpoints
metadata:
  name: onlyoffice-svc
  namespace: default
subsets:
- addresses:
  - ip: ${HOST_IP}
  ports:
  - port: ${ONLYOFFICE_PORT}
EOF

  ONLYOFFICE_SPECIFIC_SECRET="$(echo "${ONLYOFFICE_SUBDOMAIN}" | tr '.' '-')-tls"

  _OO_CONFIGURED_SECRET="$(jq -r '.ingress.onlyoffice_tls_secret // empty' "${CONF_LOCAL_JSON}" 2>/dev/null || true)"
  if [[ -n "${_OO_CONFIGURED_SECRET}" ]]; then
    ONLYOFFICE_TLS_SECRET="${_OO_CONFIGURED_SECRET}"
    log "OnlyOffice TLS: использует настроенный секрет ${ONLYOFFICE_TLS_SECRET}"
  elif [[ -n "${WILDCARD_TLS_SECRET}" ]]; then
    ONLYOFFICE_TLS_SECRET="${WILDCARD_TLS_SECRET}"
    log "OnlyOffice TLS: использует wildcard ${ONLYOFFICE_TLS_SECRET}"
  else
    ONLYOFFICE_TLS_SECRET="${ONLYOFFICE_SPECIFIC_SECRET}"
    log "OnlyOffice TLS: wildcard не найден, будет ${ONLYOFFICE_TLS_SECRET}"
  fi

  log "Создаём Ingress для ${ONLYOFFICE_SUBDOMAIN} (TLS: ${ONLYOFFICE_TLS_SECRET})"
  ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: onlyoffice-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
spec:
  ingressClassName: public
  tls:
  - hosts:
    - ${ONLYOFFICE_SUBDOMAIN}
    secretName: ${ONLYOFFICE_TLS_SECRET}
  rules:
  - host: ${ONLYOFFICE_SUBDOMAIN}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: onlyoffice-svc
            port:
              number: ${ONLYOFFICE_PORT}
EOF

  if ${SSH} "microk8s kubectl get secret ${ONLYOFFICE_TLS_SECRET} -n default >/dev/null 2>&1"; then
    log "Секрет ${ONLYOFFICE_TLS_SECRET} уже есть в кластере — сертификат не создаём"
  else
    log "Создаём Certificate (Let's Encrypt HTTP-01) для ${ONLYOFFICE_SUBDOMAIN}"
    ${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${ONLYOFFICE_TLS_SECRET}
  namespace: default
spec:
  secretName: ${ONLYOFFICE_TLS_SECRET}
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer
  dnsNames:
  - ${ONLYOFFICE_SUBDOMAIN}
EOF
    log "Ожидаем сертификат OnlyOffice (~60 сек)"
    sleep 60
  fi
else
  log "OnlyOffice DS: ingress.onlyoffice_port не задан — пропускаем субдомен ${ONLYOFFICE_SUBDOMAIN}"
fi

# ─── Монтируем статику в ingress-контроллер ──────────────────────────────────
# hostPath volume для /opt/agent-lab/static → /srv/static внутри pod
# i18n уже внутри static/i18n, отдельный volume для i18n не нужен

STATIC_HOST_DIR="${REMOTE_DIR}/static"
STATIC_POD_MOUNT="/srv/static"

log "Статика: проверяем hostPath volume в ingress-контроллере"
_HAS_STATIC="$(${SSH} "microk8s kubectl -n ingress get daemonset nginx-ingress-microk8s-controller -o yaml | grep -c 'platform-static' || true")"
if [[ "${_HAS_STATIC}" -gt 0 ]]; then
  log "Статика: hostPath volume уже смонтирован — пропускаем патч"
else
  log "Статика: патчим DaemonSet — монтируем ${STATIC_HOST_DIR} -> ${STATIC_POD_MOUNT}"
  ${SSH} "microk8s kubectl -n ingress patch daemonset nginx-ingress-microk8s-controller --type=strategic -p '{\"spec\":{\"template\":{\"spec\":{\"volumes\":[{\"name\":\"platform-static\",\"hostPath\":{\"path\":\"${STATIC_HOST_DIR}\",\"type\":\"DirectoryOrCreate\"}}],\"containers\":[{\"name\":\"nginx-ingress-microk8s\",\"volumeMounts\":[{\"name\":\"platform-static\",\"mountPath\":\"${STATIC_POD_MOUNT}\",\"readOnly\":true}]}]}}}}'"
  log "Статика: ожидаем перезапуск ingress-контроллера"
  ${SSH} "microk8s kubectl -n ingress rollout status daemonset nginx-ingress-microk8s-controller --timeout=120s"
fi

echo
echo "======================================"
echo " Ingress настроен"
echo "======================================"
${SSH} "microk8s kubectl get ingress && echo && microk8s kubectl get certificate"
echo
echo "  https://${DOMAIN}/"
jq -r '.ingress.services[] | select(.path != "/") | "  https://${DOMAIN}\(.path)"' "${CONF_LOCAL_JSON}" | DOMAIN="${DOMAIN}" envsubst
if [[ -n "${ONLYOFFICE_PORT}" ]] && [[ "${ONLYOFFICE_PORT}" != "null" ]]; then
  echo "  https://${ONLYOFFICE_SUBDOMAIN}/ (Document Server)"
fi
echo "  https://<company>.${DOMAIN}/ (поддомены компаний)"
echo "======================================"

log "Готово."
