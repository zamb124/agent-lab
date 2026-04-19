# Android: Capacitor Shell для Google Play

Android-оболочка построена на **Capacitor 6** — тот же стек, что у iOS-сборки. `applicationId = ru.humanitec.app` совпадает с iOS bundle id; общий [`mobile/capacitor.config.json`](../capacitor.config.json), общий [`www/`](../www/), общий import map в `apps/<svc>/ui/index.html`. Веб-код, deeplink-префиксы и shell-helpers ([`native-app-shell.js`](../../core/frontend/static/lib/utils/native-app-shell.js) уже обрабатывает `androidBridge`) — без изменений между платформами.

## Предварительные условия

1. Production URL и PWA на том же хосте, что в `server.url` (см. [`mobile/README.md`](../README.md)).
2. Установлены **JDK 17+** и **Android SDK** (Android Studio Hedgehog+ или command-line tools `cmdline-tools` + `platform-tools` + `build-tools 34`).
3. В корне `mobile/`: `npm install`.

## Структура каталога

`mobile/android/` создан командой `npx cap add android` (см. ниже). Что в git, что нет — управляется [`mobile/.gitignore`](../.gitignore).

```
mobile/android/
  build.gradle, settings.gradle, gradle.properties     # Gradle root
  gradle/, gradlew, gradlew.bat                        # Gradle wrapper
  variables.gradle                                     # SDK/Android X версии
  capacitor.settings.gradle                            # генерируется cap sync, плагины (app/push/splash)
  app/
    build.gradle                                       # applicationId, signingConfigs.release из ENV
    capacitor.build.gradle                             # генерируется cap sync
    src/main/
      AndroidManifest.xml                              # permissions + intent-filter с autoVerify (App Links)
      java/ru/humanitec/app/
        MainActivity.java
        HumanitecBridgeWebChromeClient.java            # перехват window.open, аналог HumanitecWebViewNewWindowFix.swift
      res/
        mipmap-*/ic_launcher*.png                      # генерируется scripts/generate_humanitec_pwa_icons.py
        mipmap-anydpi-v26/ic_launcher*.xml             # adaptive icon
        values/ic_launcher_background.xml              # #1A1A2E
        ...
    google-services.json                               # секрет, см. ниже (FCM)
```

## Init / sync

Из корня `mobile/`:

```bash
npm run cap:android:init    # npx cap add android (или sync, если уже есть)
npm run cap:android:sync    # после правок capacitor.config.json / web-кода
npm run cap:android:open    # открыть проект в Android Studio
```

## Build (release AAB для Play)

Подпись — Play App Signing: локально только **upload key** (`*.jks`). Параметры берутся из ENV:

```bash
export ANDROID_KEYSTORE_PATH=/abs/path/humanitec-upload.jks
export ANDROID_KEYSTORE_PASSWORD='...'
export ANDROID_KEY_ALIAS=humanitec-upload
export ANDROID_KEY_PASSWORD='...'

npm run cap:android:build   # mobile/scripts/build-android.sh: cap sync android + ./gradlew bundleRelease
```

Результат: `mobile/android/app/build/outputs/bundle/release/app-release.aab`. Загружается в Play Console (см. [`docs/PLAY_MANUAL.md`](../docs/PLAY_MANUAL.md), п. 7).

Без ENV сборка пройдёт, но AAB **не будет подписан** — Play Console такой не примет; в логах Gradle будет `WARN: подпись не настроена`.

## Window.open / target=_blank (аналог iOS swizzle)

Capacitor по умолчанию игнорирует `window.open` в Android WebView. В [`MainActivity.java`](app/src/main/java/ru/humanitec/app/MainActivity.java) включается `setSupportMultipleWindows(true)` и устанавливается [`HumanitecBridgeWebChromeClient`](app/src/main/java/ru/humanitec/app/HumanitecBridgeWebChromeClient.java): URL продукта (`server.url`, `localUrl`, шаблоны `server.allowNavigation` из [`capacitor.config.json`](../capacitor.config.json)) загружаются в текущем WebView, остальные — `Intent.ACTION_VIEW` в системный браузер. Симметрично [`HumanitecWebViewNewWindowFix.swift`](../ios/App/App/HumanitecWebViewNewWindowFix.swift) на iOS.

