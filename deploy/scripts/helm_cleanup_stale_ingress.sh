#!/usr/bin/env bash
# Удаляет монолитный Ingress platform после split на platform-services / platform-frontend.
# Helm не удаляет ресурсы, убранные из чарта; без cleanup /worktracker уходит на frontend (WS 403).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

PLATFORM_NS="${PLATFORM_NS:-platform}"
K="${KUBECTL:-kubectl}"

if $K get ingress platform-services -n "$PLATFORM_NS" >/dev/null 2>&1 \
  && $K get ingress platform -n "$PLATFORM_NS" >/dev/null 2>&1; then
  log_do "kubectl delete ingress platform -n $PLATFORM_NS (stale monolithic ingress)"
  $K delete ingress platform -n "$PLATFORM_NS" --wait=true
  log_ok "Ingress platform удалён"
else
  log_info "Ingress platform не найден или split ingress ещё не развёрнут — cleanup пропущен"
fi
