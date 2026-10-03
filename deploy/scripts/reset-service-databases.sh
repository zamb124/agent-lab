#!/usr/bin/env bash
# Пустые сервисные БД Postgres и сброс Redis. Дальше db-migrate накатывает цепочку с 0001_initial.
# Старая схема не переносится: базы дропаются и создаются заново.
# Перед запуском — make k8s-backup. После — деплой нового образа (init db-migrate).
#
#   CONFIRM=1 bash deploy/scripts/reset-service-databases.sh
#
# Не трогает PVC, Loki, Tempo, Grafana и SeaweedFS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

if [ "${CONFIRM:-}" != "1" ]; then
  log_error "Отказ: это удалит данные сервисных БД и Redis. Запуск: CONFIRM=1 bash deploy/scripts/reset-service-databases.sh"
  exit 1
fi

require_command kubectl
K="$KUBECTL"
NS="${PLATFORM_NS:-platform}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$REPO_ROOT/migrations/services.json"

if [ ! -f "$MANIFEST" ]; then
  log_error "нет $MANIFEST"
  exit 1
fi

if ! $K get pod postgres-0 -n "$NS" >/dev/null 2>&1; then
  log_error "Pod postgres-0 не найден в namespace $NS"
  exit 1
fi

# Поды со старым образом не должны подняться и записать схему до нового деплоя.
SCALE_DOWN=(
  flows frontend crm rag sync worktracker office wiki guest-runtime realtime scheduler-api voice browser search secrets
  capability-gateway code-runner-python code-runner-node code-runner-go code-runner-csharp
  flows-worker scheduler rag-worker sync-worker crm-worker crm-summary-worker idle-worker search-worker
  openfga centrifugo
)

log_section "Scale app/worker/openfga to 0"
for deploy in "${SCALE_DOWN[@]}"; do
  if $K get deploy "$deploy" -n "$NS" >/dev/null 2>&1; then
    log_do "scale $deploy --replicas=0"
    $K scale "deploy/$deploy" -n "$NS" --replicas=0
  else
    log_skip "deploy/$deploy нет"
  fi
done

DATABASES="$(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["postgres"]["databases"]))' "$MANIFEST")"
VECTORS="$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["postgres"]["vector_extensions"]))' "$MANIFEST")"

log_section "Drop and recreate Postgres databases"
while IFS= read -r db; do
  [ -n "$db" ] || continue
  log_do "recreate $db"
  $K exec -n "$NS" postgres-0 -- psql -U platform_user -d postgres -v ON_ERROR_STOP=1 -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db}' AND pid <> pg_backend_pid();"
  $K exec -n "$NS" postgres-0 -- psql -U platform_user -d postgres -v ON_ERROR_STOP=1 -c \
    "DROP DATABASE IF EXISTS ${db} WITH (FORCE);"
  $K exec -n "$NS" postgres-0 -- psql -U platform_user -d postgres -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE ${db} OWNER platform_user;"
  $K exec -n "$NS" postgres-0 -- psql -U platform_user -d postgres -v ON_ERROR_STOP=1 -c \
    "GRANT ALL PRIVILEGES ON DATABASE ${db} TO platform_user;"
done <<< "$DATABASES"

for db in $VECTORS; do
  log_do "CREATE EXTENSION vector ON $db"
  $K exec -n "$NS" postgres-0 -- psql -U platform_user -d "$db" -v ON_ERROR_STOP=1 -c \
    "CREATE EXTENSION IF NOT EXISTS vector;"
done

log_section "Flush Redis"
for pod in redis-0 redis-realtime-0; do
  if $K get pod "$pod" -n "$NS" >/dev/null 2>&1; then
    log_do "FLUSHALL $pod"
    $K exec -n "$NS" "$pod" -- redis-cli FLUSHALL
  else
    log_skip "pod $pod нет"
  fi
done

log_section "Drop pinned OpenFGA store"
if $K get secret openfga-ids -n "$NS" >/dev/null 2>&1; then
  log_do "delete secret openfga-ids"
  $K delete secret openfga-ids -n "$NS"
else
  log_skip "secret openfga-ids нет"
fi

log_section "Databases"
$K exec -n "$NS" postgres-0 -- psql -U platform_user -d postgres -c '\l'

log_ok "Сервисные БД пустые. Дальше — деплой: init db-migrate накатит цепочку миграций, bootstrap создаст store OpenFGA."
print_summary
