#!/usr/bin/env bash
# Перед helm upgrade --install с созданием platform-secrets: если релиза ещё нет,
# а Secret platform-secrets уже есть (kubectl apply / ручной импорт), Helm падает с
# «invalid ownership metadata». Скрипт выходит с кодом 1 и подсказкой.
#
# Задайте HELM_WILL_CREATE_PLATFORM_SECRET=1 только когда в релиз входит
# templates/01-platform-secrets.yaml (platformSecrets.create=true), например CI и
# make k8s-deploy с POSTGRES_PASSWORD.
set -euo pipefail

SECRET_NAME="${PLATFORM_SECRET_NAME:-platform-secrets}"
RELEASE="${HELM_RELEASE:-agent-lab}"
NS="${HELM_NAMESPACE:-platform}"

if [[ "${HELM_WILL_CREATE_PLATFORM_SECRET:-0}" != "1" ]]; then
  exit 0
fi

if helm status "$RELEASE" -n "$NS" >/dev/null 2>&1; then
  exit 0
fi

if ! kubectl get secret "$SECRET_NAME" -n "$NS" >/dev/null 2>&1; then
  exit 0
fi

echo "::error title=Helm install blocked by existing Secret::В namespace «${NS}» уже есть Secret «${SECRET_NAME}», но Helm-релиз «${RELEASE}» не установлен (первый install). Секрет создан не через Helm — добавить его в релиз нельзя без меток владельца." >&2
echo "" >&2
echo "Что сделать: сохранить значения ключей (если нужно), затем удалить секрет и повторить деплой — Helm создаст Secret из GitHub Secrets / helm_platform_secrets_json.sh:" >&2
echo "  kubectl delete secret ${SECRET_NAME} -n ${NS}" >&2
echo "" >&2
echo "Если секрет нужен как внешний (platformSecrets.create=false), отключите создание в чарте и не передавайте create:true в --set-json platformSecrets." >&2
exit 1
