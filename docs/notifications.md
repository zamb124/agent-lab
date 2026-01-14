# Система уведомлений платформы

## Архитектура

Система уведомлений предоставляет унифицированный механизм real-time уведомлений для всех сервисов платформы (CRM, RAG, Agents) через WebSocket и Redis Pub/Sub.

### Компоненты

```
┌─────────────────────────────────────────────────────────────────┐
│                         Браузер (PWA/WebView)                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  platform-notification-manager.js                         │  │
│  │  - WebSocket client                                       │  │
│  │  - Auto-reconnect                                         │  │
│  │  - Heartbeat                                              │  │
│  │  - Toast notifications                                    │  │
│  └──────────────────────┬────────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────────────┘
                          │ WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  core/websocket/router.py                                 │  │
│  │  - /ws/notifications endpoint                             │  │
│  │  - Authentication via cookies                             │  │
│  │  - Heartbeat handling                                     │  │
│  └──────────────────────┬────────────────────────────────────┘  │
│                         │                                        │
│  ┌──────────────────────▼─────────────────────────────────────┐ │
│  │  core/websocket/manager.py                                │ │
│  │  - NotificationManager                                    │ │
│  │  - Manages connections per user_id                        │ │
│  │  - Redis Pub/Sub listener                                │ │
│  └──────────────────────┬────────────────────────────────────┘ │
└─────────────────────────┼────────────────────────────────────────┘
                          │
                          │ Redis Pub/Sub
                          │ channel: platform:notifications
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Server                                 │
│  - Pub/Sub channel для межпроцессного общения                  │
│  - Ephemeral уведомления (не персистим в БД)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          ▲
                          │ publish()
                          │
┌─────────────────────────┴───────────────────────────────────────┐
│              Любой сервис (CRM/RAG/Agents/Worker)               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  core/websocket/publisher.py                              │  │
│  │  - notify_user(user_id, Notification)                     │  │
│  │  - Типы: ACCESS_REQUEST, ENTITY_UPDATED, TASK_COMPLETED   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Принципы

### 1. Ephemeral (эфемерность)
Уведомления НЕ сохраняются в БД. Они доставляются в реальном времени и исчезают после отправки.

### 2. User-Centric (ориентация на пользователя)
Все соединения группируются по `user_id`. Один пользователь может иметь множество активных WebSocket подключений (несколько вкладок, PWA, WebView).

### 3. Platform-Wide (общеплатформенность)
Система автоматически интегрируется во все сервисы через `core/app/factory.py`. Не требуется service-specific настройка.

### 4. Pub/Sub через Redis
Межпроцессное общение реализовано через Redis Pub/Sub, что позволяет:
- Worker'ам отправлять уведомления
- Множественным инстансам FastAPI синхронизироваться
- Масштабировать систему горизонтально

## Использование

### Backend: Отправка уведомления

```python
from core.websocket.publisher import notify_user, Notification, NotificationType

# В любом месте кода (сервис, worker, task)
await notify_user(
    user_id="user_123",
    notification=Notification(
        type=NotificationType.ACCESS_REQUEST,
        title="Новый запрос доступа",
        message="Пользователь John запросил доступ к 'Договор #42'",
        service="crm",
        priority="high",
        action_url="/crm/access-requests/req_456",
        data={
            "request_id": "req_456",
            "entity_id": "entity_789"
        }
    )
)
```

### Frontend: Подписка на уведомления

```html
<!-- Добавить в HTML -->
<platform-notification-manager></platform-notification-manager>
```

Компонент автоматически:
- Подключается к `/ws/notifications`
- Показывает toast уведомления
- Обновляет badge с количеством непрочитанных
- Переподключается при разрыве соединения
- Отправляет heartbeat для поддержания соединения

### Frontend: Обработка событий

```javascript
// Слушать кастомные события уведомлений
document.addEventListener('platform-notification', (e) => {
  const notification = e.detail;
  console.log('Уведомление:', notification);
  
  // Перейти по action_url при клике
  if (notification.action_url) {
    window.location.href = notification.action_url;
  }
});

// Слушать события WebSocket
document.addEventListener('platform-ws-connected', () => {
  console.log('WebSocket подключен');
});

