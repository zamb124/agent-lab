#!/usr/bin/env bash
# Подготовка статики для ingress на сервере.
# Копирует UI файлы из apps/*/ui/ в единую структуру static/,
# чтобы nginx ingress мог отдавать их напрямую.
#
# Использование (локально для тестов):
#   bash deploy/prepare-static.sh
#
# Использование (на сервере через SSH):
#   ssh user@server "cd /opt/agent-lab && bash deploy/prepare-static.sh"
#
# Структура после выполнения:
#   static/core/           ← core/frontend/static/
#   static/crm/ui/         ← apps/crm/ui/
#   static/sync/ui/        ← apps/sync/ui/
#   static/rag/ui/         ← apps/rag/ui/
#   static/documents/ui/   ← apps/office/ui/
#   static/flows/ui/       ← apps/flows/ui/
#   static/frontend/       ← apps/frontend/ui/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Определяем_REMOTE_DIR из конфига или используем дефолт
CONF_LOCAL_JSON="${CONF_LOCAL_JSON:-${PROJECT_ROOT}/conf.local.json}"
if [[ -f "${CONF_LOCAL_JSON}" ]]; then
  REMOTE_DIR="$(jq -r '.selectel.remote_dir // "/opt/agent-lab"' "${CONF_LOCAL_JSON}")"
else
  REMOTE_DIR="${PROJECT_ROOT}"
fi

log() {
  printf "\n[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "Подготовка статики в ${REMOTE_DIR}"

# Создаём директорию static
mkdir -p "${REMOTE_DIR}/static"

# Копируем core/frontend/static → static/core
if [[ -d "${REMOTE_DIR}/core/frontend/static" ]]; then
  log "Копируем core/frontend/static → static/core"
  rm -rf "${REMOTE_DIR}/static/core"
  cp -r "${REMOTE_DIR}/core/frontend/static" "${REMOTE_DIR}/static/core"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/core/frontend/static"
fi

# Копируем apps/crm/ui → static/crm/ui
if [[ -d "${REMOTE_DIR}/apps/crm/ui" ]]; then
  log "Копируем apps/crm/ui → static/crm/ui"
  rm -rf "${REMOTE_DIR}/static/crm"
  mkdir -p "${REMOTE_DIR}/static/crm"
  cp -r "${REMOTE_DIR}/apps/crm/ui" "${REMOTE_DIR}/static/crm"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/crm/ui"
fi

# Копируем apps/sync/ui → static/sync/ui
if [[ -d "${REMOTE_DIR}/apps/sync/ui" ]]; then
  log "Копируем apps/sync/ui → static/sync/ui"
  rm -rf "${REMOTE_DIR}/static/sync"
  mkdir -p "${REMOTE_DIR}/static/sync"
  cp -r "${REMOTE_DIR}/apps/sync/ui" "${REMOTE_DIR}/static/sync"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/sync/ui"
fi

# Копируем apps/rag/ui → static/rag/ui
if [[ -d "${REMOTE_DIR}/apps/rag/ui" ]]; then
  log "Копируем apps/rag/ui → static/rag/ui"
  rm -rf "${REMOTE_DIR}/static/rag"
  mkdir -p "${REMOTE_DIR}/static/rag"
  cp -r "${REMOTE_DIR}/apps/rag/ui" "${REMOTE_DIR}/static/rag"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/rag/ui"
fi

# Копируем apps/office/ui → static/documents/ui
if [[ -d "${REMOTE_DIR}/apps/office/ui" ]]; then
  log "Копируем apps/office/ui → static/documents/ui"
  rm -rf "${REMOTE_DIR}/static/documents"
  mkdir -p "${REMOTE_DIR}/static/documents"
  cp -r "${REMOTE_DIR}/apps/office/ui" "${REMOTE_DIR}/static/documents"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/office/ui"
fi

# Копируем apps/flows/ui → static/flows/ui
if [[ -d "${REMOTE_DIR}/apps/flows/ui" ]]; then
  log "Копируем apps/flows/ui → static/flows/ui"
  rm -rf "${REMOTE_DIR}/static/flows"
  mkdir -p "${REMOTE_DIR}/static/flows"
  cp -r "${REMOTE_DIR}/apps/flows/ui" "${REMOTE_DIR}/static/flows"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/flows/ui"
fi

# Копируем apps/frontend/ui → static/frontend
if [[ -d "${REMOTE_DIR}/apps/frontend/ui" ]]; then
  log "Копируем apps/frontend/ui → static/frontend"
  rm -rf "${REMOTE_DIR}/static/frontend"
  cp -r "${REMOTE_DIR}/apps/frontend/ui" "${REMOTE_DIR}/static/frontend"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/apps/frontend/ui"
fi

# Vendor для CRM (3d-force-graph и three)
# Копируем только нужные директории из node_modules
if [[ -d "${REMOTE_DIR}/node_modules/3d-force-graph/dist" ]]; then
  log "Копируем 3d-force-graph vendor"
  mkdir -p "${REMOTE_DIR}/static/crm/ui/vendor"
  rm -rf "${REMOTE_DIR}/static/crm/ui/vendor/3d-force-graph"
  cp -r "${REMOTE_DIR}/node_modules/3d-force-graph/dist" "${REMOTE_DIR}/static/crm/ui/vendor/3d-force-graph"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/node_modules/3d-force-graph/dist"
fi

if [[ -d "${REMOTE_DIR}/node_modules/three/build" ]]; then
  log "Копируем three vendor"
  mkdir -p "${REMOTE_DIR}/static/crm/ui/vendor"
  rm -rf "${REMOTE_DIR}/static/crm/ui/vendor/three"
  cp -r "${REMOTE_DIR}/node_modules/three/build" "${REMOTE_DIR}/static/crm/ui/vendor/three"
else
  log "WARNING: Не найдено ${REMOTE_DIR}/node_modules/three/build"
fi

log "✅ Статика подготовлена"

# Выводим структуру для отладки
echo
log "Структура static/:"
find "${REMOTE_DIR}/static" -type d | head -30 | sed "s|${REMOTE_DIR}||"
