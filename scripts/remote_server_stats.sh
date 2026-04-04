#!/usr/bin/env bash
# Сборка снимка нагрузки на удалённом хосте по SSH.
# Переменные: SSH_USER, SSH_HOST, REMOTE_DIR, STATS_COMPOSE_FILE (опционально).

set -euo pipefail

SSH_USER="${SSH_USER:?Укажите SSH_USER (например через Makefile)}"
SSH_HOST="${SSH_HOST:?Укажите SSH_HOST}"
REMOTE_DIR="${REMOTE_DIR:-/opt/agent-lab}"
COMPOSE_FILE="${STATS_COMPOSE_FILE:-docker-compose-prod.yaml}"

remote_cmd=$(printf '%q' "$REMOTE_DIR")
remote_compose=$(printf '%q' "$COMPOSE_FILE")

ssh -o BatchMode=yes -o ConnectTimeout=15 "${SSH_USER}@${SSH_HOST}" \
  "REMOTE_DIR=${remote_cmd} COMPOSE_FILE=${remote_compose} bash -s" <<'REMOTE'
set -euo pipefail

section() {
  printf '\n'
  local title="$1"
  local w=72
  printf '%*s\n' "$w" | tr ' ' '='
  printf ' %s\n' "$title"
  printf '%*s\n' "$w" | tr ' ' '='
}

docker_bin() {
  if docker info &>/dev/null; then
    echo docker
  else
    echo sudo docker
  fi
}

DOC=$(docker_bin)

section "Хост"
hostname -f 2>/dev/null || hostname
date -u "+%Y-%m-%d %H:%M:%S UTC"
uname -srvmo

section "Нагрузка"
uptime

section "Память"
free -h

section "Диски (без виртуальных fs)"
df -hT 2>/dev/null | awk 'NR==1 || /^\/dev\// {print}' || df -h

section "Топ процессов по памяти (10 строк)"
ps aux --sort=-%mem 2>/dev/null | head -n 11 || true

section "Docker: контейнеры (снимок CPU/RAM/IO)"
$DOC stats --no-stream 2>/dev/null || true

section "Docker: список контейнеров"
$DOC ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true

section "Compose в REMOTE_DIR"
if [[ -d "$REMOTE_DIR" && -f "$REMOTE_DIR/$COMPOSE_FILE" ]]; then
  cd "$REMOTE_DIR"
  $DOC compose -f "$COMPOSE_FILE" ps -a 2>/dev/null || true
else
  printf 'Каталог %s или файл %s не найдены (пропуск compose ps).\n' "$REMOTE_DIR" "$COMPOSE_FILE"
fi

section "Сетевые интерфейсы (кратко)"
ip -br addr 2>/dev/null || true

if command -v microk8s &>/dev/null; then
  section "MicroK8s (если установлен)"
  sudo microk8s kubectl get nodes 2>/dev/null || true
  sudo microk8s kubectl get pods -A 2>/dev/null | head -n 30 || true
fi

printf '\n'
REMOTE
