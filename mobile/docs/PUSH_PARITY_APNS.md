# Паритет push (Web Push vs APNs)

## Веб и Android TWA

- Регистрация: [`PWAService.ensurePushRegistration`](../../core/frontend/static/services/pwa.service.js) (вызывается из [`PlatformApp`](../../core/frontend/static/lib/base/PlatformApp.js) после успешной авторизации).
- Web Push: VAPID, тело `POST .../api/push/subscribe` с **`transport: "web_vapid"`**.
- API: `GET .../api/push/vapid-public-key`, `POST .../api/push/subscribe` — [`core/push/router.py`](../../core/push/router.py), схема — [`core/push/schemas.py`](../../core/push/schemas.py).

## iOS из App Store (Capacitor)

Web Push в WKWebView неполноценен; используется **APNs**:

1. Зависимость **`@capacitor/push-notifications`** в [`mobile/package.json`](../package.json), **`npx cap sync ios`**, в Xcode — capability **Push Notifications** (см. [`IOS_CAPACITOR.md`](IOS_CAPACITOR.md)).
2. JS: на нативной iOS-среде `ensurePushRegistration` вызывает плагин и шлёт на бэкенд **`transport: "ios_apns"`** и `keys.device_token`.
3. Бэкенд: [`ApnsPushService`](../../core/push/apns_service.py), маршрутизация в [`deliver_offline_push`](../../core/push/delivery.py). Учётные данные: [`resolve_apns_credentials`](../../core/push/apns_credentials.py) — при пустых `push.apns_team_id` / `push.apns_key_id` / `push.apns_private_key` подставляются поля **`auth.providers.apple`** (тот же `.p8`, что для Sign in with Apple, если в Apple Developer у ключа включён APNs). В `conf.json` обязателен **`push.apns_bundle_id`** (iOS App).
