#!/usr/bin/env bash
# Adopt orphan ресурсов в Helm-release или удаление legacy.
#
# Helm v3 отказывается upgrade'ить релиз, если в namespace уже существует ресурс
# того же name+kind БЕЗ Helm-метаданных:
#   labels:      app.kubernetes.io/managed-by=Helm
#   annotations: meta.helm.sh/release-name=<release>
#                meta.helm.sh/release-namespace=<namespace>
# Сообщение: 'invalid ownership metadata; label validation error: missing key ...'
#
# Этот скрипт идемпотентен:
#   - принимает список <kind>/<name>, переданный как аргументы или прочитанный с stdin;
#   - для каждого: если ресурс уже adopted под нужный release — SKIP;
#     иначе — annotate+label, чтобы Helm подхватил его при следующем upgrade.
#
# Дополнительный режим --delete-legacy=<kind>/<name>:
#   - просто удаляет ресурс (для legacy ingresses/services, которых больше нет в чарте).
#
# Запуск (примеры):
#   bash deploy/scripts/helm_adopt_orphan_resources.sh \
#     ingress/platform-services ingress/platform-frontend
#
#   bash deploy/scripts/helm_adopt_orphan_resources.sh \
#     --delete-legacy=ingress/platform \
#     ingress/platform-services ingress/platform-frontend
#
# Переменные окружения:
#   HELM_NAMESPACE (по умолчанию platform)
#   HELM_RELEASE   (по умолчанию agent-lab)
#   KUBECTL        (по умолчанию kubectl; на master ноде допустимо
#                   установить KUBECTL='microk8s kubectl')
#
# Makefile: make k8s-helm-adopt-orphans (см. Makefile target)

# shellcheck source=deploy/scripts/_common.sh
source "$(dirname "$0")/_common.sh"
set -euo pipefail

NS="${HELM_NAMESPACE:-platform}"
REL="${HELM_RELEASE:-agent-lab}"
KCTL="${KUBECTL:-kubectl}"

declare -a TO_DELETE=()
declare -a TO_ADOPT=()

usage() {
  cat <<EOF
Usage: $0 [--delete-legacy=<kind>/<name>]... <kind>/<name> ...

  --delete-legacy=<kind>/<name>   удалить legacy ресурс, отсутствующий в текущем чарте
  <kind>/<name>                   adopt orphan ресурса в release \$HELM_RELEASE

Env: HELM_NAMESPACE=$NS  HELM_RELEASE=$REL
EOF
}

if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

for arg in "$@"; do
  case "$arg" in
    --delete-legacy=*)
      TO_DELETE+=("${arg#--delete-legacy=}")
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    */*)
      TO_ADOPT+=("$arg")
      ;;
    *)
      log_error "Неверный аргумент: $arg (ожидается <kind>/<name> или --delete-legacy=<kind>/<name>)"
      exit 1
      ;;
  esac
done

require_command "${KCTL%% *}"

log_section "Helm adopt orphan resources в ${NS} (release=${REL})"

# 1) Удаление legacy
for ref in "${TO_DELETE[@]}"; do
  kind="${ref%/*}"
  name="${ref#*/}"
  if ! eval "${KCTL} get ${kind} ${name} -n ${NS}" >/dev/null 2>&1; then
    log_skip "delete legacy ${kind}/${name} (не существует)"
    continue
  fi
  log_do "Удаляю legacy ${kind}/${name}"
  if ! eval "${KCTL} delete ${kind} ${name} -n ${NS} --ignore-not-found=true" >/dev/null 2>&1; then
    log_error "Не удалось удалить ${kind}/${name}"
    exit 1
  fi
  log_ok "delete legacy ${kind}/${name}"
done

# 2) Adopt orphans
for ref in "${TO_ADOPT[@]}"; do
  kind="${ref%/*}"
  name="${ref#*/}"
  if ! eval "${KCTL} get ${kind} ${name} -n ${NS}" >/dev/null 2>&1; then
    log_skip "adopt ${kind}/${name} (не существует)"
    continue
  fi
  current_release=$(eval "${KCTL} get ${kind} ${name} -n ${NS} -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}'" 2>/dev/null || true)
  current_managed=$(eval "${KCTL} get ${kind} ${name} -n ${NS} -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}'" 2>/dev/null || true)

  if [ "$current_release" = "$REL" ] && [ "$current_managed" = "Helm" ]; then
    log_skip "adopt ${kind}/${name} (уже принадлежит ${REL})"
    continue
  fi

  log_do "Adopt ${kind}/${name} в release ${REL}"
  eval "${KCTL} annotate ${kind} ${name} -n ${NS} meta.helm.sh/release-name=${REL} --overwrite" >/dev/null
  eval "${KCTL} annotate ${kind} ${name} -n ${NS} meta.helm.sh/release-namespace=${NS} --overwrite" >/dev/null
  eval "${KCTL} label ${kind} ${name} -n ${NS} app.kubernetes.io/managed-by=Helm --overwrite" >/dev/null
  log_ok "adopt ${kind}/${name}"
done

print_summary
