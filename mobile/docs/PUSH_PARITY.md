# Паритет push (Web Push, APNs, FCM)

Один backend-эндпоинт `/api/push/subscribe` принимает три транспорта; выбор зависит от того, где запущен клиент.

## Таблица транспортов

| Платформа | Канал доставки | Транспорт в `SubscribeRequest` | Ключ | Backend сервис |
|-----------|----------------|-------------------------------|------|----------------|
| Браузер / PWA standalone | Web Push (VAPID) + Service Worker | `web_vapid` | `keys.p256dh`, `keys.auth` | [`WebPushService`](../../core/push/service.py) |
| iOS из App Store (Capacitor) | Apple Push Notification service | `ios_apns` | `keys.device_token` (hex) | [`ApnsPushService`](../../core/push/apns_service.py) |
| Android из Google Play (Capacitor) | Firebase Cloud Messaging HTTP v1 | `android_fcm` | `keys.device_token` (FCM registration token) | [`FcmPushService`](../../core/push/fcm_service.py) |

Маршрутизация — в [`deliver_offline_push`](../../core/push/delivery.py): подписки разделяются по префиксу `endpoint` (`https://…` для web, `apns:<hex>` для iOS, `fcm:<token>` для Android).

## Web (браузер и PWA)

- Регистрация — в эффекте [`pwa.effect.js`](../../core/frontend/static/lib/events/effects/pwa.effect.js) на событие `pwa/push/subscribe_requested`.
- VAPID ключ выдаёт `GET .../api/push/vapid-public-key`.
- В TWA на Android (если бы использовался): web push работал бы автоматически через Chrome, но мы публикуемся через **Capacitor**, не TWA.

## iOS (Capacitor + APNs)

1. Зависимость `@capacitor/push-notifications` уже в [`mobile/package.json`](../package.json), `npx cap sync ios`.
2. В Xcode — capability **Push Notifications** + **Background Modes → Remote notifications**.
3. JS на `Capacitor.getPlatform() === 'ios'` зовёт `PushNotifications.register()` и шлёт `transport: "ios_apns"` + `keys.device_token`.
4. Backend: учётные данные собирает [`resolve_apns_credentials`](../../core/push/apns_credentials.py); при пустых `push.apns_team_id` / `push.apns_key_id` / `push.apns_private_key` подставляются `auth.providers.apple` (тот же `.p8`, что для Sign in with Apple, если у ключа в Apple Developer включён APNs). В `conf.json` обязателен `push.apns_bundle_id`.

## Android (Capacitor + FCM)

1. Зависимость `@capacitor/push-notifications` ставится через `mobile/package.json` (плагин общий для iOS и Android, нативные модули добавляет `npx cap sync android`).
2. **Firebase project** (бесплатный): Console → Project settings → **Add app → Android**, package name `ru.humanitec.app`. Скачать `google-services.json`, положить в `mobile/android/app/google-services.json` (в `.gitignore`).
3. В `mobile/android/build.gradle` уже подключён `classpath 'com.google.gms:google-services:...'`, в `mobile/android/app/build.gradle` — условный `apply plugin: 'com.google.gms.google-services'` при наличии `google-services.json`.
4. JS на `Capacitor.getPlatform() === 'android'` зовёт `PushNotifications.register()` и шлёт `transport: "android_fcm"` + `keys.device_token`.
5. Backend: учётные данные собирает [`resolve_fcm_credentials`](../../core/push/fcm_credentials.py) из `push.fcm_credentials_json` (объект service account JSON либо строка JSON в ENV `PUSH__FCM_CREDENTIALS_JSON`). Service account — Firebase Console → **Project settings → Service accounts → Generate new private key**. `project_id` берётся из самого JSON, либо переопределяется `push.fcm_project_id`.
6. [`FcmPushService`](../../core/push/fcm_service.py) использует HTTP v1 API (`POST https://fcm.googleapis.com/v1/projects/<project>/messages:send`). На ошибки `UNREGISTERED` / `INVALID_ARGUMENT` / `NOT_FOUND` — подписка удаляется автоматически (как у APNs `410`).

## Permissions

- iOS: `UIBackgroundModes → remote-notification` в [`Info.plist`](../ios/App/App/Info.plist), `aps-environment` в [`App.entitlements`](../ios/App/App/App.entitlements).
- Android: `POST_NOTIFICATIONS` (Android 13+) и `WAKE_LOCK` в [`AndroidManifest.xml`](../android/app/src/main/AndroidManifest.xml).

## Не поддерживается

- Android WebView (Capacitor) **не** даёт рабочий Web Push — отсюда необходимость FCM.
- Десктопные оболочки (Mac App Store через Catalyst или Mac Safari PWA) используют тот же `web_vapid` через системный браузер.
