# API Reference

Документация REST API для Agent Lab.

## Базовый URL

```
http://localhost:8001
```

## Аутентификация

Большинство endpoints требуют авторизации через cookie сессии. Авторизация через Yandex OAuth.

## Admin API

Управление агентами и flows.

### Agents

#### GET /api/v1/admin/agents

Получить список всех агентов.

**Ответ**:
```json
["calculator_agent", "weather_agent", "explainer_agent"]
```

#### GET /api/v1/admin/agents/{agent_id}

Получить конфигурацию агента.

**Ответ**:
```json
{
  "agent_id": "calculator_agent",
  "name": "Calculator Agent",
  "description": "Помогает с математическими вычислениями",
  "type": "react",
  "prompt": "Ты калькулятор-помощник...",
  "tools": [...]
}
```

#### POST /api/v1/admin/agents

Создать нового агента.

**Тело запроса**:
```json
{
  "agent_id": "my_agent",
  "name": "My Agent",
  "type": "react",
  "prompt": "...",
  "tools": []
}
```

### Flows

#### GET /api/v1/admin/flows

Получить список всех flows.

#### GET /api/v1/admin/flows/{flow_id}

Получить конфигурацию flow.

#### POST /api/v1/admin/flows

Создать новый flow.

## Flows API

Взаимодействие с агентами через flows.

### POST /api/v1/flows/{flow_id}/message

Отправить сообщение в flow.

**Тело запроса**:
```json
{
  "message": "Привет! Посчитай 2+2",
  "user_id": "user_123",
  "session_id": "optional_session_id",
  "files": [],
  "history": []
}
```

**Ответ**:
```json
{
  "task_id": "task_abc123",
  "session_id": "api:user_123:my_flow:xxx",
  "status": "pending",
  "message": "Сообщение принято в обработку"
}
```

### GET /api/v1/flows/{flow_id}/tasks/{task_id}

Получить статус и результат задачи (polling).

**Ответ** (в процессе):
```json
{
  "task_id": "task_abc123",
  "status": "processing",
  "session_id": "api:user_123:my_flow:xxx",
  "result": null
}
```

**Ответ** (завершено):
```json
{
  "task_id": "task_abc123",
  "status": "completed",
  "session_id": "api:user_123:my_flow:xxx",
  "result": {
    "messages": [
      {
        "role": "assistant",
        "content": "2+2 = 4"
      }
    ]
  },
  "completed_at": "2025-10-06T10:30:00Z"
}
```

### GET /api/v1/flows/{flow_id}/sessions/{session_id}

Получить историю сессии.

**Ответ**:
```json
{
  "session_id": "api:user_123:my_flow:xxx",
  "messages": [
    {"role": "user", "content": "Привет!"},
    {"role": "assistant", "content": "Здравствуйте!"}
  ]
}
```

### DELETE /api/v1/flows/{flow_id}/sessions/{session_id}

Удалить сессию и её историю.

## Auth API

Авторизация через внешние провайдеры.

### GET /auth/{provider}/login

Начать OAuth авторизацию.

**Параметры**:
- `provider` - провайдер (yandex)
- `redirect_uri` - URL для редиректа после авторизации

### GET /auth/{provider}/callback

Callback для OAuth.

### GET /auth/me

Получить информацию о текущем пользователе.

**Ответ**:
```json
{
  "user_id": "user_123",
  "email": "user@example.com",
  "name": "Иван Иванов",
  "companies": ["company_1", "company_2"],
  "active_company_id": "company_1"
}
```

### POST /auth/logout

Выход из системы.

## Files API

Работа с файлами.

### GET /api/v1/files/{file_id}

Скачать файл.

**Параметры**:
- `file_id` - ID файла

### POST /api/v1/files/upload

Загрузить файл (через multipart/form-data).

## FASHN API

Виртуальная примерка одежды.

### POST /api/v1/fashn/try-on

Выполнить виртуальную примерку.

**Тело запроса**:
```json
{
  "model_image_url": "https://...",
  "product_image_url": "https://...",
  "item_kind": "bag",
  "model_height_cm": 170,
  "product_width_mm": 300
}
```

## Telegram API

Webhooks для Telegram ботов.

### POST /api/v1/telegram/webhook/{flow_id}

Webhook для получения обновлений от Telegram.

## Health Check

### GET /health

Проверка состояния сервиса.

**Ответ**:
```json
{
  "status": "healthy",
  "database": "connected",
  "checkpointer": "initialized"
}
```

## Коды ошибок

- `400` - Неверный запрос
- `401` - Не авторизован
- `403` - Доступ запрещен
- `404` - Не найдено
- `429` - Превышен лимит запросов
- `500` - Внутренняя ошибка сервера

## Примеры использования

### Python

```python
import httpx

# Отправить сообщение
response = httpx.post(
    "http://localhost:8001/api/v1/flows/my_flow/message",
    json={
        "message": "Привет!",
        "user_id": "user_123"
    }
)
task_id = response.json()["task_id"]

# Получить результат
import time
while True:
    result = httpx.get(
        f"http://localhost:8001/api/v1/flows/my_flow/tasks/{task_id}"
    ).json()
    
    if result["status"] == "completed":
        print(result["result"])
        break
    
    time.sleep(1)
```

### cURL

```bash
# Отправить сообщение
curl -X POST http://localhost:8001/api/v1/flows/my_flow/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет!",
    "user_id": "user_123"
  }'

# Получить результат
curl http://localhost:8001/api/v1/flows/my_flow/tasks/task_abc123
```

## Frontend API

Дополнительные endpoints для веб-интерфейса:

- `GET /` - главная страница
- `GET /dashboard` - дашборд
- `GET /builder` - конструктор агентов
- `GET /chat` - чат интерфейс
- `GET /billing` - биллинг

Подробнее: [frontend.md](frontend.md)

