#!/usr/bin/env bash
# Загружает OPENFGA_STORE_ID / OPENFGA_AUTHORIZATION_MODEL_ID для helm --set.
# Приоритет: уже заданные env → Kubernetes Secret openfga-ids.
# Печатает export-строки на stdout (source <(bash ...)).
#
# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

NS="${PLATFORM_NS:-${HELM_NAMESPACE:-platform}}"
IDS_SECRET="${OPENFGA_IDS_SECRET:-openfga-ids}"
K="${KUBECTL}"

STORE_ID="${OPENFGA_STORE_ID:-}"
MODEL_ID="${OPENFGA_AUTHORIZATION_MODEL_ID:-}"

if [ -z "${STORE_ID}" ] || [ -z "${MODEL_ID}" ]; then
  if $K get secret "${IDS_SECRET}" -n "${NS}" >/dev/null 2>&1; then
    if [ -z "${STORE_ID}" ]; then
      STORE_ID="$($K get secret "${IDS_SECRET}" -n "${NS}" -o jsonpath='{.data.store-id}' | base64 -d)"
    fi
    if [ -z "${MODEL_ID}" ]; then
      MODEL_ID="$($K get secret "${IDS_SECRET}" -n "${NS}" -o jsonpath='{.data.authorization-model-id}' | base64 -d)"
    fi
  fi
fi

if [ -n "${STORE_ID}" ]; then
  printf 'export OPENFGA_STORE_ID=%q\n' "${STORE_ID}"
fi
if [ -n "${MODEL_ID}" ]; then
  printf 'export OPENFGA_AUTHORIZATION_MODEL_ID=%q\n' "${MODEL_ID}"
fi
