#!/usr/bin/env bash
# Полная настройка сервера: MicroK8s + Docker Engine + Portainer Agent + /opt/agent-lab
# Запускается локально, все команды выполняются на сервере по SSH.
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

ssh-keygen -R "${ip}" 2>/dev/null || true
ssh-keygen -R "[${ip}]:${ssh_port}" 2>/dev/null || true

log "Подключаюсь к серверу: ${login}@${ip}:${ssh_port}"

ssh \
  -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -p "${ssh_port}" \
  "${login}@${ip}" \
  "bash -s" <<'REMOTE_SCRIPT'

set -euo pipefail

log() {
  printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO="sudo"
fi

CURRENT_USER="$(id -un)"
MICROK8S_CHANNEL="${MICROK8S_CHANNEL:-1.29/stable}"

# MicroK8s
log "Установка MicroK8s (channel: ${MICROK8S_CHANNEL})"
if ! command -v microk8s >/dev/null 2>&1; then
  ${SUDO} snap install microk8s --classic --channel="${MICROK8S_CHANNEL}"
else
  log "MicroK8s уже установлен, пропускаем"
fi

log "Ожидание готовности кластера"
${SUDO} microk8s status --wait-ready

enable_addon() {
  local addon="$1"
  if ${SUDO} microk8s status --format short 2>/dev/null | grep -q "^enabled:.*\b${addon}\b"; then
    log "Addon '${addon}' уже включён, пропускаем"
  else
    log "Включаем addon '${addon}'"
    ${SUDO} microk8s enable "${addon}"
  fi
}

log "Включение addon-ов MicroK8s"
enable_addon community
enable_addon dns
enable_addon hostpath-storage
enable_addon helm
enable_addon metrics-server
enable_addon dashboard
enable_addon portainer

log "Итоговая проверка кластера"
${SUDO} microk8s status --wait-ready

# Docker Engine
if command -v docker >/dev/null 2>&1; then
  log "Docker уже установлен: $(docker --version)"
else
  log "Устанавливаем Docker Engine"
  ${SUDO} apt-get update -qq
  ${SUDO} apt-get install -y -qq ca-certificates curl gnupg
  ${SUDO} install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | ${SUDO} gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  ${SUDO} chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | ${SUDO} tee /etc/apt/sources.list.d/docker.list > /dev/null
  ${SUDO} apt-get update -qq
  ${SUDO} apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  log "Docker установлен: $(docker --version)"
fi

if ! id -nG "${CURRENT_USER}" | grep -qw docker; then
  ${SUDO} usermod -aG docker "${CURRENT_USER}"
  log "Пользователь ${CURRENT_USER} добавлен в группу docker"
fi

# Portainer Agent
if docker ps -a --format '{{.Names}}' | grep -q '^portainer_agent$'; then
  log "Portainer Agent уже запущен, пропускаем"
else
  log "Запускаем Portainer Agent"
  docker run -d \
    --name portainer_agent \
    --restart unless-stopped \
    -p 9001:9001 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /var/lib/docker/volumes:/var/lib/docker/volumes \
    portainer/agent:latest
fi

# Рабочая директория /opt/agent-lab
log "Создаём /opt/agent-lab"
${SUDO} mkdir -p /opt/agent-lab
${SUDO} chown "${CURRENT_USER}:${CURRENT_USER}" /opt/agent-lab

if [[ ! -f /opt/agent-lab/.env ]]; then
  log "Создаём шаблон /opt/agent-lab/.env"
  printf 'IMAGE=ghcr.io/<GITHUB_USERNAME>/agent-lab:latest\nPOSTGRES_PASSWORD=\nAUTH__JWT_SECRET=\n' \
    > /opt/agent-lab/.env
  log "Заполните /opt/agent-lab/.env перед первым деплоем"
else
  log "/opt/agent-lab/.env уже существует, не перезаписываем"
fi

# Итог
NODE_IP="$(ip -4 addr show scope global 2>/dev/null \
  | awk '/inet / {print $2}' \
  | awk -F/ '{print $1}' \
  | head -n 1 || true)"

[[ -z "${NODE_IP}" ]] && NODE_IP="IP_СЕРВЕРА"

echo
echo "======================================"
echo " Настройка завершена"
echo "======================================"
echo
echo "Portainer (K8s панель):"
echo "  http://${NODE_IP}:30777"
echo
echo "Portainer Agent (Docker):"
echo "  Добавь окружение в Portainer: ${NODE_IP}:9001"
echo "  Home -> Add environment -> Docker Standalone -> Agent"
echo
echo "Платформа после деплоя:"
echo "  agents:   http://${NODE_IP}:8001"
echo "  frontend: http://${NODE_IP}:8002"
echo "  crm:      http://${NODE_IP}:8003"
echo "  rag:      http://${NODE_IP}:8004"
echo "  sync:     http://${NODE_IP}:8005"
echo "======================================"

REMOTE_SCRIPT

log "Сервер готов."
