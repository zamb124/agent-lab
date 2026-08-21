#!/usr/bin/env bash
# Однострочный base64 kubeconfig для GitHub Secret KUBECONFIG_B64.
# server всегда https://MASTER_HOST_IP:16443 — не 127.0.0.1 из `microk8s config`.
# YAML в stdout не печатает (только base64). Логи — в stderr.
#
# На master:  bash deploy/scripts/kubeconfig-for-github-actions.sh
# С ноутбука: тот же вызов (SSH на MASTER_HOST_IP).
# Запись в GitHub: gh secret set KUBECONFIG_B64 --body "$(bash deploy/scripts/kubeconfig-for-github-actions.sh)"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

PUBLIC_IP="${MASTER_HOST_IP:-31.192.111.33}"
API_PORT="${MICROK8S_API_PORT:-16443}"

raw_config=""
if command -v microk8s >/dev/null 2>&1; then
  raw_config="$(microk8s config)"
else
  require_command ssh || exit 1
  raw_config="$(ssh -o BatchMode=yes -o ConnectTimeout=15 "${SSH_USER}@${PUBLIC_IP}" 'export PATH=/snap/bin:$PATH; microk8s config')"
fi

if [ -z "$raw_config" ]; then
  log_error "пустой microk8s config"
  exit 1
fi

rewritten="$(PUBLIC_IP="$PUBLIC_IP" API_PORT="$API_PORT" python3 -c '
import os
import re
import sys

public_ip = os.environ["PUBLIC_IP"]
api_port = os.environ["API_PORT"]
text = sys.stdin.read()
text = re.sub(
    r"https://(?:127\.0\.0\.1|localhost)(?::\d+)?",
    f"https://{public_ip}:{api_port}",
    text,
)
if f"https://{public_ip}:{api_port}" not in text:
    raise SystemExit("kubeconfig: нет server https://%s:%s после подстановки" % (public_ip, api_port))
if "127.0.0.1" in text or "localhost" in text:
    raise SystemExit("kubeconfig: остался 127.0.0.1/localhost")
sys.stdout.write(text)
' <<<"$raw_config")"

printf '%s' "$rewritten" | base64 | tr -d '\n'
printf '\n' >&2
log_ok "KUBECONFIG_B64: server https://${PUBLIC_IP}:${API_PORT} (строка в stdout)" >&2
