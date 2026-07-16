#!/usr/bin/env bash
# LEGACY: host launchd CBM daemon.
# Канон: Docker Compose — bash scripts/zed_search/compose.sh up
echo "[zed-search] cbm_daemon.sh устарел. Перенаправляю на Compose..."
case "${1:-install}" in
  uninstall|stop)
    exec bash "$(cd "$(dirname "$0")" && pwd)/compose.sh" stop-legacy
    ;;
  status)
    exec bash "$(cd "$(dirname "$0")" && pwd)/compose.sh" status
    ;;
  wire-clients|wire)
    exec bash "$(cd "$(dirname "$0")" && pwd)/compose.sh" wire
    ;;
  *)
    exec bash "$(cd "$(dirname "$0")" && pwd)/compose.sh" up --no-index
    ;;
esac
