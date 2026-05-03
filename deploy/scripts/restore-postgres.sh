#!/usr/bin/env bash
# Восстановление Postgres из дампа в pod postgres-0.
#
# Использование:
#   bash deploy/scripts/restore-postgres.sh <path/to/dump.sql.gz>
#   bash deploy/scripts/restore-postgres.sh --s3 s3://shvedzilla/backups/dump-...sql.gz
#
# ВНИМАНИЕ: дамп выполняется через psql с CLEAN/IF EXISTS — существующие БД будут удалены и пересозданы.
# Перед запуском: остановите приложения (kubectl scale deployment ... --replicas=0)
# или гарантируйте отсутствие активных сессий, иначе DROP DATABASE упадёт.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl 2>/dev/null || require_command microk8s || exit 1
K="$KUBECTL"

INPUT=""
S3_PATH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --s3) S3_PATH="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *)
      INPUT="$1"; shift
      ;;
  esac
done

# Скачиваем из S3 если нужно
TMP_FILE=""
if [ -n "$S3_PATH" ]; then
  require_command aws
  TMP_FILE="$(mktemp -t pgrestore.XXXXXX.sql.gz)"
  log_do "aws s3 cp $S3_PATH $TMP_FILE"
  aws s3 cp "$S3_PATH" "$TMP_FILE"
  INPUT="$TMP_FILE"
fi

if [ -z "$INPUT" ] || [ ! -f "$INPUT" ]; then
  log_error "Не указан путь к дампу или файла нет: '$INPUT'"
  exit 1
fi

log_section "Restore Postgres ← $INPUT"

# Sanity: подтверждение
if [ "${YES:-0}" != "1" ]; then
  printf 'Подтвердите перезапись данных в postgres-0 namespace=%s [yes/N]: ' "$PLATFORM_NS"
  read -r ans
  if [ "$ans" != "yes" ]; then
    log_warn "Отмена пользователем"
    [ -n "$TMP_FILE" ] && rm -f "$TMP_FILE"
    exit 1
  fi
fi

if ! $K get pod postgres-0 -n "$PLATFORM_NS" >/dev/null 2>&1; then
  log_error "Pod postgres-0 не найден"
  exit 1
fi

log_do "Стрим дампа в psql -U platform_user (через kubectl exec stdin)"

# Распаковываем (если .gz) и стримим в kubectl exec stdin
if [[ "$INPUT" == *.gz ]]; then
  gunzip -c "$INPUT"
else
  cat "$INPUT"
fi | $K exec -i -n "$PLATFORM_NS" postgres-0 -- \
  bash -lc 'psql -U platform_user -d postgres -v ON_ERROR_STOP=1' \
  || {
    log_error "psql упал — смотрите вывод выше"
    [ -n "$TMP_FILE" ] && rm -f "$TMP_FILE"
    exit 1
  }

[ -n "$TMP_FILE" ] && rm -f "$TMP_FILE"

log_ok "Restore завершён"
log_info "Список БД после restore:"
$K exec -n "$PLATFORM_NS" postgres-0 -- psql -U platform_user -d postgres -c '\l' | sed 's/^/    /'

print_summary
