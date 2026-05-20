#!/usr/bin/env bash
# Полный снос legacy docker compose стека на хосте по SSH.
# CONFIRM=0 (dry-run, default) | 1 (реальный снос).
# Шаги (CONFIRM=1): docker compose down --volumes --rmi all, docker rm -f, volume rm,
# Выполняет network rm, rmi -f, system prune -af --volumes, rm -rf COMPOSE_DIR / EXTRA_DIRS.
# Makefile: make k8s-decommission-compose [SSH_TARGET=root@<host>] [CONFIRM=1]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command ssh

SSH_TARGET="${SSH_TARGET:-${SSH_USER}@${MASTER_HOST_IP}}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/agent-lab/docker-compose-prod.yaml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-agentlab-prod}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/agent-lab}"
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/zamb124/agent-lab}"
EXTRA_DIRS="${EXTRA_DIRS:-/opt/sync}"
CONFIRM="${CONFIRM:-0}"

log_section "Decommission docker compose: $SSH_TARGET (CONFIRM=$CONFIRM)"

# Инвентаризация: что есть на хосте.
remote_inventory() {
  ssh -o BatchMode=yes "$SSH_TARGET" "bash -s" <<EOF
set -uo pipefail
echo '--containers--'
docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null \\
  | grep -E '^(agentlab_|${COMPOSE_PROJECT}-)' || true
echo '--volumes--'
docker volume ls -q 2>/dev/null | grep -E "^${COMPOSE_PROJECT}_" || true
echo '--networks--'
docker network ls --format '{{.Name}}' 2>/dev/null | grep -E "^${COMPOSE_PROJECT}_" || true
echo '--images--'
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' 2>/dev/null \\
  | grep -E "^${IMAGE_NAME}:" || true
echo '--dirs--'
for d in $COMPOSE_DIR $EXTRA_DIRS; do
  if [ -e "\$d" ]; then echo "\$d EXISTS"; fi
done
EOF
}

INVENTORY="$(remote_inventory)"
printf '%s\n' "$INVENTORY" | sed 's/^/    /'

if [ "$CONFIRM" != "1" ]; then
  log_info "DRY-RUN: ничего не удалено. Для реального сноса: CONFIRM=1 bash $0"
  exit 0
fi

# Реальный снос.
log_section "Снос (CONFIRM=1)"
ssh -o BatchMode=yes "$SSH_TARGET" "bash -s" <<EOF
set -uo pipefail

# 1. compose down (если файл есть и проект жив).
if [ -f "$COMPOSE_FILE" ] && docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps -q 2>/dev/null | grep -q .; then
  echo "[DO]    docker compose down --volumes --remove-orphans --rmi all"
  docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" down --volumes --remove-orphans --rmi all || true
else
  echo "[SKIP]  docker compose down (файл нет или проект не запущен)"
fi

# 2. Висящие контейнеры (если down оставил).
LEFT=\$(docker ps -a -q --filter "name=^agentlab_" --filter "name=^${COMPOSE_PROJECT}-" 2>/dev/null | tr '\\n' ' ')
if [ -n "\$LEFT" ]; then
  echo "[DO]    docker rm -f <agentlab_* / ${COMPOSE_PROJECT}-*>"
  docker rm -f \$LEFT || true
else
  echo "[SKIP]  висящих agentlab_* контейнеров нет"
fi

# 3. Volumes.
VOLS=\$(docker volume ls -q 2>/dev/null | grep -E "^${COMPOSE_PROJECT}_" | tr '\\n' ' ' || true)
if [ -n "\$VOLS" ]; then
  echo "[DO]    docker volume rm ${COMPOSE_PROJECT}_*"
  docker volume rm \$VOLS || true
else
  echo "[SKIP]  volumes ${COMPOSE_PROJECT}_* отсутствуют"
fi

# 4. Networks.
NETS=\$(docker network ls --format '{{.Name}}' 2>/dev/null | grep -E "^${COMPOSE_PROJECT}_" | tr '\\n' ' ' || true)
if [ -n "\$NETS" ]; then
  echo "[DO]    docker network rm ${COMPOSE_PROJECT}_*"
  docker network rm \$NETS || true
else
  echo "[SKIP]  networks ${COMPOSE_PROJECT}_* отсутствуют"
fi

# 5. Образы.
IMGS=\$(docker images -q "$IMAGE_NAME" 2>/dev/null | sort -u | tr '\\n' ' ' || true)
if [ -n "\$IMGS" ]; then
  echo "[DO]    docker rmi -f $IMAGE_NAME (все теги)"
  docker rmi -f \$IMGS || true
else
  echo "[SKIP]  образов $IMAGE_NAME нет"
fi

# 6. Финальный prune (висячие слои/контейнеры/сети).
echo "[DO]    docker system prune -af --volumes"
docker system prune -af --volumes 2>&1 | tail -3 || true

# 7. Каталоги compose.
for d in $COMPOSE_DIR $EXTRA_DIRS; do
  if [ -e "\$d" ]; then
    echo "[DO]    rm -rf \$d"
    rm -rf "\$d"
  else
    echo "[SKIP]  \$d отсутствует"
  fi
done

echo "[OK]    decommission complete on \$(hostname)"
EOF

log_section "Проверка после сноса"
remote_inventory | sed 's/^/    /'

print_summary
