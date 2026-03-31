# Fastlane: загрузка витрины App Store

Метаданные и скриншоты лежат в **`../store-listing/metadata/`** (формат deliver). Лента **`upload_listing`** вызывает `upload_to_app_store` без бинарника.

## Установка

```bash
cd mobile/fastlane
bundle install
```

Нужны Ruby и Bundler (macOS: системный Ruby или `brew install ruby`).

## Секреты (ключ API App Store Connect)

Рекомендуется ключ API, а не пароль Apple ID:

1. [App Store Connect](https://appstoreconnect.apple.com) — Users and Access — Keys — App Store Connect API — создать ключ, скачать `.p8` (один раз).

2. Переменные окружения перед `fastlane`:

```bash
export APP_STORE_CONNECT_KEY_ID="********"
export APP_STORE_CONNECT_ISSUER_ID="********-****-****-****-************"
export APP_STORE_CONNECT_KEY_PATH="/absolute/path/to/AuthKey_XXXXXXXXXX.p8"
export FASTLANE_TEAM_ID="ABCDE12345"   # опционально, если в Appfile не задан
```

3. Запуск:

```bash
cd mobile/fastlane
bundle exec fastlane upload_listing
```

Только текст, без замены скриншотов в консоли:

```bash
SKIP_SCREENSHOTS=1 bundle exec fastlane upload_listing
```

## CI

В GitHub Actions / Xcode Cloud: положить `.p8` в секреты или зашифровать артефакт, экспортировать переменные в шаге перед `bundle exec fastlane upload_listing`. Не коммитить ключ.
