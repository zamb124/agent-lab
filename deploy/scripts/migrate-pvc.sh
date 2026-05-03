#!/usr/bin/env bash
# Переносит StatefulSet с данными на другую ноду кластера.
# Делает backup, переопределяет nodeName через Helm, перебиндит PVC, восстанавливает данные.
#
# Использование:
#   bash deploy/scripts/migrate-pvc.sh <component> <new_node>
#
# component: postgres | redis | loki | tempo | grafana
# new_node:  имя ноды (kubernetes.io/hostname), например master или gpu-worker
#
# ВНИМАНИЕ: скрипт останавливает компонент на время переноса. Другие сервисы,
# зависящие от postgres/redis, будут недоступны на время миграции (~5–15 мин).
#
# Требования:
#   - kubectl (или microk8s kubectl)
#   - helm (или microk8s helm3)
#   - pg_dumpall / pg_restore (для postgres)
#   - Доступ к кластеру (kubeconfig)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

COMPONENT="${1:-}"
NEW_NODE="${2:-}"

if [ -z "$COMPONENT" ] || [ -z "$NEW_NODE" ]; then
  echo "Использование: $0 <component> <new_node>"
  echo "  component: postgres | redis | loki | tempo | grafana"
  echo "  new_node:  master | gpu-worker | <любое kubernetes.io/hostname>"
  exit 1
fi

VALID_COMPONENTS="postgres redis loki tempo grafana"
if ! echo "$VALID_COMPONENTS" | grep -qw "$COMPONENT"; then
  log_error "Неизвестный компонент: $COMPONENT. Допустимые: $VALID_COMPONENTS"
  exit 1
fi

K="$KUBECTL"
H="$HELM"
PLATFORM_NS="${PLATFORM_NS:-platform}"
HELM_CHART="${HELM_CHART:-./deploy/helm/agent-lab}"
HELM_RELEASE="${HELM_RELEASE:-agent-lab}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/migrate-pvc-backup}"

mkdir -p "$BACKUP_DIR"
BACKUP_STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${COMPONENT}-${BACKUP_STAMP}"

log_section "Перенос $COMPONENT → $NEW_NODE"

# Определяем Helm path для nodeName
case "$COMPONENT" in
  postgres) HELM_NODE_PATH="postgres.nodeName" ;;
  redis)    HELM_NODE_PATH="redis.nodeName" ;;
  loki)     HELM_NODE_PATH="observability.loki.nodeName" ;;
  tempo)    HELM_NODE_PATH="observability.tempo.nodeName" ;;
  grafana)  HELM_NODE_PATH="observability.grafana.nodeName" ;;
esac

# Текущая нода компонента
CURRENT_NODE=$($K get pod -n "$PLATFORM_NS" -l "app=${COMPONENT}" \
  -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null || echo "unknown")

log_info "Текущая нода: $CURRENT_NODE → целевая: $NEW_NODE"

if [ "$CURRENT_NODE" = "$NEW_NODE" ]; then
  log_skip "$COMPONENT уже на ноде $NEW_NODE — миграция не нужна"
  exit 0
fi

# Проверка backup за последние 5 минут
RECENT_BACKUP=$(find "$BACKUP_DIR" -name "${COMPONENT}-*.done" -newer \
  <(date -r "$(find "$BACKUP_DIR" -name "${COMPONENT}-*.done" -newer \
  /tmp 2>/dev/null | head -1 || echo /tmp)" 2>/dev/null) 2>/dev/null | head -1 || true)
if [ -n "$RECENT_BACKUP" ] && [ "$(find "$BACKUP_DIR" -name "${COMPONENT}-*.done" \
  -mmin -5 2>/dev/null | head -1)" ]; then
  log_skip "Backup сделан менее 5 минут назад ($RECENT_BACKUP) — шаг 1 пропущен"
else
  # Шаг 1: Backup
  log_section "1) Backup $COMPONENT"
  mkdir -p "$BACKUP_PATH"

  case "$COMPONENT" in
    postgres)
      log_do "pg_dumpall → $BACKUP_PATH/dump.sql"
      $K exec -n "$PLATFORM_NS" postgres-0 -- \
        pg_dumpall -U platform_user > "$BACKUP_PATH/dump.sql"
      ;;
    redis)
      log_do "BGSAVE + copy dump.rdb → $BACKUP_PATH/"
      $K exec -n "$PLATFORM_NS" redis-0 -- redis-cli BGSAVE
      sleep 3
      $K cp "${PLATFORM_NS}/redis-0:/data/dump.rdb" "$BACKUP_PATH/dump.rdb"
      ;;
    loki|tempo|grafana)
      MOUNT_PATH=""
      case "$COMPONENT" in
        loki)   MOUNT_PATH="/loki" ;;
        tempo)  MOUNT_PATH="/var/tempo" ;;
        grafana) MOUNT_PATH="/var/lib/grafana" ;;
      esac
      log_do "tar $COMPONENT data → $BACKUP_PATH/data.tar.gz"
      $K exec -n "$PLATFORM_NS" "${COMPONENT}-0" -- \
        tar czf - "$MOUNT_PATH" 2>/dev/null > "$BACKUP_PATH/data.tar.gz" || \
      $K exec -n "$PLATFORM_NS" "$(get_grafana_pod)" -- \
        tar czf - "$MOUNT_PATH" 2>/dev/null > "$BACKUP_PATH/data.tar.gz"
      ;;
  esac

  touch "${BACKUP_PATH}.done"
  log_ok "Backup сохранён: $BACKUP_PATH"