document.addEventListener('platform-ws-disconnected', () => {
  console.log('WebSocket отключен');
});
```

## Типы уведомлений

```python
class NotificationType(str, Enum):
    ACCESS_REQUEST = "access_request"      # Запрос доступа к сущности
    ENTITY_UPDATED = "entity_updated"      # Обновление entity
    TASK_COMPLETED = "task_completed"      # Завершение задачи
    MENTION = "mention"                    # Упоминание пользователя
    SYSTEM = "system"                      # Системное уведомление
```

## Приоритеты

- `low` - информационные уведомления
- `normal` - стандартные уведомления (по умолчанию)
- `high` - требующие внимания
- `urgent` - критические, требующие немедленной реакции

## Модель уведомления

```python
class Notification(BaseModel):
    type: NotificationType           # Тип уведомления
    title: str                       # Заголовок
    message: str                     # Текст сообщения
    data: Dict[str, Any] = {}       # Дополнительные данные
    service: str                     # "crm", "rag", "agents"
    priority: str = "normal"         # Приоритет
    action_url: Optional[str] = None # URL для перехода
    created_at: datetime             # Время создания (автоматически)
```

## Интеграция в сервисы

### Автоматическое подключение

В `core/app/factory.py` автоматически:
1. Подключается WebSocket router (`/ws/notifications`)
2. Запускается Redis Pub/Sub listener при старте приложения
3. Останавливается listener при shutdown

Это означает, что **любой** сервис, использующий `create_app()` из `core/app/factory.py`, автоматически поддерживает уведомления.

### CRM: Запросы доступа

```python
# apps/crm/services/access_request_service.py
from core.websocket.publisher import notify_user, Notification, NotificationType

async def create_request(self, entity_id: str, requester_user_id: str, ...):
    # ... создание запроса ...
    
    entity = await self._entity_repo.get(entity_id)
    
    await notify_user(
        user_id=entity.user_id,
        notification=Notification(
            type=NotificationType.ACCESS_REQUEST,
            title="Новый запрос доступа",
            message=f"Пользователь {requester_user_id} запросил доступ к '{entity.name}'",
            service="crm",
            priority="high",
            action_url=f"/crm/access-requests/{request.request_id}",
            data={
                "request_id": request.request_id,
                "entity_id": entity_id,
                "requester_id": requester_user_id
            }
        )
    )
```

### RAG: Обработка документов

```python
# apps/rag/services/processing.py
from core.websocket.publisher import notify_user, Notification, NotificationType

async def process_document(self, document_id: str, user_id: str):
    # ... обработка ...
    
    await notify_user(
        user_id=user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title="Документ обработан",
            message=f"Документ '{document.name}' успешно обработан",
            service="rag",
            priority="normal",
            action_url=f"/rag/documents/{document_id}",
            data={"document_id": document_id}
        )
    )
```

### Agents: Завершение задачи

```python
# apps/agents/src/runner.py
from core.websocket.publisher import notify_user, Notification, NotificationType

async def on_task_complete(self, task_id: str, user_id: str, result: dict):
    await notify_user(
        user_id=user_id,
        notification=Notification(
            type=NotificationType.TASK_COMPLETED,
            title="Агент завершил работу",
            message=f"Задача {task_id} выполнена",
            service="agents",
            priority="normal",
            action_url=f"/agents/tasks/{task_id}",
            data={
                "task_id": task_id,
                "result": result
            }
        )
    )
```

## Мониторинг

### Статистика WebSocket соединений

```bash
GET /ws/stats
```

Ответ:
```json
{
  "total_users": 15,
  "total_connections": 23,
  "users": {
    "user_123": 3,
    "user_456": 1,
    "user_789": 2
  }
}
```

### Логирование

```python
# Все события логируются автоматически
# core/websocket/manager.py
logger.info(f"WS подключен: user={user_id}, всего={len(self._connections[user_id])}")
logger.info(f"WS отключен: user={user_id}")
logger.debug(f"User {user_id} не подключен, уведомление пропущено")
```

## Тестирование

### Unit тесты

```python
# tests/core/websocket/test_notification_manager.py
from core.websocket.manager import NotificationManager

@pytest.mark.asyncio
async def test_multiple_connections_same_user():
    manager = NotificationManager()
    user_id = "user_123"
    
    # Подключаем 3 WebSocket для одного пользователя
    await manager.connect(ws1, user_id)
    await manager.connect(ws2, user_id)
    await manager.connect(ws3, user_id)
    
    # Отправляем уведомление
    notification = {"type": "test", "message": "Hello"}
    await manager.send_to_user(user_id, notification)
    
    # Все 3 соединения получили уведомление
    assert len(ws1.received) == 1
    assert len(ws2.received) == 1
    assert len(ws3.received) == 1
