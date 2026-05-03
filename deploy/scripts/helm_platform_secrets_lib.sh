#!/usr/bin/env bash
# Аргументы Helm для блока values.platformSecrets из переменных окружения.
# Только имена переменных; значения не хранятся в файле.
#
# После вызова helm_platform_secrets_fill_flags используйте массив:
#   HELM_PLATFORM_SECRETS_FLAGS
#
# Использование:
#   source deploy/scripts/helm_platform_secrets_lib.sh
#   helm_platform_secrets_fill_flags
#   helm upgrade ... "${HELM_PLATFORM_SECRETS_FLAGS[@]}"

HELM_PLATFORM_SECRETS_FLAGS=()

helm_platform_secrets_fill_flags() {
  HELM_PLATFORM_SECRETS_FLAGS=()
  local _rag
  _rag="${RAG_EMBEDDING_API_KEY:-}"
  if [ -z "$_rag" ]; then
    _rag="${LLM_OPENROUTER_API_KEY:-}"
  fi

  HELM_PLATFORM_SECRETS_FLAGS+=(--set platformSecrets.create=true)
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.postgresPassword=${POSTGRES_PASSWORD}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authJwtSecret=${AUTH_JWT_SECRET}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.hfToken=${HF_TOKEN:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authYandexClientId=${AUTH_YANDEX_CLIENT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authYandexClientSecret=${AUTH_YANDEX_CLIENT_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authGoogleClientId=${AUTH_GOOGLE_CLIENT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authGoogleClientSecret=${AUTH_GOOGLE_CLIENT_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authGithubClientId=${AUTH_GITHUB_CLIENT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authGithubClientSecret=${AUTH_GITHUB_CLIENT_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authAmocrmClientId=${AUTH_AMOCRM_CLIENT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authAmocrmClientSecret=${AUTH_AMOCRM_CLIENT_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authApplePrivateKey=${AUTH_APPLE_PRIVATE_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.authDemoPassword=${AUTH_DEMO_PASSWORD:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.pushVapidPublicKey=${PUSH_VAPID_PUBLIC_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.pushVapidPrivateKey=${PUSH_VAPID_PRIVATE_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.pushApnsPrivateKey=${PUSH_APNS_PRIVATE_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.pushFcmCredentialsJson=${PUSH_FCM_CREDENTIALS_JSON:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.pushFcmProjectId=${PUSH_FCM_PROJECT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.selectelAccessKey=${SELECTEL_ACCESS_KEY}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.selectelSecretKey=${SELECTEL_SECRET_KEY}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.livekitApiKey=${LIVEKIT_API_KEY}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.livekitApiSecret=${LIVEKIT_API_SECRET}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.turnSecret=${TURN_SECRET}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.onlyofficeJwtSecret=${ONLYOFFICE_JWT_SECRET}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.grafanaAdminPassword=${GRAFANA_ADMIN_PASSWORD}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.llmBothubApiKey=${LLM_BOTHUB_API_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.llmOpenrouterApiKey=${LLM_OPENROUTER_API_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.sttCloudRuApiKey=${STT_CLOUD_RU_API_KEY:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.ragEmbeddingApiKey=${_rag}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.yoomoneyAccountNumber=${YOOMONEY_ACCOUNT_NUMBER:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.yoomoneyNotificationSecret=${YOOMONEY_NOTIFICATION_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.yoomoneyClientId=${YOOMONEY_CLIENT_ID:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.yoomoneyClientSecret=${YOOMONEY_CLIENT_SECRET:-}")
  HELM_PLATFORM_SECRETS_FLAGS+=(--set-string "platformSecrets.yoomoneyAccessToken=${YOOMONEY_ACCESS_TOKEN:-}")
}
