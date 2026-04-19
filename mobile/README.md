# Сборки магазинов (iOS + Android, обе на Capacitor)

Каталог **`mobile/`** — оболочки, конфиги и документация для упаковки PWA в магазины приложений. **UI и бизнес-логика** — в `core/` и `apps/*/ui/`. iOS и Android используют один и тот же стек (Capacitor 6), общий [`capacitor.config.json`](capacitor.config.json) и общий веб-код; различия — только нативная подложка под каждую платформу.

## Операционные гиды

| Тема | Документ |
|------|----------|
| **iOS** — Capacitor, Xcode, safe area, иконки, OAuth | [`docs/IOS_CAPACITOR.md`](docs/IOS_CAPACITOR.md) |
| **Android** — Capacitor, AndroidManifest, App Links, FCM | [`android/README.md`](android/README.md) |
| **App Store** — где кликать в Apple | [`docs/APPLE_MANUAL.md`](docs/APPLE_MANUAL.md) |
| **App Store** — поля и тексты Humanitec | [`docs/APP_STORE_HUMANITEC.md`](docs/APP_STORE_HUMANITEC.md) |
| **Google Play** — где кликать в Console | [`docs/PLAY_MANUAL.md`](docs/PLAY_MANUAL.md) |
| **Google Play** — поля и тексты Humanitec | [`docs/PLAY_HUMANITEC.md`](docs/PLAY_HUMANITEC.md) |
| **Push** — паритет Web / APNs / FCM | [`docs/PUSH_PARITY.md`](docs/PUSH_PARITY.md) |
| **Скриншоты** — ресайз под слоты ASC и Play | [`screens/README.md`](screens/README.md), `uv run python mobile/screens/generate_app_store_screenshots.py` |

## Проверки PWA (production)

Нужны для той же среды, что откроет оболочка.

- Манифест и SW: [`scripts/check-pwa-manifest-url.sh`](scripts/check-pwa-manifest-url.sh) — в `mobile/.env` задать `PWA_MANIFEST_URL` (см. [`config/env.example`](config/env.example)).
- Lighthouse: `export PWA_LIGHTHOUSE_URL="https://<host>/"`, затем [`scripts/run-lighthouse-ci.sh`](scripts/run-lighthouse-ci.sh) или `npm run pwa:lighthouse` в `mobile/`; пороги — [`lighthouserc.cjs`](lighthouserc.cjs).
- VAPID: `GET /<service>/api/push/vapid-public-key` на том же origin (см. [`core/push/router.py`](../core/push/router.py)).

## Релизы и обновления

- **Только веб:** деплой `core/` и `apps/` — обе оболочки подхватывают изменения **без** нового бинарника, пока не меняются `applicationId` / bundle id, signing, домены, нативные плагины или разрешения.
- **Новый билд:** смена package/bundle id, новые разрешения (Info.plist / AndroidManifest), обновление Capacitor / SDK / нативных плагинов.
- **Версии:** Android — монотонно `versionCode`; iOS — `CFBundleShortVersionString` / `CFBundleVersion` по правилам Apple.
- **Витрина App Store:** тексты и скриншоты — только вручную в [App Store Connect](https://appstoreconnect.apple.com); чеклист — [`docs/APPLE_MANUAL.md`](docs/APPLE_MANUAL.md).
- **Витрина Google Play:** тексты, скриншоты, Data safety, Content rating — вручную в [Play Console](https://play.google.com/console); чеклист — [`docs/PLAY_MANUAL.md`](docs/PLAY_MANUAL.md).
- **CI:** подпись только в защищённых ветках; секреты не в git. Lighthouse PWA по URL: [`.github/workflows/mobile-pwa-lighthouse.yml`](../.github/workflows/mobile-pwa-lighthouse.yml). Сборка Android AAB: [`.github/workflows/mobile-android-build.yml`](../.github/workflows/mobile-android-build.yml).

## Связь с репозиторием

| Компонент | Где |
|-----------|-----|
| Манифест, SW, offline | [`core/frontend/pwa/`](../core/frontend/pwa/) |
| Маршруты `/manifest.json`, `/sw.js`, `/.well-known/assetlinks.json`, `/.well-known/apple-app-site-association` | [`core/app/pwa_routes.py`](../core/app/pwa_routes.py) |
| Digital Asset Links (Android App Links) | `core/frontend/pwa/assetlinks.json`, шаблон [`assetlinks.json.example`](../core/frontend/pwa/assetlinks.json.example) |
| Universal Links (iOS) | `core/frontend/pwa/apple-app-site-association`; префиксы — [`platform-deeplink-paths.js`](../core/frontend/static/lib/utils/platform-deeplink-paths.js) |
| ESM Capacitor для веб-страницы | [`core/frontend/static/assets/js/vendor/@capacitor/`](../core/frontend/static/assets/js/vendor/@capacitor/) — копии из `mobile/node_modules/@capacitor/{core,app,splash-screen,push-notifications}` (`dist/esm` → `vendor/.../index.js` + `definitions.js`); обновлять при смене версии плагинов в [`mobile/package.json`](package.json) |
| Регистрация push (web/iOS/Android) | [`core/frontend/static/lib/events/effects/pwa.effect.js`](../core/frontend/static/lib/events/effects/pwa.effect.js) |
| Доставка push (Web Push / APNs / FCM) | [`core/push/`](../core/push/) |

## Справочники

- [Дорожная карта магазинов (кратко)](docs/WATERFALL.md)
- [Tenant и start_url](docs/TENANT_START_URL.md)
- [РФ: учётки магазинов](docs/RU_OPS_ACCOUNTS.md)
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
  capacitor.config.json
  package.json
  lighthouserc.cjs
  android/                          # Capacitor Android (см. android/README.md)
    app/                            # Gradle module: src/main/{AndroidManifest, java, res}
    build.gradle, settings.gradle, ...
  ios/App/                          # Capacitor iOS (см. docs/IOS_CAPACITOR.md)
  docs/
    WATERFALL.md
    IOS_CAPACITOR.md
    APPLE_MANUAL.md
    APP_STORE_HUMANITEC.md
    PLAY_MANUAL.md
    PLAY_HUMANITEC.md
    PUSH_PARITY.md
    TENANT_START_URL.md
    RU_OPS_ACCOUNTS.md
    QA_MATRIX_TEMPLATE.md
  scripts/
    init-android.sh, build-android.sh
    check-pwa-manifest-url.sh, run-lighthouse-ci.sh
  screens/                          # Скриншоты + Play feature graphic + Play 512 icon
  config/                           # env.example, capacitor.config.json.example, assetlinks.json.template
  www/                              # Заглушка Capacitor webDir
```

## Секреты

В git **не коммитится**:
- iOS: `*.p8`, профили (`*.mobileprovision`), `Pods/`.
- Android: `*.jks`, `*.keystore`, `mobile/android/app/google-services.json`, локальные `local.properties`, `*.aab`/`*.apk`.
- Общее: `mobile/.env`.

Шаблоны: [`config/env.example`](config/env.example), [`config/assetlinks.json.template`](config/assetlinks.json.template).
