#!/usr/bin/env bash
# Идемпотентный OpenFGA backfill в кластере: SQL/KV roster → tuples.
# Тот же набор модулей, что `make openfga-backfill`, но внутри пода приложения
# (ENV OPENFGA__* / DATABASE__* уже в контейнере).
#
# Переменные:
#   PLATFORM_NS                 (default: platform)
#   OPENFGA_BACKFILL_APP        (default: flows) — Deployment, из которого exec
#   SYNC_LOCAL_FLOWS_BACKFILL=1 — скопировать локальный apps/flows/authz/backfill.py
#                                 в под (нужно, пока образ без фикса таблиц flows/tools)
#
# Запуск: bash deploy/scripts/openfga_backfill_cluster.sh
# Makefile: make k8s-openfga-backfill

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

NS="${PLATFORM_NS:-${HELM_NAMESPACE:-platform}}"
APP="${OPENFGA_BACKFILL_APP:-flows}"
K="${KUBECTL}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SYNC_LOCAL="${SYNC_LOCAL_FLOWS_BACKFILL:-0}"

require_command kubectl

log_section "OpenFGA backfill (ns=${NS} app=${APP})"

wait_for \
  "deployment/openfga Available" \
  "${K} get deploy openfga -n ${NS} -o jsonpath='{.status.availableReplicas}' | grep -qE '^[1-9]'" \
  180

wait_for \
  "deployment/${APP} Available" \
  "${K} get deploy ${APP} -n ${NS} -o jsonpath='{.status.availableReplicas}' | grep -qE '^[1-9]'" \
  180

POD="$($K get pod -n "${NS}" -l "app=${APP}" -o jsonpath='{.items[0].metadata.name}')"
if [ -z "${POD}" ]; then
  log_error "нет Running пода app=${APP} в ${NS}"
  print_summary
  exit 1
fi
log_info "pod=${POD}"

ENABLED="$($K exec -n "${NS}" "${POD}" -- printenv OPENFGA__ENABLED)"
STORE_ID="$($K exec -n "${NS}" "${POD}" -- printenv OPENFGA__STORE_ID)"
MODEL_ID="$($K exec -n "${NS}" "${POD}" -- printenv OPENFGA__AUTHORIZATION_MODEL_ID)"
if [ "${ENABLED}" != "true" ] || [ -z "${STORE_ID}" ] || [ -z "${MODEL_ID}" ]; then
  log_error "OpenFGA в поде выключен или без pin (OPENFGA__ENABLED=${ENABLED} store=${STORE_ID})"
  print_summary
  exit 1
fi
log_ok "OPENFGA__ENABLED=true store=${STORE_ID}"

if [ "${SYNC_LOCAL}" = "1" ]; then
  LOCAL_BACKFILL="${REPO_ROOT}/apps/flows/authz/backfill.py"
  if [ ! -f "${LOCAL_BACKFILL}" ]; then
    log_error "нет ${LOCAL_BACKFILL}"
    print_summary
    exit 1
  fi
  log_do "kubectl cp flows authz backfill.py → ${POD}"
  $K cp "${LOCAL_BACKFILL}" "${NS}/${POD}:/app/apps/flows/authz/backfill.py"
fi

MODULES=(
  core.authz.backfill_company
  core.authz.backfill_groups
  core.namespace.authz
  apps.flows.authz
  apps.crm.authz
  apps.office.authz
  apps.wiki.authz
  apps.sync.authz
  apps.worktracker.authz
  core.mail.authz
  core.datasources.authz.backfill
)

for mod in "${MODULES[@]}"; do
  log_do "python -m ${mod}"
  $K exec -n "${NS}" "${POD}" -- env PYTHONUNBUFFERED=1 python -m "${mod}"
  log_ok "${mod}"
done

check_step \
  "flow:system/lara имеет scoped tuples" \
  "${K} exec -n ${NS} postgres-0 -- psql -U platform_user -d openfga -tAc \"SELECT count(*) FROM tuple WHERE object_type='flow' AND object_id='system/lara'\" | grep -qE '^[1-9]'"

check_step \
  "scoped group имеет реального user:*" \
  "${K} exec -n ${NS} postgres-0 -- psql -U platform_user -d openfga -tAc \"SELECT count(*) FROM tuple WHERE object_type='group' AND object_id LIKE '%/%' AND relation='member' AND _user LIKE 'user:user_%'\" | grep -qE '^[1-9]'"

print_summary
