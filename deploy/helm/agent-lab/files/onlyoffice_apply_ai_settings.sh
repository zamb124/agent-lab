#!/usr/bin/env bash
# Merge platform aiSettings (+ AI plugin autostart) into Document Server local.json,
# then install AI plugin if pluginsmanager is available.
set -euo pipefail

FRAGMENT_PATH="${ONLYOFFICE_AI_FRAGMENT_PATH:-/opt/platform/onlyoffice-ai-local-fragment.json}"
LOCAL_JSON="${ONLYOFFICE_LOCAL_JSON:-/etc/onlyoffice/documentserver/local.json}"
LLM_BASE="${PLATFORM_LLM_BASE_URL:?PLATFORM_LLM_BASE_URL is required}"
LLM_PROXY="${PLATFORM_LLM_PROXY_URL:?PLATFORM_LLM_PROXY_URL is required}"
PROVIDER_NAME="${PLATFORM_LLM_PROVIDER_NAME:-Platform LLMs}"

if [[ ! -f "${FRAGMENT_PATH}" ]]; then
  echo "onlyoffice AI fragment missing: ${FRAGMENT_PATH}" >&2
  exit 1
fi

TMP_FRAGMENT="$(mktemp)"
TMP_MERGED="$(mktemp)"
trap 'rm -f "${TMP_FRAGMENT}" "${TMP_MERGED}"' EXIT

sed \
  -e "s|__PLATFORM_LLM_BASE__|${LLM_BASE}|g" \
  -e "s|__PLATFORM_LLM_PROXY__|${LLM_PROXY}|g" \
  -e "s|__PROVIDER_DISPLAY_NAME__|${PROVIDER_NAME}|g" \
  "${FRAGMENT_PATH}" > "${TMP_FRAGMENT}"

if [[ ! -f "${LOCAL_JSON}" ]]; then
  echo '{}' > "${LOCAL_JSON}"
fi

if command -v jq >/dev/null 2>&1; then
  jq -s '.[0] * .[1]' "${LOCAL_JSON}" "${TMP_FRAGMENT}" > "${TMP_MERGED}"
  cp "${TMP_MERGED}" "${LOCAL_JSON}"
else
  python3 -c '
import json
import sys

local_path, fragment_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

def deep_merge(base, overlay):
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

with open(local_path, encoding="utf-8") as local_file:
    local_payload = json.load(local_file)
with open(fragment_path, encoding="utf-8") as fragment_file:
    fragment_payload = json.load(fragment_file)
if not isinstance(local_payload, dict) or not isinstance(fragment_payload, dict):
    raise SystemExit("local.json and fragment must be JSON objects")
merged = deep_merge(local_payload, fragment_payload)
with open(out_path, "w", encoding="utf-8") as out_file:
    json.dump(merged, out_file, ensure_ascii=False, indent=2)
    out_file.write("\n")
' "${LOCAL_JSON}" "${TMP_FRAGMENT}" "${TMP_MERGED}"
  cp "${TMP_MERGED}" "${LOCAL_JSON}"
fi

PLUGIN_URL="${ONLYOFFICE_AI_PLUGIN_URL:-https://onlyoffice.github.io/sdkjs-plugins/content/ai/config.json}"
if [[ -x /usr/bin/documentserver-pluginsmanager.sh ]]; then
  /usr/bin/documentserver-pluginsmanager.sh --install="${PLUGIN_URL}" || true
elif [[ -x /usr/bin/documentserver-pluginsmanager ]]; then
  /usr/bin/documentserver-pluginsmanager --install="${PLUGIN_URL}" || true
fi

echo "onlyoffice AI settings applied: llm_base=${LLM_BASE}"
