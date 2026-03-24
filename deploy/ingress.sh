#!/usr/bin/env bash
# Настройка MicroK8s Ingress + cert-manager (Let's Encrypt) на сервере.
#
# Архитектура:
#   domain.com/         → frontend  (8002)
#   domain.com/agents   → agents    (8001)
#   domain.com/crm      → crm       (8003)
#   domain.com/rag      → rag       (8004)
#   domain.com/sync     → sync      (8005, websocket)
#   *.domain.com/*      → те же правила (поддомены компаний)
#
# Конфиг в conf.local.json:
#   "selectel": { "ip": "...", "login": "...", "ssh_port": "22" }
#   "ingress": {
#     "domain": "humanitec.ru",
#     "email": "admin@humanitec.ru",
#     "services": [
#       {"name": "frontend", "port": 8002, "path": "/",      "websocket": false},
#       {"name": "agents",   "port": 8001, "path": "/flows","websocket": false},
#       {"name": "crm",      "port": 8003, "path": "/crm",   "websocket": false},
#       {"name": "rag",      "port": 8004, "path": "/rag",   "websocket": false},
#       {"name": "sync",     "port": 8005, "path": "/sync",  "websocket": true}
#     ]
#   }
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

SSH="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10 -p ${SSH_PORT} ${LOGIN}@${IP}"

# Получаем IP хоста на сервере
HOST_IP="$(${SSH} "ip -4 addr show scope global | awk '/inet / {print \$2}' | awk -F/ '{print \$1}' | head -1")"
log "IP хоста: ${HOST_IP}"

# cert-manager
log "Проверяем cert-manager"
${SSH} "microk8s kubectl get namespace cert-manager >/dev/null 2>&1 || (microk8s enable cert-manager && microk8s kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=120s)"

# ClusterIssuer
log "ClusterIssuer (Let's Encrypt)"
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

# Генерируем paths для ingress
build_paths() {
  jq -r '
    .ingress.services
    | sort_by(.path | length)
    | reverse
    | .[]
    | "      - path: \(.path)\n        pathType: Prefix\n        backend:\n          service:\n            name: \(.name)-svc\n            port:\n              number: \(.port)"
  ' "${CONF_LOCAL_JSON}"
}

PATHS="$(build_paths)"

# Ingress: TLS только на apex. Wildcard *.domain в одном Certificate с HTTP-01 выдать нельзя
# (нужен DNS-01) — иначе заказ ACME зависает в pending без Secret. Поддомены компаний: см. deploy/wildcard-tls.md
TLS_SECRET="$(echo "${DOMAIN}" | tr '.' '-')-tls"

log "Создаём Ingress для ${DOMAIN} и *.${DOMAIN}"
${SSH} "microk8s kubectl apply -f -" <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: humanitec-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection "upgrade";
spec:
  ingressClassName: public
  tls:
  - hosts:
    - ${DOMAIN}
    secretName: ${TLS_SECRET}
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
# Браузеры требуют WSS (wss://) — LiveKit должен быть доступен через HTTPS/WSS.
# Отдельный поддомен позволяет получить Let's Encrypt сертификат через HTTP-01.
LIVEKIT_SUBDOMAIN="livekit.${DOMAIN}"
LIVEKIT_TLS_SECRET="$(echo "${LIVEKIT_SUBDOMAIN}" | tr '.' '-')-tls"
LIVEKIT_PORT=7880

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

log "Создаём Ingress для ${LIVEKIT_SUBDOMAIN}"
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
    nginx.ingress.kubernetes.io/configuration-snippet: |
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection "upgrade";
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

if ${SSH} "microk8s kubectl get secret ${LIVEKIT_TLS_SECRET} -n default >/dev/null 2>&1"; then
  log "Certificate ${LIVEKIT_TLS_SECRET} уже существует — пропускаем"
else
  log "Certificate (Let's Encrypt HTTP-01) для ${LIVEKIT_SUBDOMAIN}"
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

echo
echo "======================================"
echo " Ingress настроен"
echo "======================================"
${SSH} "microk8s kubectl get ingress && echo && microk8s kubectl get certificate"
echo
echo "  https://${DOMAIN}/"
jq -r '.ingress.services[] | select(.path != "/") | "  https://${DOMAIN}\(.path)"' "${CONF_LOCAL_JSON}" | DOMAIN="${DOMAIN}" envsubst
echo "  https://<company>.${DOMAIN}/ (поддомены компаний)"
echo "======================================"

log "Готово."
