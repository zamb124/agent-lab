#!/usr/bin/env bash
# Печатает JSON для helm --set-json platformSecrets='<stdout>' из переменных окружения.
# jq корректно экранирует переводы строк и кавычки (--set-string с этим ломался).
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "helm_platform_secrets_json.sh: нужен jq (APT/Homebrew)." >&2
  exit 1
fi

jq -n \
  --arg postgresPassword "${POSTGRES_PASSWORD:-}" \
  --arg authJwtSecret "${AUTH_JWT_SECRET:-}" \
  --arg hfToken "${HF_TOKEN:-}" \
  --arg authYandexClientId "${AUTH_YANDEX_CLIENT_ID:-}" \
  --arg authYandexClientSecret "${AUTH_YANDEX_CLIENT_SECRET:-}" \
  --arg authGoogleClientId "${AUTH_GOOGLE_CLIENT_ID:-}" \
  --arg authGoogleClientSecret "${AUTH_GOOGLE_CLIENT_SECRET:-}" \
  --arg authGithubClientId "${AUTH_GITHUB_CLIENT_ID:-}" \
  --arg authGithubClientSecret "${AUTH_GITHUB_CLIENT_SECRET:-}" \
  --arg authAmocrmClientId "${AUTH_AMOCRM_CLIENT_ID:-}" \
  --arg authAmocrmClientSecret "${AUTH_AMOCRM_CLIENT_SECRET:-}" \
  --arg authApplePrivateKey "${AUTH_APPLE_PRIVATE_KEY:-}" \
  --arg authDemoPassword "${AUTH_DEMO_PASSWORD:-}" \
  --arg pushVapidPublicKey "${PUSH_VAPID_PUBLIC_KEY:-}" \
  --arg pushVapidPrivateKey "${PUSH_VAPID_PRIVATE_KEY:-}" \
  --arg pushApnsPrivateKey "${PUSH_APNS_PRIVATE_KEY:-}" \
  --arg pushFcmCredentialsJson "${PUSH_FCM_CREDENTIALS_JSON:-}" \
  --arg pushFcmProjectId "${PUSH_FCM_PROJECT_ID:-}" \
  --arg selectelAccessKey "${SELECTEL_ACCESS_KEY:-}" \
  --arg selectelSecretKey "${SELECTEL_SECRET_KEY:-}" \
  --arg livekitApiKey "${LIVEKIT_API_KEY:-}" \
  --arg livekitApiSecret "${LIVEKIT_API_SECRET:-}" \
  --arg turnSecret "${TURN_SECRET:-}" \
  --arg onlyofficeJwtSecret "${ONLYOFFICE_JWT_SECRET:-}" \
  --arg grafanaAdminPassword "${GRAFANA_ADMIN_PASSWORD:-}" \
  --arg llmBothubApiKey "${LLM_BOTHUB_API_KEY:-}" \
  --arg llmOpenrouterApiKey "${LLM_OPENROUTER_API_KEY:-}" \
  --arg llmYandexApiKey "${LLM_YANDEX_API_KEY:-}" \
  --arg llmYandexFolderId "${LLM_YANDEX_FOLDER_ID:-}" \
  --arg sttCloudRuApiKey "${STT_CLOUD_RU_API_KEY:-}" \
  --arg sttYandexApiKey "${STT_YANDEX_API_KEY:-}" \
  --arg sttYandexFolderId "${STT_YANDEX_FOLDER_ID:-}" \
  --arg sttSberClientId "${STT_SBER_CLIENT_ID:-}" \
  --arg sttSberClientSecret "${STT_SBER_CLIENT_SECRET:-}" \
  --arg ttsCloudRuApiKey "${TTS_CLOUD_RU_API_KEY:-}" \
  --arg ttsYandexApiKey "${TTS_YANDEX_API_KEY:-}" \
  --arg ttsYandexFolderId "${TTS_YANDEX_FOLDER_ID:-}" \
  --arg ttsSberClientId "${TTS_SBER_CLIENT_ID:-}" \
  --arg ttsSberClientSecret "${TTS_SBER_CLIENT_SECRET:-}" \
  --arg ragEmbeddingApiKey "${RAG_EMBEDDING_API_KEY:-}" \
  --arg yoomoneyAccountNumber "${YOOMONEY_ACCOUNT_NUMBER:-}" \
  --arg yoomoneyNotificationSecret "${YOOMONEY_NOTIFICATION_SECRET:-}" \
  --arg yoomoneyClientId "${YOOMONEY_CLIENT_ID:-}" \
  --arg yoomoneyClientSecret "${YOOMONEY_CLIENT_SECRET:-}" \
  --arg yoomoneyAccessToken "${YOOMONEY_ACCESS_TOKEN:-}" \
  '{
    create: true,
    postgresPassword: $postgresPassword,
    authJwtSecret: $authJwtSecret,
    hfToken: $hfToken,
    authYandexClientId: $authYandexClientId,
    authYandexClientSecret: $authYandexClientSecret,
    authGoogleClientId: $authGoogleClientId,
    authGoogleClientSecret: $authGoogleClientSecret,
    authGithubClientId: $authGithubClientId,
    authGithubClientSecret: $authGithubClientSecret,
    authAmocrmClientId: $authAmocrmClientId,
    authAmocrmClientSecret: $authAmocrmClientSecret,
    authApplePrivateKey: $authApplePrivateKey,
    authDemoPassword: $authDemoPassword,
    pushVapidPublicKey: $pushVapidPublicKey,
    pushVapidPrivateKey: $pushVapidPrivateKey,
    pushApnsPrivateKey: $pushApnsPrivateKey,
    pushFcmCredentialsJson: $pushFcmCredentialsJson,
    pushFcmProjectId: $pushFcmProjectId,
    selectelAccessKey: $selectelAccessKey,
    selectelSecretKey: $selectelSecretKey,
    livekitApiKey: $livekitApiKey,
    livekitApiSecret: $livekitApiSecret,
    turnSecret: $turnSecret,
    onlyofficeJwtSecret: $onlyofficeJwtSecret,
    grafanaAdminPassword: $grafanaAdminPassword,
    llmBothubApiKey: $llmBothubApiKey,
    llmOpenrouterApiKey: $llmOpenrouterApiKey,
    llmYandexApiKey: $llmYandexApiKey,
    llmYandexFolderId: $llmYandexFolderId,
    sttCloudRuApiKey: $sttCloudRuApiKey,
    sttYandexApiKey: $sttYandexApiKey,
    sttYandexFolderId: $sttYandexFolderId,
    sttSberClientId: $sttSberClientId,
    sttSberClientSecret: $sttSberClientSecret,
    ttsCloudRuApiKey: $ttsCloudRuApiKey,
    ttsYandexApiKey: $ttsYandexApiKey,
    ttsYandexFolderId: $ttsYandexFolderId,
    ttsSberClientId: $ttsSberClientId,
    ttsSberClientSecret: $ttsSberClientSecret,
    ragEmbeddingApiKey: $ragEmbeddingApiKey,
    yoomoneyAccountNumber: $yoomoneyAccountNumber,
    yoomoneyNotificationSecret: $yoomoneyNotificationSecret,
    yoomoneyClientId: $yoomoneyClientId,
    yoomoneyClientSecret: $yoomoneyClientSecret,
    yoomoneyAccessToken: $yoomoneyAccessToken
  }'
