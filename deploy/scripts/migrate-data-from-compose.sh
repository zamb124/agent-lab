#!/usr/bin/env bash
# Одноразовая миграция данных из старой docker compose инсталляции в новый Helm-кластер.
#
# Алгоритм:
#   1. SSH на старый хост (где жил docker-compose-prod.yaml).
#   2. docker exec agentlab_postgres pg_dumpall -U platform_user > /tmp/dump.sql.gz
#   3. scp дамп на локальную машину
#   4. kubectl cp в pod platform/postgres-0
#   5. psql -f внутри пода
#   6. Проверка: \l показывает все 7 БД
#   7. Удаляет временные файлы
#
# ENV:
#   OLD_HOST              = root@84.38.184.105 (где docker-compose-prod.yaml)
#   OLD_PG_CONTAINER      = agentlab_postgres
#   OLD_PG_USER           = platform_user
#   PLATFORM_NS           = platform
#   KEEP_DUMP             = 0|1 (по умолчанию 0 — удалить после restore)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl 2>/dev/null || require_command microk8s || exit 1
require_command ssh
require_command scp
K="$KUBECTL"

OLD_HOST="${OLD_HOST:-${SSH_USER}@${MASTER_HOST_IP}}"
OLD_PG_CONTAINER="${OLD_PG_CONTAINER:-agentlab_postgres}"
OLD_PG_USER="${OLD_PG_USER:-platform_user}"
KEEP_DUMP="${KEEP_DUMP:-0}"

EXPECTED_DBS=(platform_shared platform_agents platform_crm platform_sync platform_rag platform_office platform_tracing)

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_DUMP="$(pwd)/migrate-dump-${TS}.sql.gz"

log_section "Миграция Postgres из compose ($OLD_HOST) → K8s pod postgres-0"

# 1. Дамп на старом хосте
log_do "ssh $OLD_HOST: pg_dumpall в /tmp/dump.sql.gz внутри $OLD_PG_CONTAINER"
ssh -o BatchMode=yes "$OLD_HOST" "docker exec $OLD_PG_CONTAINER pg_dumpall -U $OLD_PG_USER --clean --if-exists | gzip > /tmp/migrate-dump-${TS}.sql.gz"

# 2. Копируем локально
log_do "scp $OLD_HOST:/tmp/migrate-dump-${TS}.sql.gz → $LOCAL_DUMP"
scp -o BatchMode=yes "$OLD_HOST:/tmp/migrate-dump-${TS}.sql.gz" "$LOCAL_DUMP"

if [ ! -s "$LOCAL_DUMP" ]; then
  log_error "Локальный дамп пустой"
  exit 1
fi
SIZE=$(du -h "$LOCAL_DUMP" | cut -f1)
log_ok "Дамп получен: $LOCAL_DUMP ($SIZE)"

# 3. Чистим временный файл на старом хосте (не падаем при ошибке)
ssh -o BatchMode=yes "$OLD_HOST" "rm -f /tmp/migrate-dump-${TS}.sql.gz" || \
  log_warn "Не удалось удалить временный файл на $OLD_HOST"

# 4. Restore в pod postgres-0
log_do "Restore в platform/postgres-0 (через kubectl exec stdin)"
gunzip -c "$LOCAL_DUMP" | $K exec -i -n "$PLATFORM_NS" postgres-0 -- \
  bash -lc 'psql -U platform_user -d postgres -v ON_ERROR_STOP=1' \
  || {
    log_error "psql упал при restore"
    exit 1
  }

# 5. Проверка списка БД
log_section "Проверка БД после restore"
DB_LIST=$($K exec -n "$PLATFORM_NS" postgres-0 -- psql -U platform_user -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname LIKE 'platform_%' ORDER BY datname;")
printf '%s\n' "$DB_LIST" | sed 's/^/    /'

MISSING=()
for db in "${EXPECTED_DBS[@]}"; do
  if ! printf '%s' "$DB_LIST" | grep -qx "$db"; then
    MISSING+=("$db")
  fi
done

if [ "${#MISSING[@]}" -eq 0 ]; then
  log_ok "Все 7 ожидаемых БД на месте"
else
  log_error "Отсутствуют БД: ${MISSING[*]}"
  exit 1
fi

# 6. Очистка
if [ "$KEEP_DUMP" = "1" ]; then
  log_info "Локальный дамп сохранён: $LOCAL_DUMP"
else
  rm -f "$LOCAL_DUMP"
  log_ok "Локальный дамп удалён"
fi

print_summary
