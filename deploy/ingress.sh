#!/usr/bin/env bash
# Настройка MicroK8s Ingress + cert-manager (Let's Encrypt) на сервере.
# Читает домен и поддомены из conf.local.json -> ingress.
# Запускается локально, все команды выполняются на сервере по SSH.
#
# Структура conf.local.json:
#   "ingress": {
#     "domain": "example.com",
#     "email": "admin@example.com",
#     "subdomains": [
#       {"name": "sync", "port": 8005, "websocket": true},
#       {"name": "agents", "port": 8001, "websocket": false},
#       {"name": "crm", "port": 8003, "websocket": false},
#       {"name": "rag", "port": 8004, "websocket": false}
#     ]
#   }
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONF_LOCAL_JSON="${CONF_LOCAL_JSON:-${PROJECT_ROOT}/conf.local.json}"

log() {
  printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Локально не найдена команда '$1'. Установите её и повторите." >&2
    exit 1
  fi
}

require_cmd jq
require_cmd ssh

if [[ ! -f "${CONF_LOCAL_JSON}" ]]; then
  echo "Не найден файл конфигурации: ${CONF_LOCAL_JSON}" >&2
  exit 1
fi

ip="$(jq -er '.selectel.ip' "${CONF_LOCAL_JSON}")"
login="$(jq -er '.selectel.login' "${CONF_LOCAL_JSON}")"
ssh_port="$(jq -r '.selectel.ssh_port // "22"' "${CONF_LOCAL_JSON}")"
domain="$(jq -er '.ingress.domain' "${CONF_LOCAL_JSON}")"
email="$(jq -er '.ingress.email' "${CONF_LOCAL_JSON}")"

# "sync:8005:true agents:8001:false crm:8003:false"
subdomains_str="$(jq -r '.ingress.subdomains[] | "\(.name):\(.port):\(.websocket // false)"' "${CONF_LOCAL_JSON}" | tr '\n' ' ')"

log "Домен: ${domain}"
log "Поддомены: ${subdomains_str}"
log "Подключаюсь к серверу: ${login}@${ip}:${ssh_port}"

ssh \
  -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -p "${ssh_port}" \
  "${login}@${ip}" \
  DOMAIN="${domain}" EMAIL="${email}" SUBDOMAINS="${subdomains_str}" \
  "bash -s" <<'REMOTE_SCRIPT'

set -euo pipefail

log() {
  printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

# cert-manager
if microk8s kubectl get namespace cert-manager >/dev/null 2>&1; then
  log "cert-manager уже установлен, пропускаем"
else
  log "Включаем cert-manager"
  microk8s enable cert-manager
  microk8s kubectl wait --for=condition=ready pod \
    -l app=cert-manager -n cert-manager --timeout=120s
fi

# ClusterIssuer (Let's Encrypt)
log "Применяем ClusterIssuer (Let's Encrypt)"
microk8s kubectl apply -f - <<EOF
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

# Service + Endpoints для каждого поддомена
HOST_IP="$(ip -4 addr show scope global | awk '/inet / {print $2}' | awk -F/ '{print $1}' | head -1)"
log "IP хоста для Endpoints: ${HOST_IP}"

for entry in ${SUBDOMAINS}; do
  IFS=':' read -r sub port ws <<< "${entry}"
  svc_name="${sub}-svc"
  log "Настраиваем Service/Endpoints: ${svc_name} -> ${HOST_IP}:${port}"

  microk8s kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${svc_name}
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
  name: ${svc_name}
  namespace: default
subsets:
- addresses:
  - ip: ${HOST_IP}
  ports:
  - port: ${port}
EOF
done

# Ingress для каждого поддомена
for entry in ${SUBDOMAINS}; do
  IFS=':' read -r sub port ws <<< "${entry}"
  fqdn="${sub}.${DOMAIN}"
  svc_name="${sub}-svc"
  secret_name="${sub}-$(echo "${DOMAIN}" | tr '.' '-')-tls"
  ingress_name="${sub}-ingress"

  log "Настраиваем Ingress: ${fqdn} -> ${svc_name}:${port}"

  ws_annotations=""
  if [[ "${ws}" == "true" ]]; then
    ws_annotations='
    nginx.ingress.kubernetes.io/proxy-http-version: "1.1"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";'
  fi

  microk8s kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${ingress_name}
  namespace: default
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"${ws_annotations}
spec:
  ingressClassName: public
  tls:
  - hosts:
    - ${fqdn}
    secretName: ${secret_name}
  rules:
  - host: ${fqdn}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ${svc_name}
            port:
              number: ${port}
EOF
done

# Итог
log "Ожидаем выдачи сертификатов (~30 сек)"
sleep 30

echo
echo "======================================"
echo " Ingress настроен"
echo "======================================"
echo
microk8s kubectl get ingress
echo
microk8s kubectl get certificate
echo
for entry in ${SUBDOMAINS}; do
  IFS=':' read -r sub port ws <<< "${entry}"
  echo "  https://${sub}.${DOMAIN}"
done
echo "======================================"

REMOTE_SCRIPT

log "Готово."