```

### E2E тесты

```python
# tests/core/websocket/test_notification_e2e.py
import websockets

@pytest.mark.asyncio
async def test_access_request_notification_flow(crm_client, crm_service):
    port = crm_service.port
    ws_url = f"ws://localhost:{port}/ws/notifications"
    
    # Подключаемся к WebSocket
    async with websockets.connect(ws_url, extra_headers={
        "Cookie": f"session_id={session_id}"
    }) as ws:
        
        # Создаем запрос доступа через API
        response = await crm_client.post("/crm/api/v1/access-requests", ...)
        
        # Получаем уведомление через WebSocket
        message = await asyncio.wait_for(ws.recv(), timeout=5)
        notification = json.loads(message)
        
        assert notification["type"] == "access_request"
        assert notification["service"] == "crm"
```

## Безопасность

### Аутентификация

WebSocket соединения аутентифицируются через cookie:

```python
# core/websocket/router.py
user = await get_user_from_websocket(websocket)
if not user or not user.user_id:
    await websocket.close(code=1008, reason="Authentication required")
    return
```

### Изоляция пользователей

Уведомления доставляются **только** пользователям с соответствующим `user_id`. Невозможно получить чужие уведомления.

## Масштабирование

### Horizontal Scaling

Система автоматически работает с несколькими инстансами FastAPI:

1. Каждый инстанс имеет свой `NotificationManager`
2. Все инстансы слушают один Redis Pub/Sub канал `platform:notifications`
3. Когда любой worker/сервис публикует уведомление, все инстансы получают его
4. Каждый инстанс отправляет уведомление своим подключенным клиентам

```
Worker/Service --> Redis Pub/Sub --> FastAPI Instance 1 --> Browser Tab 1
                                 ├--> FastAPI Instance 2 --> Browser Tab 2, 3
                                 └--> FastAPI Instance 3 --> Browser Tab 4
```

### Ограничения

- **Ephemeral**: нет истории уведомлений. Если пользователь offline - уведомление теряется
- **No persistence**: уведомления не сохраняются в БД
- **Redis dependency**: требуется работающий Redis сервер

## FAQ

### Как добавить новый тип уведомления?

1. Добавить в `NotificationType` enum:
```python
class NotificationType(str, Enum):
    MY_NEW_TYPE = "my_new_type"
```

2. Использовать при отправке:
```python
await notify_user(
    user_id=user_id,
    notification=Notification(
        type=NotificationType.MY_NEW_TYPE,
        ...
    )
)
```

### Как кастомизировать UI уведомлений?

Слушай событие `platform-notification` и реализуй свою логику:

```javascript
document.addEventListener('platform-notification', (e) => {
  const notification = e.detail;
  
  // Показать кастомный UI вместо toast
  myCustomNotificationUI.show(notification);
  
  // Отменить стандартный toast
  e.preventDefault();
});
```

### Можно ли получить историю уведомлений?

Нет. Система предназначена только для real-time уведомлений. Если нужна история - реализуй отдельную систему персистентных уведомлений в БД.

### Как отключить toast на frontend?

Установи атрибут `show-toasts="false"`:

```html
<platform-notification-manager show-toasts="false"></platform-notification-manager>
```

### Работает ли система без Redis?

Нет. Redis Pub/Sub критически важен для межпроцессного общения.

## Troubleshooting

### WebSocket не подключается

1. Проверь cookie `session_id` в запросе
2. Проверь что пользователь аутентифицирован
3. Проверь логи FastAPI:
```
WS подключен: user={user_id}, всего={count}
```

### Уведомления не приходят

1. Проверь что Redis запущен
2. Проверь что Redis listener стартовал:
```
Redis listener для уведомлений запущен
```
3. Проверь что `notify_user()` вызывается с правильным `user_id`
4. Проверь логи:
```
User {user_id} не подключен, уведомление пропущено
```

### Соединение разрывается

1. Проверь heartbeat (должен отправляться каждые 30 сек)
2. Проверь что nginx/load balancer поддерживает WebSocket
3. Настрой timeout в nginx:
```nginx
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

## См. также

- [CRM Documentation](./crm.md)
- [RAG Documentation](./rag.md)
- [Core Architecture](./architecture.md)

