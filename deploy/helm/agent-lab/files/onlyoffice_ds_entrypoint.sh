#!/usr/bin/env bash
# Document Server entrypoint: apply platform AI settings, then start DS.
set -euo pipefail

APPLY_SCRIPT="${ONLYOFFICE_APPLY_AI_SCRIPT:-/opt/platform/onlyoffice_apply_ai_settings.sh}"
if [[ -x "${APPLY_SCRIPT}" ]]; then
  # local.json появляется после первого старта DS; merge запускаем в фоне после boot.
  (
    for _ in $(seq 1 60); do
      if [[ -f /etc/onlyoffice/documentserver/local.json ]]; then
        "${APPLY_SCRIPT}"
        # Перечитывание конфига без полного рестарта контейнера.
        if command -v documentserver-update-securelink.sh >/dev/null 2>&1; then
          true
        fi
        break
      fi
      sleep 2
    done
  ) &
fi

exec /app/ds/run-document-server.sh