fi

# Шаг 2: Helm upgrade с новым nodeName
log_section "2) Helm upgrade: $HELM_NODE_PATH=$NEW_NODE"
log_do "helm upgrade --install с --set $HELM_NODE_PATH=$NEW_NODE"
$H upgrade --install "$HELM_RELEASE" "$HELM_CHART" \
  --namespace "$PLATFORM_NS" \
  --reuse-values \
  --set "${HELM_NODE_PATH}=${NEW_NODE}" \
  --wait=false \
  --timeout 5m 2>&1 | head -5

# Шаг 3: Ждём Pending (PVC не Bound на новой ноде)
log_section "3) Ожидание Pending пода (до 120s)"
DEADLINE=$(($(date +%s) + 120))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  PHASE=$($K get pod -n "$PLATFORM_NS" -l "app=${COMPONENT}" \
    -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
  if [ "$PHASE" = "Pending" ] || [ "$PHASE" = "" ]; then
    log_info "Pod $COMPONENT в состоянии Pending (PVC ждёт ноду)"
    break
  fi
  sleep 5
done

# Шаг 4: Удаляем старый PVC + StatefulSet (чтобы provisioner создал PVC на новой ноде)
log_section "4) Удаление старого PVC и StatefulSet $COMPONENT"
log_do "kubectl delete statefulset $COMPONENT"
$K delete statefulset "$COMPONENT" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true

case "$COMPONENT" in
  postgres)
    log_do "kubectl delete pvc data-postgres-0"
    $K delete pvc "data-postgres-0" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true
    ;;
  redis)
    log_do "kubectl delete pvc data-redis-0"
    $K delete pvc "data-redis-0" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true
    ;;
  loki)
    log_do "kubectl delete pvc data-loki-0"
    $K delete pvc "data-loki-0" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true
    ;;
  tempo)
    log_do "kubectl delete pvc data-tempo-0"
    $K delete pvc "data-tempo-0" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true
    ;;
  grafana)
    log_do "kubectl delete pvc grafana-data"
    $K delete pvc "grafana-data" -n "$PLATFORM_NS" --wait=false 2>/dev/null || true
    ;;
esac

# Шаг 5: Повторный helm upgrade — provisioner создаст PVC на новой ноде
log_section "5) Helm upgrade (повторный — создаст PVC на $NEW_NODE)"
$H upgrade --install "$HELM_RELEASE" "$HELM_CHART" \
  --namespace "$PLATFORM_NS" \
  --reuse-values \
  --set "${HELM_NODE_PATH}=${NEW_NODE}" \
  --wait --timeout 15m

log_ok "Pod $COMPONENT поднялся на $NEW_NODE (с пустыми данными)"

# Шаг 6: Restore
log_section "6) Restore данных"

case "$COMPONENT" in
  postgres)
    log_info "Ожидаем готовности postgres-0..."
    $K wait pod/postgres-0 -n "$PLATFORM_NS" \
      --for=condition=ready --timeout=120s
    log_do "psql restore из $BACKUP_PATH/dump.sql"
    $K exec -i -n "$PLATFORM_NS" postgres-0 -- \
      psql -U platform_user postgres < "$BACKUP_PATH/dump.sql"
    ;;
  redis)
    log_info "Ожидаем готовности redis-0..."
    $K wait pod/redis-0 -n "$PLATFORM_NS" \
      --for=condition=ready --timeout=60s
    log_do "Останавливаем redis, копируем dump.rdb, перезапускаем"
    $K cp "$BACKUP_PATH/dump.rdb" "${PLATFORM_NS}/redis-0:/data/dump.rdb"
    $K exec -n "$PLATFORM_NS" redis-0 -- redis-cli DEBUG RELOAD
    ;;
  loki|tempo|grafana)
    MOUNT_PATH=""
    case "$COMPONENT" in
      loki)   MOUNT_PATH="/loki" ;;
      tempo)  MOUNT_PATH="/var/tempo" ;;
      grafana) MOUNT_PATH="/var/lib/grafana" ;;
    esac
    log_do "Restore tar → $MOUNT_PATH в ${COMPONENT}-0"
    $K exec -i -n "$PLATFORM_NS" "${COMPONENT}-0" -- \
      tar xzf - -C / < "$BACKUP_PATH/data.tar.gz"
    $K delete pod -n "$PLATFORM_NS" "${COMPONENT}-0"
    ;;
esac

log_ok "Миграция $COMPONENT завершена: $CURRENT_NODE → $NEW_NODE"
log_info "Запустите cluster-health.sh для финальной проверки."
