#!/usr/bin/env bash
# Устарел: GPU живёт на master. Используйте bootstrap-master.sh + bootstrap-nvidia.sh.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

log_error "Отдельная GPU-нода не входит в канон. На master: bash $SCRIPT_DIR/bootstrap-master.sh"
exit 1
