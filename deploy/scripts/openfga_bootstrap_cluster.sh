#!/usr/bin/env bash
# Идемпотентный bootstrap OpenFGA в кластере (без uv/Python на runner).
#
# Источник pin ids (приоритет):
#   1) OPENFGA_STORE_ID / OPENFGA_AUTHORIZATION_MODEL_ID в env
#   2) Kubernetes Secret openfga-ids (store-id, authorization-model-id)
#   3) env apps (frontend OPENFGA__STORE_ID)
#   4) создать новый store
#
# Всегда пишет/обновляет Secret openfga-ids.
# APPLY=1 (default) — helm upgrade --reuse-values --set pin.
#
# Переменные:
#   PLATFORM_NS / HELM_NAMESPACE  (default: platform)
#   HELM_RELEASE                  (default: agent-lab)
#   HELM_CHART                    (default: ./deploy/helm/agent-lab)
#   APPLY=1
#   OPENFGA_LOCAL_PORT            (default: 18080)
#
# Запуск: bash deploy/scripts/openfga_bootstrap_cluster.sh
# Makefile: make k8s-openfga-bootstrap

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

NS="${PLATFORM_NS:-${HELM_NAMESPACE:-platform}}"
REL="${HELM_RELEASE:-agent-lab}"
CHART="${HELM_CHART:-./deploy/helm/agent-lab}"
APPLY="${APPLY:-1}"
LOCAL_PORT="${OPENFGA_LOCAL_PORT:-18080}"
IDS_SECRET="${OPENFGA_IDS_SECRET:-openfga-ids}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODEL_JSON="${OPENFGA_MODEL_JSON:-${REPO_ROOT}/core/authz/model.json}"
K="${KUBECTL}"

require_command curl
require_command jq

log_section "OpenFGA bootstrap (ns=${NS})"

if [ ! -f "${MODEL_JSON}" ]; then
  log_error "нет model.json: ${MODEL_JSON}"
  print_summary
  exit 1
fi

idempotent \
  "БД openfga существует" \
  "${K} exec -n ${NS} postgres-0 -- psql -U platform_user -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='openfga'\" | grep -q 1" \
  "${K} exec -n ${NS} postgres-0 -- psql -U platform_user -d postgres -c 'CREATE DATABASE openfga;' && ${K} exec -n ${NS} postgres-0 -- psql -U platform_user -d postgres -c 'GRANT ALL PRIVILEGES ON DATABASE openfga TO platform_user;'"

wait_for \
  "deployment/openfga Available" \
  "${K} get deploy openfga -n ${NS} -o jsonpath='{.status.availableReplicas}' | grep -qE '^[1-9]'" \
  180

TOKEN="$($K get secret platform-secrets -n "${NS}" -o jsonpath='{.data.openfga-api-token}' 2>/dev/null | base64 -d || true)"
if [ -z "${TOKEN}" ]; then
  log_error "platform-secrets.openfga-api-token пуст. Задайте GitHub Secret OPENFGA_API_TOKEN и сделайте helm upgrade / make k8s-secrets-sync."
  print_summary
  exit 1
fi

EXISTING_STORE="${OPENFGA_STORE_ID:-}"
if [ -z "${EXISTING_STORE}" ] && $K get secret "${IDS_SECRET}" -n "${NS}" >/dev/null 2>&1; then
  EXISTING_STORE="$($K get secret "${IDS_SECRET}" -n "${NS}" -o jsonpath='{.data.store-id}' 2>/dev/null | base64 -d || true)"
  if [ -n "${EXISTING_STORE}" ]; then
    log_info "Reuse store_id from Secret ${IDS_SECRET}"
  fi
fi
if [ -z "${EXISTING_STORE}" ]; then
  EXISTING_STORE="$($K get deploy frontend -n "${NS}" -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="OPENFGA__STORE_ID")]}{.value}{end}' 2>/dev/null || true)"
fi

