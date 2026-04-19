# Магазины приложений: дорожная карта (операционная)

Базовая линия продукта: **PWA на production** (HTTPS, `manifest.json`, Service Worker, маршруты в [`core/app/pwa_routes.py`](../../core/app/pwa_routes.py)). Дальше — оболочки и витрины без дублирования веб-логики в `mobile/`.

## По платформам

| Направление | Документ |
|-------------|----------|
| Android Capacitor, AndroidManifest, App Links, FCM, сборка AAB | [`android/README.md`](../android/README.md) |
| iOS Capacitor, WKWebView, Xcode | [`IOS_CAPACITOR.md`](IOS_CAPACITOR.md) |
| App Store (что заполнять в Apple вручную) | [`APPLE_MANUAL.md`](APPLE_MANUAL.md) |
| App Store: тексты витрины Humanitec | [`APP_STORE_HUMANITEC.md`](APP_STORE_HUMANITEC.md) |
| Google Play (что заполнять в Console вручную) | [`PLAY_MANUAL.md`](PLAY_MANUAL.md) |
| Google Play: тексты витрины Humanitec | [`PLAY_HUMANITEC.md`](PLAY_HUMANITEC.md) |
| Push-паритет: Web Push, APNs (iOS), FCM (Android) | [`PUSH_PARITY.md`](PUSH_PARITY.md) |
| Матрица ручных тестов перед релизом | [`QA_MATRIX_TEMPLATE.md`](QA_MATRIX_TEMPLATE.md) |

## Справочно

- Tenant и `start_url`: [`TENANT_START_URL.md`](TENANT_START_URL.md)
- Учётки разработчика и РФ: [`RU_OPS_ACCOUNTS.md`](RU_OPS_ACCOUNTS.md)

## Зависимости (логический порядок)

Сначала доступен тот же URL в браузере, что подхватит оболочка. Затем Android и/или iOS можно вести параллельно после публикации `assetlinks.json` (Android) и настройки подписи (обе платформы). Витрина и отправка на ревью — после стабильных сборок; push в фоне на iOS (APNs) и на Android (FCM) — отдельный слой, см. `PUSH_PARITY.md`.
