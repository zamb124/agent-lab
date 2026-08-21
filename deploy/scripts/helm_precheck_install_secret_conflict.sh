#!/usr/bin/env bash
# Перед helm upgrade --install с созданием platform-secrets.
# Secret без меток Helm (kubectl apply / импорт при переезде) ломает и первый
# install, и upgrade: «invalid ownership metadata».
#
# Релиз уже есть — adopt в Helm (значения Secret не трогаем).
# Релиза нет + HELM_DELETE_ORPHAN_PLATFORM_SECRET=1 — удалить Secret.
# Релиза нет без флага — exit 1 с подсказкой.
#
# HELM_WILL_CREATE_PLATFORM_SECRET=1 только когда в релиз входит
# templates/01-platform-secrets.yaml (CI и make k8s-deploy с POSTGRES_PASSWORD).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SECRET_NAME="${PLATFORM_SECRET_NAME:-platform-secrets}"
RELEASE="${HELM_RELEASE:-agent-lab}"
NS="${HELM_NAMESPACE:-platform}"

if [[ "${HELM_WILL_CREATE_PLATFORM_SECRET:-0}" != "1" ]]; then
  exit 0
fi

if ! kubectl get secret "$SECRET_NAME" -n "$NS" >/dev/null 2>&1; then
  exit 0
fi

managed="$(kubectl get secret "$SECRET_NAME" -n "$NS" -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}' 2>/dev/null || true)"
release_name="$(kubectl get secret "$SECRET_NAME" -n "$NS" -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)"
if [[ "$managed" == "Helm" && "$release_name" == "$RELEASE" ]]; then
  exit 0
fi

if helm status "$RELEASE" -n "$NS" >/dev/null 2>&1; then
  echo "::notice title=Adopt orphan platform-secrets::Secret «${SECRET_NAME}» есть, но без Helm-меток — adopt в релиз «${RELEASE}»." >&2
  HELM_NAMESPACE="$NS" HELM_RELEASE="$RELEASE" \
    bash "$SCRIPT_DIR/helm_adopt_orphan_resources.sh" "secret/${SECRET_NAME}"
  exit 0
fi

if [[ "${HELM_DELETE_ORPHAN_PLATFORM_SECRET:-0}" == "1" ]]; then
  echo "::notice title=Удаление сиротского Secret::HELM_DELETE_ORPHAN_PLATFORM_SECRET=1: удаляю «${SECRET_NAME}» в «${NS}» перед первым install (значения возьмутся из Helm / GitHub Secrets)." >&2
  kubectl delete secret "$SECRET_NAME" -n "$NS"
  exit 0
fi

echo "::error title=Helm install blocked by existing Secret::В namespace «${NS}» уже есть Secret «${SECRET_NAME}», но Helm-релиз «${RELEASE}» не установлен (первый install). Секрет создан не через Helm — добавить его в релиз нельзя без меток владельца." >&2
echo "" >&2
echo "Что сделать (локально или SSH на master):" >&2
echo "  kubectl delete secret ${SECRET_NAME} -n ${NS}" >&2
echo "" >&2
echo "В GitHub Actions: запустите workflow Deploy с галочкой «replace_orphan_platform_secret» (удалит секрет автоматически один раз), либо выполните kubectl delete вручную и перезапустите." >&2
echo "" >&2
echo "Если секрет нужен как внешний (platformSecrets.create=false), отключите создание в чарте и не передавайте create:true в --set-json platformSecrets." >&2
exit 1
