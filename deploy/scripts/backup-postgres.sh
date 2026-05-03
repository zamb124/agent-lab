#!/usr/bin/env bash
# Бэкап Postgres из K8s кластера: pg_dumpall → gzip → локальный файл (или S3).
# Запускать локально с настроенным kubectl или с master ноды.
#
# Использование:
#   bash deploy/scripts/backup-postgres.sh                        # → backups/dump-<ts>.sql.gz
#   bash deploy/scripts/backup-postgres.sh --out /tmp/dump.sql.gz # явный путь
#   bash deploy/scripts/backup-postgres.sh --s3 s3://shvedzilla/backups/   # + загрузка в S3
#
# Безопасность:
#   - Использует kubectl exec (без проброса портов и пароля в командной строке).
#   - PGPASSWORD читается из Secret platform-secrets внутри пода.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

require_command kubectl 2>/dev/null || require_command microk8s || exit 1
K="$KUBECTL"

OUT_PATH=""
S3_PREFIX=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_PATH="$2"; shift 2 ;;
    --s3)  S3_PREFIX="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      log_error "Unknown arg: $1"
      exit 1
      ;;
  esac
done

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -z "$OUT_PATH" ]; then
  mkdir -p backups
  OUT_PATH="backups/dump-${TIMESTAMP}.sql.gz"
fi

log_section "Backup Postgres → $OUT_PATH"

# Проверка пода
if ! $K get pod postgres-0 -n "$PLATFORM_NS" >/dev/null 2>&1; then
  log_error "Pod postgres-0 не найден в namespace $PLATFORM_NS"
  exit 1
fi

log_do "kubectl exec postgres-0 -- pg_dumpall | gzip > $OUT_PATH"

# Pipe через kubectl exec без TTY — критично, иначе бинарный gzip битый
$K exec -n "$PLATFORM_NS" postgres-0 -- \
  bash -lc 'pg_dumpall -U platform_user --clean --if-exists' \
  | gzip > "$OUT_PATH"

if [ ! -s "$OUT_PATH" ]; then
  log_error "Дамп пустой!"
  rm -f "$OUT_PATH"
  exit 1
fi

SIZE=$(du -h "$OUT_PATH" | cut -f1)
log_ok "Локальный дамп готов: $OUT_PATH ($SIZE)"

# S3 (опционально)
if [ -n "$S3_PREFIX" ]; then
  if ! command -v aws >/dev/null 2>&1; then
    log_error "Утилита 'aws' не найдена; нужна для --s3 (или используйте rclone)"
    exit 1
  fi
  S3_URL="${S3_PREFIX%/}/dump-${TIMESTAMP}.sql.gz"
  log_do "aws s3 cp $OUT_PATH $S3_URL"
  if [ -z "${AWS_ENDPOINT_URL:-}" ]; then
    log_warn "AWS_ENDPOINT_URL не задан — для Selectel S3 укажите https://s3.ru-3.storage.selcloud.ru"
  fi
  aws s3 cp "$OUT_PATH" "$S3_URL"
  log_ok "Загружено в $S3_URL"
fi

print_summary
