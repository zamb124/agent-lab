# Сборки магазинов (Android TWA / iOS)

Каталог **`mobile/`** — оболочки, конфиги и документация для упаковки PWA в приложения. **UI и бизнес-логика** — в `core/`, `apps/*/ui/`.

## Операционные гиды

| Тема | Документ |
|------|----------|
| **iOS** — Capacitor, Xcode, safe area, иконки, OAuth | [`docs/IOS_CAPACITOR.md`](docs/IOS_CAPACITOR.md) |
| **Android** — TWA, Digital Asset Links, Bubblewrap | [`android/README.md`](android/README.md) |
| **Витрина App Store** — тексты, скриншоты, fastlane | [`store-listing/README.md`](store-listing/README.md), [`fastlane/README.md`](fastlane/README.md) |

## Проверки PWA (production)

Нужны для той же среды, что откроет оболочка.

- Манифест и SW: [`scripts/check-pwa-manifest-url.sh`](scripts/check-pwa-manifest-url.sh) — в `mobile/.env` задать `PWA_MANIFEST_URL` (см. [`config/env.example`](config/env.example)).
- Lighthouse: `export PWA_LIGHTHOUSE_URL="https://<host>/"`, затем [`scripts/run-lighthouse-ci.sh`](scripts/run-lighthouse-ci.sh) или `npm run pwa:lighthouse` в `mobile/`; пороги — [`lighthouserc.cjs`](lighthouserc.cjs).
- VAPID: `GET /<service>/api/push/vapid-public-key` на том же origin (см. [`core/push/router.py`](../core/push/router.py)).

## Релизы и обновления

- **Только веб:** деплой `core/` и `apps/` — TWA и Capacitor подхватывают изменения **без** нового бинарника, пока не меняются `applicationId` / bundle id, signing, домен, критичные нативные плагины или разрешения в манифестах.
- **Новый билд:** смена package/bundle id, новые разрешения (Info.plist / AndroidManifest), обновление Capacitor/Bubblewrap/SDK по требованию магазина, нативные плагины (push и т.д.).
- **Версии:** Android — монотонно `versionCode`; iOS — `CFBundleShortVersionString` / `CFBundleVersion` по правилам Apple.
- **Витрина из репозитория:** [`store-listing/metadata/`](store-listing/metadata/), загрузка — [`fastlane/README.md`](fastlane/README.md); скриншоты — `uv run python mobile/scripts/capture_app_store_screenshots.py` или `make store-screenshots-ios` из корня репо.
- **CI:** подпись только в защищённых ветках; секреты не в git. PWA по URL: [`.github/workflows/README.md`](../.github/workflows/README.md) (`PWA_LIGHTHOUSE_URL`).

## Связь с репозиторием

| Компонент | Где |
|-----------|-----|
| Манифест, SW, offline | [`core/frontend/pwa/`](../core/frontend/pwa/) |
| Digital Asset Links | `core/frontend/pwa/assetlinks.json` — `GET /.well-known/assetlinks.json` ([`pwa_routes.py`](../core/app/pwa_routes.py)), шаблон [`assetlinks.json.example`](../core/frontend/pwa/assetlinks.json.example) |
| Universal Links (iOS) | `core/frontend/pwa/apple-app-site-association` — `GET /.well-known/apple-app-site-association`; префиксы путей — [`platform-deeplink-paths.js`](../core/frontend/static/lib/utils/platform-deeplink-paths.js) |
| ESM Capacitor для веб-страницы | [`core/frontend/static/assets/js/vendor/@capacitor/`](../core/frontend/static/assets/js/vendor/@capacitor/) — копии из `mobile/node_modules/@capacitor/{core,app}`; обновлять при смене версии **`@capacitor/app`** / **`@capacitor/core`** в **`mobile/package.json`** |
| Маршруты `/manifest.json`, `/sw.js` | [`core/app/pwa_routes.py`](../core/app/pwa_routes.py) |
| Клиент PWA | [`core/frontend/static/services/pwa.service.js`](../core/frontend/static/services/pwa.service.js) |

## Справочники

- [Дорожная карта магазинов (кратко)](docs/WATERFALL.md)
- [Tenant и start_url](docs/TENANT_START_URL.md)
- [РФ: учётки магазинов](docs/RU_OPS_ACCOUNTS.md)
- [Push: Web vs APNs](docs/PUSH_PARITY_APNS.md)
- [QA-матрица перед релизом](docs/QA_MATRIX_TEMPLATE.md)

## Быстрый старт

```bash
cd mobile
npm install
./scripts/check-pwa-manifest-url.sh
```

Дальше — [`docs/WATERFALL.md`](docs/WATERFALL.md), [`android/README.md`](android/README.md), [`docs/IOS_CAPACITOR.md`](docs/IOS_CAPACITOR.md).

## Структура каталога

```
mobile/
  docs/WATERFALL.md
  docs/IOS_CAPACITOR.md
  docs/TENANT_START_URL.md
  docs/RU_OPS_ACCOUNTS.md
  docs/PUSH_PARITY_APNS.md
  docs/QA_MATRIX_TEMPLATE.md
  store-listing/metadata/
  fastlane/
  scripts/capture_app_store_screenshots.py
  scripts/generate_humanitec_pwa_icons.py   # корень репо: scripts/generate_humanitec_pwa_icons.py
  lighthouserc.cjs
  capacitor.config.json
  android/README.md
  config/env.example
  config/capacitor.config.json.example
  config/assetlinks.json.template
  www/index.html
  package.json
```

## Секреты

Ключи подписи, профили Apple, JSON Play Console **не в git**. Шаблон: [`config/env.example`](config/env.example).