PF_PID=""
cleanup() {
  if [ -n "${PF_PID}" ] && kill -0 "${PF_PID}" 2>/dev/null; then
    kill "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

log_do "kubectl port-forward svc/openfga ${LOCAL_PORT}:8080"
$K port-forward -n "${NS}" svc/openfga "${LOCAL_PORT}:8080" >/tmp/openfga-pf.log 2>&1 &
PF_PID=$!
wait_for \
  "OpenFGA healthz via port-forward" \
  "curl -sf http://127.0.0.1:${LOCAL_PORT}/healthz >/dev/null" \
  60

API="http://127.0.0.1:${LOCAL_PORT}"
AUTH_HDR=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")

STORE_ID="${EXISTING_STORE}"
if [ -z "${STORE_ID}" ]; then
  log_do "POST ${API}/stores"
  CREATE_OUT="$(curl -sf "${AUTH_HDR[@]}" -d '{"name":"platform"}' "${API}/stores")"
  STORE_ID="$(printf '%s' "${CREATE_OUT}" | jq -r '.id')"
  if [ -z "${STORE_ID}" ] || [ "${STORE_ID}" = "null" ]; then
    log_error "create_store без id: ${CREATE_OUT}"
    print_summary
    exit 1
  fi
  log_ok "store created: ${STORE_ID}"
else
  log_info "reuse store_id=${STORE_ID}"
fi

# OpenFGA выдаёт новый authorization_model_id на каждый POST даже при
# идентичном теле (плюс нормализует metadata) — контентное сравнение
# ненадёжно. Pin по sha256 model.json в секрете: модель не менялась →
# переиспользуем сохранённый ID и не катим поды новым env.
MODEL_BODY="$(jq '{schema_version, type_definitions}' "${MODEL_JSON}")"
MODEL_SHA="$(shasum -a 256 "${MODEL_JSON}" | cut -d' ' -f1)"
LIVE_MODEL_SHA=""
LIVE_MODEL_ID=""
if $K get secret "${IDS_SECRET}" -n "${NS}" >/dev/null 2>&1; then
  LIVE_MODEL_SHA="$($K get secret "${IDS_SECRET}" -n "${NS}" -o jsonpath='{.data.model-sha256}' 2>/dev/null | base64 -d || true)"
  LIVE_MODEL_ID="$($K get secret "${IDS_SECRET}" -n "${NS}" -o jsonpath='{.data.authorization-model-id}' 2>/dev/null | base64 -d || true)"
fi
if [ -n "${LIVE_MODEL_ID}" ] && [ "${LIVE_MODEL_SHA}" = "${MODEL_SHA}" ]; then
  MODEL_ID="${LIVE_MODEL_ID}"
  log_info "reuse authorization_model_id=${MODEL_ID} (model.json sha совпал)"
else
  log_do "POST authorization-models (model.json изменён)"
  WRITE_OUT="$(
    curl -sf "${AUTH_HDR[@]}" \
      -d "${MODEL_BODY}" \
      "${API}/stores/${STORE_ID}/authorization-models"
  )"
  MODEL_ID="$(printf '%s' "${WRITE_OUT}" | jq -r '.authorization_model_id')"
  if [ -z "${MODEL_ID}" ] || [ "${MODEL_ID}" = "null" ]; then
    log_error "write model без authorization_model_id: ${WRITE_OUT}"
    print_summary
    exit 1
  fi
fi

log_ok "store_id=${STORE_ID}"
log_ok "authorization_model_id=${MODEL_ID}"

log_do "upsert Secret ${IDS_SECRET}"
$K create secret generic "${IDS_SECRET}" \
  -n "${NS}" \
  --from-literal=store-id="${STORE_ID}" \
  --from-literal=authorization-model-id="${MODEL_ID}" \
  --from-literal=model-sha256="${MODEL_SHA}" \
  --dry-run=client -o yaml | $K apply -f -
log_ok "Secret ${IDS_SECRET} обновлён (канон pin для следующих деплоев)"

if [ "${APPLY}" = "1" ]; then
  require_command helm
  LIVE_STORE="$($K get deploy frontend -n "${NS}" -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="OPENFGA__STORE_ID")]}{.value}{end}' 2>/dev/null || true)"
  LIVE_MODEL="$($K get deploy frontend -n "${NS}" -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="OPENFGA__AUTHORIZATION_MODEL_ID")]}{.value}{end}' 2>/dev/null || true)"
  if [ -n "${LIVE_STORE}" ] && [ "${LIVE_STORE}" = "${STORE_ID}" ] && [ "${LIVE_MODEL}" = "${MODEL_ID}" ]; then
    log_skip "OpenFGA pin уже на frontend (store/model совпали) — второй helm --wait не нужен"
  else
    log_do "helm upgrade --reuse-values --set openfga.storeId / authorizationModelId"
    helm upgrade "${REL}" "${CHART}" \
      --namespace "${NS}" \
      --reuse-values \
      --set "openfga.storeId=${STORE_ID}" \
      --set "openfga.authorizationModelId=${MODEL_ID}" \
      --wait --timeout 15m
    log_ok "Helm pinned; apps получили OPENFGA__STORE_ID / OPENFGA__AUTHORIZATION_MODEL_ID"
  fi
else
  log_info "APPLY=0 — helm не трогали. Pin: APPLY=1 make k8s-openfga-bootstrap"
fi

print_summary
