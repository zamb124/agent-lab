#!/usr/bin/env bash
# После применения миграций БД перезапускает Deployments приложений и TaskIQ-воркеров,
# чтобы процессы поднялись на актуальной схеме (короче жить без полного CrashLoop до случайного рестарта).
#
# Идемпотентность: повторный запуск безопасен — снова выполняет rollout restart и ждёт завершения rollout.
#
# ENV:
#   PLATFORM_NS / K8S_NAMESPACE — namespace (по умолчанию platform)
#   SKIP_MIGRATION_JOB_WAIT=1 — не проверять и не ждать Job migrations
#   MIGRATION_JOB_WAIT_TIMEOUT — ожидание Complete для Job migrations (по умолчанию 600s), формат как у kubectl wait
#   ROLLOUT_STATUS_TIMEOUT — kubectl rollout status на каждый Deployment (по умолчанию 600s)
#
# Запуск:
#   bash deploy/scripts/k8s_post_migrate_rollout.sh
#   make k8s-post-migrate-rollout

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

PLATFORM_NS="${K8S_NAMESPACE:-${PLATFORM_NS:-platform}}"
SKIP_MIGRATION_JOB_WAIT="${SKIP_MIGRATION_JOB_WAIT:-0}"
MIGRATION_JOB_WAIT_TIMEOUT="${MIGRATION_JOB_WAIT_TIMEOUT:-600s}"
ROLLOUT_STATUS_TIMEOUT="${ROLLOUT_STATUS_TIMEOUT:-600s}"

# Совпадает с приложениями и воркерами из Helm values (без livekit/onlyoffice/grafana/litserve —
# они не зависят от scripts.db_migrate). Если компонент выключен в values, строка будет пропущена.
POST_MIGRATE_DEPLOYMENTS=(
  flows frontend crm rag sync office scheduler-api voice browser
  flows-worker scheduler rag-worker sync-worker crm-worker idle-worker
)

require_command kubectl 2>/dev/null || require_command microk8s || exit 1
K="$KUBECTL"

wait_for_migrations_job() {
  if [ "$SKIP_MIGRATION_JOB_WAIT" = "1" ]; then
    log_skip "Ожидание Job migrations (SKIP_MIGRATION_JOB_WAIT=1)"
    return 0
  fi

  if ! "$K" get job migrations -n "$PLATFORM_NS" >/dev/null 2>&1; then
    log_info "Job migrations не найден в ${PLATFORM_NS} (часто удалён Helm hook после успеха). Продолжаю rollout."
    return 0
  fi

  log_info "Ожидание успешного завершения job/migrations (timeout ${MIGRATION_JOB_WAIT_TIMEOUT})"
  if "$K" wait --for=condition=complete "job/migrations" -n "$PLATFORM_NS" --timeout="$MIGRATION_JOB_WAIT_TIMEOUT"; then
    log_ok "job/migrations завершился успешно"
    return 0
  fi

  log_error "job/migrations не достиг состояния Complete за отведённое время или завершился с ошибкой"
  "$K" describe job migrations -n "$PLATFORM_NS" | tail -40 || true
  log_info "Логи pod миграций (если есть): $K logs -n $PLATFORM_NS job/migrations --tail=200"
  return 1
}

restart_one() {
  local dep="$1"
  if ! "$K" get "deployment/${dep}" -n "$PLATFORM_NS" >/dev/null 2>&1; then
    log_skip "deployment/${dep} отсутствует в ${PLATFORM_NS}"
    return 0
  fi
  log_do "kubectl rollout restart deployment/${dep} -n ${PLATFORM_NS}"
  "$K" rollout restart "deployment/${dep}" -n "$PLATFORM_NS"
  log_ok "restart отправлен: ${dep}"
}

wait_rollout_one() {
  local dep="$1"
  if ! "$K" get "deployment/${dep}" -n "$PLATFORM_NS" >/dev/null 2>&1; then
    return 0
  fi
  log_info "kubectl rollout status deployment/${dep} (timeout ${ROLLOUT_STATUS_TIMEOUT})"
  if "$K" rollout status "deployment/${dep}" -n "$PLATFORM_NS" --timeout="$ROLLOUT_STATUS_TIMEOUT"; then
    log_ok "rollout готов: ${dep}"
  else
    log_error "rollout не завершился за timeout: ${dep}"
    return 1
  fi
}

main() {
  log_section "Post-migrate rollout (namespace=${PLATFORM_NS})"

  wait_for_migrations_job

  local dep
  for dep in "${POST_MIGRATE_DEPLOYMENTS[@]}"; do
    restart_one "$dep"
  done

  local failed=0
  for dep in "${POST_MIGRATE_DEPLOYMENTS[@]}"; do
    if ! wait_rollout_one "$dep"; then
      failed=$((failed + 1))
    fi
  done

  if [ "$failed" -gt 0 ]; then
    log_error "Не все rollout завершились успешно (failures=${failed})"
    exit 1
  fi

  log_section "Готово"
  log_ok "Все присутствующие Deployments из списка перезапущены и в статусе успешного rollout"
}

main "$@"
