#!/usr/bin/env bash
# Снимает блокировку Helm: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress.
# Удаляет только Kubernetes Secret(ы) ревизии с label owner=helm и status=pending-upgrade|pending-install|pending-rollback.
# Это не helm rollback: манифесты Pod/Deployment в кластере не меняются — только метаданные релиза Helm.
#
# Переменные окружения:
#   HELM_NAMESPACE (по умолчанию platform)
#   HELM_RELEASE   (по умолчанию agent-lab)
#
# Запуск: bash deploy/scripts/helm_clear_pending_release.sh
# Makefile: make k8s-helm-clear-pending

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

NS="${HELM_NAMESPACE:-platform}"
REL="${HELM_RELEASE:-agent-lab}"

require_command kubectl

log_section "Helm: удаление зависших pending-* Secret для ${REL} в ${NS}"

deleted=0
while IFS="$(printf '\t')" read -r name st; do
  if [ -z "${name}" ]; then
    continue
  fi
  case "$st" in
    pending-upgrade | pending-install | pending-rollback)
      log_do "Удаление Secret ${name} (status=${st})"
      kubectl delete secret "${name}" -n "${NS}"
      log_ok "Удалён ${name}"
      deleted=$((deleted + 1))
      ;;
    *)
      log_skip "${name} status=${st}"
      ;;
  esac
done < <(kubectl get secrets -n "${NS}" -l "owner=helm,name=${REL}" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.status}{"\n"}{end}')

if [ "${deleted}" -eq 0 ]; then
  log_skip "Нет Secret с label status=pending-* для релиза ${REL}"
fi

log_info "Проверка состояния релиза:"
if command -v helm >/dev/null 2>&1; then
  helm status "${REL}" -n "${NS}" || true
elif command -v microk8s >/dev/null 2>&1; then
  microk8s helm3 status "${REL}" -n "${NS}" || true
else
  log_warn "Утилита helm не найдена; выполните вручную: helm status ${REL} -n ${NS}"
fi