JS-уровень ([`native-app-shell.js`](../../core/frontend/static/lib/utils/native-app-shell.js)) дополнительно патчит `window.open` и перехватывает клики по `<a target="_blank">` — это работает независимо от платформы и срабатывает раньше нативного fallback.

## App Links (Digital Asset Links)

`intent-filter` с `android:autoVerify="true"` для апексов и wildcard-поддоменов (синхронизировано с [`mobile/ios/App/App/App.entitlements`](../ios/App/App/App.entitlements)):

- `humanitec.ru` + `*.humanitec.ru`
- `humanetic.ru` + `*.humanetic.ru`
- `agents-lab.ru` + `*.agents-lab.ru`

Wildcard покрывает tenant slug-поддомены каждой компании (`artflash.humanitec.ru`, `mycompany.humanitec.ru`, …) — пользователь нажимает `https://artflash.humanitec.ru/sync/c/...` в любом приложении и попадает прямо в Humanitec. Префиксы путей синхронизированы с [`DEEPLINK_PATH_PREFIXES`](../../core/frontend/static/lib/utils/platform-deeplink-paths.js).

**Верификация:** wildcard-хосты требуют Android 12+ (API 31+). Android берёт `assetlinks.json` с **апексного** домена (`https://humanitec.ru/.well-known/assetlinks.json`) — этот один файл покрывает и сам апекс, и все его поддомены. То есть монтировать отдельный JSON на каждый slug **не нужно**, достаточно по одному файлу на корневой домен (`humanitec.ru`, `humanetic.ru`, `agents-lab.ru`).

Шаблон содержимого — [`../config/assetlinks.json.template`](../config/assetlinks.json.template). В `sha256_cert_fingerprints` нужны **оба** fingerprint: upload key и Play App Signing key — оба берутся в **Play Console → Release → Setup → App signing** после первой загрузки AAB.

`Content-Type: application/json` обязателен. Бэкенд платформы регистрирует маршрут условно (если `core/frontend/pwa/assetlinks.json` существует, см. [`core/app/pwa_routes.py`](../../core/app/pwa_routes.py)).

## Push (FCM)

См. [`docs/PUSH_PARITY.md`](../docs/PUSH_PARITY.md). Кратко:

1. Firebase Console → Add app → Android, package `ru.humanitec.app`. Скачать `google-services.json` → положить в `mobile/android/app/google-services.json` (в `.gitignore`).
2. `mobile/android/build.gradle` уже содержит `classpath 'com.google.gms:google-services:...'`; `mobile/android/app/build.gradle` подключает плагин при наличии файла.
3. Service account JSON (Firebase Console → Project settings → Service accounts → Generate new private key) → ENV `PUSH__FCM_CREDENTIALS_JSON` или поле `push.fcm_credentials_json` в `conf.json`. См. [`core/push/fcm_credentials.py`](../../core/push/fcm_credentials.py), [`core/push/fcm_service.py`](../../core/push/fcm_service.py).

## OAuth (Google / Yandex / Apple / GitHub)

`server.allowNavigation` в [`capacitor.config.json`](../capacitor.config.json) перечисляет hostname-шаблоны, где WebView **не** уходит в системный браузер. Список идентичен iOS. Для Android тот же `overrideUserAgent` с Chrome-строкой — без него Yandex иногда отдаёт сломанный JS на встроенный WebView. После правки конфига — `npm run cap:android:sync`.

## Иконки и Splash

Иконки (mipmap всех плотностей + adaptive icon с фоном `#1A1A2E`) генерирует [`scripts/generate_humanitec_pwa_icons.py`](../../scripts/generate_humanitec_pwa_icons.py). Splash — стандартный механизм Capacitor (`@capacitor/splash-screen`, конфиг в [`capacitor.config.json`](../capacitor.config.json)).

## Обновление только веба

После публикации в Play обновления UI/логики на сайте подхватываются без пересборки AAB, пока не меняются `applicationId`, signing, разрешения, версии нативных плагинов или хосты для App Links.

## Альтернативные витрины

Тот же AAB можно загружать в **RuStore**, **AppGallery** и аналогичные витрины — package, подпись и App Links совпадают. Каждое соглашение и модерация — отдельно (см. [`docs/RU_OPS_ACCOUNTS.md`](../docs/RU_OPS_ACCOUNTS.md)).
