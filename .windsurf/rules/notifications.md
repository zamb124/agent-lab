---
trigger: model_decision
alwaysApply: false
description: "Система уведомлений уведомления notification notifications"
---
# Система нотификаций (канон)

## Единый поток

`Service/Worker/Task -> notify_user(...) -> Redis (platform:ui_events) -> WS /<svc>/api/ws/notifications -> platform-notification-manager -> toast + badge`

`notify_user` оборачивает уведомление в `UIEvent` (`type: notify/<service>/<kind>_received`) и публикует через [`publish_ui_event`](../../core/ui_events/dispatcher.py) в канал `platform:ui_events`. WS-менеджер ([`core/websocket/manager.py`](../../core/websocket/manager.py)) форвардит ровно сериализованный `UIEvent` (`{id, type, payload, meta}`) в сокеты адресата.

Исключение **операторские задачи flows**: **`publish_operator_tasks_refresh`** ([`apps/flows/src/services/operator_tasks_broadcast.py`](../../apps/flows/src/services/operator_tasks_broadcast.py)) публикует UIEvent-конверт `{target, event}` в тот же канал `platform:ui_events` напрямую через **`RedisClient.publish`** контейнера (работает и в **TaskIQ worker**, где singleton **`notification_manager._redis_client`** не инициализирован). Тип события — **`notify/flows/flows_operator_tasks_updated_received`**; `payload.kind = "flows_operator_tasks_updated"`. В **`platform-notification-manager`** без toast и без записи в колокольчик — отдельное WS-подключение на **`operator-workbench-page`** перезагружает канбан по этому событию.

## Backend: как отправлять

Только через `core.websocket.publisher.notify_user`.

```python
from core.websocket.publisher import Notification, NotificationType, notify_user

await notify_user(
    user_id="user_123",
    notification=Notification(
        type=NotificationType.SYSTEM,
        title="Готово",
        message="Операция завершена",
        service="crm",
        priority="normal",
        action_url="/crm/tasks/task_1",
        data={"task_id": "task_1"},
    ),
)
```

Разрешено вызывать из service/worker/TaskIQ/endpoint.  
Хранить уведомления в БД нельзя: канал только real-time.

## Офлайн: Web Push и APNs

Если у пользователя **нет** активного WebSocket к `/<svc>/api/ws/notifications`, `notify_user` дополнительно вызывает [`deliver_offline_push`](../../core/push/delivery.py):

- Подписки с `endpoint`, начинающимся с **`https://`**, и `transport: web_vapid` (см. [`SubscribeRequest`](../../core/push/schemas.py)) уходят в **VAPID** ([`WebPushService`](../../core/push/service.py)).
- Подписки с `endpoint` вида **`apns:<hex>`** (регистрация из нативного iOS через Capacitor) уходят в **APNs** ([`ApnsPushService`](../../core/push/apns_service.py)), если [`resolve_apns_credentials`](../../core/push/apns_credentials.py) собрал полный набор: обязателен **`push.apns_bundle_id`**, остальное — из **`push.apns_*`** или из **`auth.providers.apple`** (тот же `.p8`, что для Sign in with Apple, если у ключа в Apple Developer включён APNs).

Инициализация: [`create_service_app` lifespan](../../core/app/factory.py) — `init_web_push_service` при `push.enabled`; `init_apns_push_service` при успешном `resolve_apns_credentials`. Тот же APNs-init в **sync worker** ([`apps/sync/realtime/broker.py`](../../apps/sync/realtime/broker.py)).

API: `POST .../api/push/subscribe` с **`transport`**: `web_vapid` | `ios_apns`. Клиент: pwa-эффект [`core/frontend/static/lib/events/effects/pwa.effect.js`](../../core/frontend/static/lib/events/effects/pwa.effect.js) после авторизации диспатчит `PWA_EVENTS.SUBSCRIBE_REQUESTED`; effect шлёт subscribe в backend.

Service Worker ([`core/frontend/pwa/sw.js`](../../core/frontend/pwa/sw.js)) шлёт `postMessage` с типом `humanitec-web-push` и вызывает `showNotification`. В Chrome при **активной вкладке** системный баннер часто не показывается; pwa-эффект по этому сообщению диспатчит `CoreEvents.UI_TOAST_SHOW` (glass-toast), чтобы пуш был виден в открытом приложении.

## Frontend: как показывать

- Локальные UI-тосты: `this.toast(i18n_key, { type, vars, duration })` helper
  `PlatformElement` (диспатчит `CoreEvents.UI_TOAST_SHOW`).
- Кросс-сервисные нотификации: через `<platform-notification-manager></platform-notification-manager>`
  (рендерится один раз в `PlatformApp.render()`).
- Не рендерить `glass-toast` вручную в приложениях; глобальный
  `<glass-toast>` уже смонтирован core-shell'ом.

## События в браузере

Актуальные события от менеджера:

- `notification-received` — `CustomEvent` на самом компоненте
- `platform-notification-received` — `CustomEvent` на `window`

`platform-notification` и `platform-ws-connected/disconnected` не использовать.

## Z-index (обязательно)

- Toast должен быть выше открытых модалок.
- При создании `glass-toast` использовать динамический слой: `nextModalLayerZIndex()` из `core/frontend/static/lib/utils/modal-z-stack.js`.
- Фиксированный `--z-toast` без динамического подъема для runtime-показа запрещен.

## Запрещено

- Хардкод WS URL и портов.
- Локальные самописные toast-механизмы в `apps/*/ui`.
- Broadcast уведомлений всем пользователям.
