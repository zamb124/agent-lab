# Фаза 5 — паритет push (Web Push vs APNs)

## Текущее состояние веба

- Подписка через VAPID: [`core/frontend/static/services/pwa.service.js`](../../core/frontend/static/services/pwa.service.js).
- API: `GET .../api/push/vapid-public-key`, `POST .../api/push/subscribe` (см. [`core/push/router.py`](../../core/push/router.py)).

## Android TWA

Поведение как в Chrome: Web Push (VAPID) при поддержке каналом.

## iOS из App Store (Capacitor / WKWebView)

Фоновые уведомления по тому же Web Push pipeline, что в Safari PWA, в нативной оболочке **часто недоступны или нестабильны**. Целевой вариант паритета:

1. **Apple Push Notification service (APNs)** через плагин Capacitor Push Notifications.
2. На бэкенде — регистрация устройства с типом клиента (например `ios_native_apns` vs `web_push_vapid`), маршрутизация отправки.
3. Веб-код: при `Capacitor.isNativePlatform()` вызывать регистрацию нативного токена вместо `PushManager.subscribe`.

Этот документ фиксирует решение на уровне архитектуры; реализация — отдельные задачи на backend и `pwa.service.js` / обёртку уведомлений.
