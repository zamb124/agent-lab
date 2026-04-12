#!/usr/bin/env bash
# Подготовка статики для ingress на сервере.
# Извлекает UI файлы из Docker образа в единую структуру static/,
# чтобы nginx ingress мог отдавать их напрямую.
#
# Структура после выполнения:
#   static/core/           ← /app/core/frontend/static/ из образа
#   static/crm/ui/         ← /app/apps/crm/ui/ из образа
#   static/sync/ui/        ← /app/apps/sync/ui/ из образа
#   static/rag/ui/         ← /app/apps/rag/ui/ из образа
#   static/documents/ui/   ← /app/apps/office/ui/ из образа
#   static/flows/ui/       ← /app/apps/flows/ui/ из образа
#   static/frontend/       ← /app/apps/frontend/ui/ из образа
#   static/i18n/           ← сгенерировано python скриптом из образа

set -euo pipefail

REMOTE_DIR="${REMOTE_DIR:-/opt/agent-lab}"
IMAGE="${IMAGE:-ghcr.io/zamb124/agent-lab:latest}"

log() {
  printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "Подготовка статики в ${REMOTE_DIR} из образа ${IMAGE}"

mkdir -p "${REMOTE_DIR}/static"

# Создаём временный контейнер для извлечения файлов
CONTAINER_ID="$(docker create "${IMAGE}")"
log "Временный контейнер: ${CONTAINER_ID}"

copy_from_image() {
  local src="$1"
  local dst="$2"
  log "Извлекаем ${src} → ${dst}"
  rm -rf "${dst}"
  mkdir -p "$(dirname "${dst}")"
  if docker cp "${CONTAINER_ID}:${src}" "${dst}" 2>/dev/null; then
    log "  OK: ${dst}"
  else
    log "  WARNING: Не найдено ${src} в образе"
  fi
}

copy_from_image /app/core/frontend/static               "${REMOTE_DIR}/static/core"
copy_from_image /app/apps/crm/ui                        "${REMOTE_DIR}/static/crm/ui"
copy_from_image /app/apps/sync/ui                       "${REMOTE_DIR}/static/sync/ui"
copy_from_image /app/apps/rag/ui                        "${REMOTE_DIR}/static/rag/ui"
copy_from_image /app/apps/office/ui                     "${REMOTE_DIR}/static/documents/ui"
copy_from_image /app/apps/flows/ui                      "${REMOTE_DIR}/static/flows/ui"
copy_from_image /app/apps/frontend/ui                   "${REMOTE_DIR}/static/frontend"
copy_from_image /app/node_modules/3d-force-graph/dist   "${REMOTE_DIR}/static/crm/ui/vendor/3d-force-graph"
copy_from_image /app/node_modules/three/build           "${REMOTE_DIR}/static/crm/ui/vendor/three"

docker rm "${CONTAINER_ID}" >/dev/null
log "Временный контейнер удалён"

log "Генерация объединённых i18n переводов"
mkdir -p "${REMOTE_DIR}/static/i18n"
docker run --rm --workdir /app \
  -v "${REMOTE_DIR}/static/i18n:/output" \
  "${IMAGE}" \
  python /app/scripts/build_i18n.py --output /output

log "✅ Статика подготовлена"

echo
log "Структура static/:"
find "${REMOTE_DIR}/static" -maxdepth 3 -type d | sed "s|${REMOTE_DIR}||"
