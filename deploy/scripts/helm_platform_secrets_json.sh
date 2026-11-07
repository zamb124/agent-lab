#!/usr/bin/env bash
# Печатает JSON для helm --set-json platformSecrets='<stdout>' из переменных окружения.
# jq корректно экранирует переводы строк и кавычки (--set-string с этим ломался).
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "helm_platform_secrets_json.sh: нужен jq (APT/Homebrew)." >&2
  exit 1
fi

if [ -z "${PROXY_ENABLED:-}" ]; then
  PROXY_ENABLED="false"
fi
if [ -z "${PROXY_PROXIES:-}" ]; then
  PROXY_PROXIES="[]"
fi

jq -n \
  --arg postgresPassword "${POSTGRES_PASSWORD:-}" \
  --arg openfgaApiToken "${OPENFGA_API_TOKEN:-}" \
  --arg authJwtSecret "${AUTH_JWT_SECRET:-}" \
  --arg secretsEncryptionKey "${SECRETS_ENCRYPTION_KEY:-}" \
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
  --arg s3AccessKey "${S3_ACCESS_KEY:-}" \
  --arg s3SecretKey "${S3_SECRET_KEY:-}" \
  --arg livekitApiKey "${LIVEKIT_API_KEY:-}" \
  --arg livekitApiSecret "${LIVEKIT_API_SECRET:-}" \
  --arg centrifugoApiKey "${CENTRIFUGO_API_KEY:-}" \
  --arg turnSecret "${TURN_SECRET:-}" \
  --arg onlyofficeJwtSecret "${ONLYOFFICE_JWT_SECRET:-}" \
  --arg grafanaAdminPassword "${GRAFANA_ADMIN_PASSWORD:-}" \
  --arg telegramAlertsBotToken "${TELEGRAM_ALERTS_BOT_TOKEN:-}" \
  --arg telegramAlertsChatId "${TELEGRAM_ALERTS_CHAT_ID:-}" \
  --arg llmOpenrouterApiKey "${LLM__OPENROUTER__API_KEY:-${LLM_OPENROUTER_API_KEY:-}}" \
  --arg llmOpenrouterApiKeys "${LLM__OPENROUTER__API_KEYS:-}" \
  --arg llmBothubApiKey "${LLM__BOTHUB__API_KEY:-${LLM_BOTHUB_API_KEY:-}}" \
  --arg llmBothubApiKeys "${LLM__BOTHUB__API_KEYS:-}" \
  --arg llmGroqApiKey "${LLM__GROQ__API_KEY:-}" \
  --arg llmGroqApiKeys "${LLM__GROQ__API_KEYS:-}" \
  --arg llmCerebrasApiKey "${LLM__CEREBRAS__API_KEY:-}" \
  --arg llmCerebrasApiKeys "${LLM__CEREBRAS__API_KEYS:-}" \
  --arg llmGoogleApiKey "${LLM__GOOGLE__API_KEY:-}" \
  --arg llmGoogleApiKeys "${LLM__GOOGLE__API_KEYS:-}" \
  --arg llmGithubApiKey "${LLM__GITHUB__API_KEY:-}" \
  --arg llmGithubApiKeys "${LLM__GITHUB__API_KEYS:-}" \
  --arg llmHuggingfaceApiKey "${LLM__HUGGINGFACE__API_KEY:-}" \
  --arg llmHuggingfaceApiKeys "${LLM__HUGGINGFACE__API_KEYS:-}" \
  --arg llmNvidiaApiKey "${LLM__NVIDIA__API_KEY:-}" \
  --arg llmNvidiaApiKeys "${LLM__NVIDIA__API_KEYS:-}" \
  --arg llmMistralApiKey "${LLM__MISTRAL__API_KEY:-}" \
  --arg llmMistralApiKeys "${LLM__MISTRAL__API_KEYS:-}" \
  --arg llmZaiApiKey "${LLM__ZAI__API_KEY:-}" \
  --arg llmZaiApiKeys "${LLM__ZAI__API_KEYS:-}" \
  --arg llmSambanovaApiKey "${LLM__SAMBANOVA__API_KEY:-}" \
  --arg llmSambanovaApiKeys "${LLM__SAMBANOVA__API_KEYS:-}" \
  --arg llmDeepinfraApiKey "${LLM__DEEPINFRA__API_KEY:-}" \
  --arg llmDeepinfraApiKeys "${LLM__DEEPINFRA__API_KEYS:-}" \
  --arg llmCailaApiKey "${LLM__CAILA__API_KEY:-}" \
  --arg llmCailaApiKeys "${LLM__CAILA__API_KEYS:-}" \
  --arg llmYandexApiKey "${LLM__YANDEX__API_KEY:-}" \
  --arg llmYandexApiKeys "${LLM__YANDEX__API_KEYS:-}" \
  --arg llmYandexFolderId "${LLM__YANDEX__FOLDER_ID:-}" \
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
  --arg tinkoffTerminalKey "${TINKOFF_TERMINAL_KEY:-}" \
  --arg tinkoffTerminalPassword "${TINKOFF_TERMINAL_PASSWORD:-}" \
  --arg proxyEnabled "$PROXY_ENABLED" \
  --arg proxyProxies "$PROXY_PROXIES" \
  --arg searchTinyfishApiKey "${SEARCH__TINYFISH__API_KEY:-}" \
  --arg searchLinkupApiKey "${SEARCH__LINKUP__API_KEY:-}" \
  --arg searchSerperApiKey "${SEARCH__SERPER__API_KEY:-}" \
  --arg searchTavilyApiKey "${SEARCH__TAVILY__API_KEY:-}" \
  --arg mailSystemIspmanagerAuthinfoPassword "${MAIL__SYSTEM__ISPMANAGER__AUTHINFO_PASSWORD:-}" \
  --arg customerAuthTgBotToken "${CUSTOMER_AUTH_TG_BOT_TOKEN:-}" \
  --arg customerAuthTgBotUsername "${CUSTOMER_AUTH_TG_BOT_USERNAME:-}" \
  --arg customerAuthTgWebhookSecret "${CUSTOMER_AUTH_TG_WEBHOOK_SECRET:-}" \
  --arg customerAuthMaxAccessToken "${CUSTOMER_AUTH_MAX_ACCESS_TOKEN:-}" \
  --arg customerAuthMaxBotName "${CUSTOMER_AUTH_MAX_BOT_NAME:-}" \
  --arg customerAuthMaxWebhookSecret "${CUSTOMER_AUTH_MAX_WEBHOOK_SECRET:-}" \
  --arg customerAuthYandexClientId "${CUSTOMER_AUTH_YANDEX_CLIENT_ID:-}" \
  --arg customerAuthYandexClientSecret "${CUSTOMER_AUTH_YANDEX_CLIENT_SECRET:-}" \
  --arg customerAuthVkClientId "${CUSTOMER_AUTH_VK_CLIENT_ID:-}" \
  --arg customerAuthVkClientSecret "${CUSTOMER_AUTH_VK_CLIENT_SECRET:-}" \
  --arg customerAuthSberClientId "${CUSTOMER_AUTH_SBER_CLIENT_ID:-}" \
  --arg customerAuthSberClientSecret "${CUSTOMER_AUTH_SBER_CLIENT_SECRET:-}" \
  --arg customerAuthSmsruApiId "${CUSTOMER_AUTH_SMSRU_API_ID:-}" \
  --arg customerAuthSmsruSender "${CUSTOMER_AUTH_SMSRU_SENDER:-}" \
  '{
    create: true,
    postgresPassword: $postgresPassword,
    openfgaApiToken: $openfgaApiToken,
    authJwtSecret: $authJwtSecret,
    secretsEncryptionKey: $secretsEncryptionKey,
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
    s3AccessKey: $s3AccessKey,
    s3SecretKey: $s3SecretKey,
    livekitApiKey: $livekitApiKey,
    livekitApiSecret: $livekitApiSecret,
    centrifugoApiKey: $centrifugoApiKey,
    turnSecret: $turnSecret,
    onlyofficeJwtSecret: $onlyofficeJwtSecret,
    grafanaAdminPassword: $grafanaAdminPassword,
    telegramAlertsBotToken: $telegramAlertsBotToken,
    telegramAlertsChatId: $telegramAlertsChatId,
    llmOpenrouterApiKey: $llmOpenrouterApiKey,
    llmOpenrouterApiKeys: $llmOpenrouterApiKeys,
    llmBothubApiKey: $llmBothubApiKey,
    llmBothubApiKeys: $llmBothubApiKeys,
    llmGroqApiKey: $llmGroqApiKey,
    llmGroqApiKeys: $llmGroqApiKeys,
    llmCerebrasApiKey: $llmCerebrasApiKey,
    llmCerebrasApiKeys: $llmCerebrasApiKeys,
    llmGoogleApiKey: $llmGoogleApiKey,
    llmGoogleApiKeys: $llmGoogleApiKeys,
    llmGithubApiKey: $llmGithubApiKey,
    llmGithubApiKeys: $llmGithubApiKeys,
    llmHuggingfaceApiKey: $llmHuggingfaceApiKey,
    llmHuggingfaceApiKeys: $llmHuggingfaceApiKeys,
    llmNvidiaApiKey: $llmNvidiaApiKey,
    llmNvidiaApiKeys: $llmNvidiaApiKeys,
    llmMistralApiKey: $llmMistralApiKey,
    llmMistralApiKeys: $llmMistralApiKeys,
    llmZaiApiKey: $llmZaiApiKey,
    llmZaiApiKeys: $llmZaiApiKeys,
    llmSambanovaApiKey: $llmSambanovaApiKey,
    llmSambanovaApiKeys: $llmSambanovaApiKeys,
    llmDeepinfraApiKey: $llmDeepinfraApiKey,
    llmDeepinfraApiKeys: $llmDeepinfraApiKeys,
    llmCailaApiKey: $llmCailaApiKey,
    llmCailaApiKeys: $llmCailaApiKeys,
    llmYandexApiKey: $llmYandexApiKey,
    llmYandexApiKeys: $llmYandexApiKeys,
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
    tinkoffTerminalKey: $tinkoffTerminalKey,
    tinkoffTerminalPassword: $tinkoffTerminalPassword,
    proxyEnabled: $proxyEnabled,
    proxyProxies: $proxyProxies,
    searchTinyfishApiKey: $searchTinyfishApiKey,
    searchLinkupApiKey: $searchLinkupApiKey,
    searchSerperApiKey: $searchSerperApiKey,
    searchTavilyApiKey: $searchTavilyApiKey,
    mailSystemIspmanagerAuthinfoPassword: $mailSystemIspmanagerAuthinfoPassword,
    customerAuthTgBotToken: $customerAuthTgBotToken,
    customerAuthTgBotUsername: $customerAuthTgBotUsername,
    customerAuthTgWebhookSecret: $customerAuthTgWebhookSecret,
    customerAuthMaxAccessToken: $customerAuthMaxAccessToken,
    customerAuthMaxBotName: $customerAuthMaxBotName,
    customerAuthMaxWebhookSecret: $customerAuthMaxWebhookSecret,
    customerAuthYandexClientId: $customerAuthYandexClientId,
    customerAuthYandexClientSecret: $customerAuthYandexClientSecret,
    customerAuthVkClientId: $customerAuthVkClientId,
    customerAuthVkClientSecret: $customerAuthVkClientSecret,
    customerAuthSberClientId: $customerAuthSberClientId,
    customerAuthSberClientSecret: $customerAuthSberClientSecret,
    customerAuthSmsruApiId: $customerAuthSmsruApiId,
    customerAuthSmsruSender: $customerAuthSmsruSender
  }'
