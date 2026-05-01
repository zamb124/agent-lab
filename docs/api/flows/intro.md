A2A (Agent-to-Agent) API - протокол для взаимодействия с ИИ-агентами в платформе Humanitec.

## Обзор

A2A API реализует спецификацию [Google A2A Protocol](https://ai.google.dev/a2a) для управления агентами, отправки сообщений и работы с задачами. API поддерживает как синхронные, так и потоковые (streaming) запросы через JSON-RPC 2.0.

## Базовый URL

```
https://humanitec.ru/flows/a2a/{flow_id}
```

Где `{flow_id}` - уникальный идентификатор агента в платформе.

## Аутентификация

Все запросы требуют аутентификации через JWT токен:

- **Bearer токен** в заголовке `Authorization: Bearer {token}`
- **API ключ** в заголовке `X-API-Key: {key}`
- **Embed Session токен** для встроенных виджетов

Токены содержат информацию о компании, пользователе и правах доступа.

## Agent Card

Agent Card - это метаданные агента, описывающие его возможности, capabilities и настройки.

### Получение Agent Card

```bash
GET /flows/a2a/{flow_id}
GET /flows/a2a/{flow_id}/.well-known/agent-card.json
```

**Query параметры:**
- `v` - версия агента (опционально)

**Пример:**
```bash
curl -H "Authorization: Bearer {token}" \
  https://humanitec.ru/flows/a2a/my-agent
```

**Ответ:**
```json
{
  "agentId": "my-agent",
  "displayName": "My AI Assistant",
  "description": "Helpful assistant for various tasks",
  "capabilities": [
    "streaming",
    "pushNotifications"
  ],
  "skills": [...]
}
```

## JSON-RPC методы

Все методы вызываются через POST запрос на `/{flow_id}` с JSON-RPC 2.0 телом:

```bash
POST /flows/a2a/{flow_id}
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "content": {
        "parts": [
          {"text": "Hello, agent!"}
        ]
      }
    }
  }
}
```

### message/send

Отправляет сообщение агенту и получает полный ответ.

**Параметры:**
- `message` - объект сообщения с role и content
- `sessionId` - идентификатор сессии (опционально)
- `metadata` - дополнительные метаданные

**Пример:**
```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "What is the capital of France?"}
          ]
        }
      }
    }
  }'
```

### message/stream

Отправляет сообщение и получает потоковый ответ через Server-Sent Events (SSE).

**Параметры:** те же, что и `message/send`

**Пример:**
```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Tell me a story"}
          ]
        }
      }
    }
  }'
```

**Ответ:** SSE события с фрагментами ответа в реальном времени.

### tasks/get

Получает информацию о задаче по её идентификатору.

**Параметры:**
- `taskId` - идентификатор задачи

**Пример:**
```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tasks/get",
    "params": {
      "taskId": "task-123"
    }
  }'
```

### tasks/cancel

Отменяет выполняющуюся задачу.

**Параметры:**
- `taskId` - идентификатор задачи

**Пример:**
```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tasks/cancel",
    "params": {
      "taskId": "task-123"
    }
  }'
```

### tasks/resubscribe

Переподписывается на потоковый ответ задачи через SSE.

**Параметры:**
- `taskId` - идентификатор задачи

### tasks/pushNotificationConfig/*

Управление конфигурацией push-уведомлений для задач:

- `tasks/pushNotificationConfig/get` - получить конфигурацию
- `tasks/pushNotificationConfig/set` - установить конфигурацию
- `tasks/pushNotificationConfig/delete` - удалить конфигурацию
- `tasks/pushNotificationConfig/list` - список всех конфигураций

### agent/getAuthenticatedExtendedCard

Получает расширенную Agent Card с аутентифицированными данными пользователя.

## Skills

Skills - это специализированные режимы работы агента для конкретных задач.

### Список skills

```bash
GET /flows/a2a/{flow_id}/skills
```

### Получение skill

```bash
GET /flows/a2a/{flow_id}/skills/{branch_id}
```

### Tools в skill

```bash
GET /flows/a2a/{flow_id}/skills/{branch_id}/tools
```

### Создание skill

```bash
POST /flows/a2a/{flow_id}/skills
Content-Type: application/json

{
  "branch_id": "my-skill",
  "name": "My Skill",
  "description": "Skill description",
  ...
}
```

### Обновление skill

```bash
PUT /flows/a2a/{flow_id}/skills/{branch_id}
Content-Type: application/json

{
  "name": "Updated Skill",
  ...
}
```

### Удаление skill

```bash
DELETE /flows/a2a/{flow_id}/skills/{branch_id}
```

### Schema для создания skill

```bash
GET /flows/a2a/{flow_id}/schema
```

Возвращает JSON Schema для создания skill в формате ISchema.

## Embed Integration

Для встроенных виджетов используется специальный endpoint с embed токеном:

```bash
POST /flows/a2a/embed/{embed_id}
```

Embed токены ограничивают доступ к конкретному flow, skill и origin.

## Версионирование

Агенты поддерживают версионирование. Версию можно указать:

- **Query параметр:** `?v=20241226120000000000`
- **В metadata:** `{"metadata": {"version": "20241226120000000000"}}`

Приоритет у query параметра.

## Ошибки

JSON-RPC ошибки возвращаются в стандартном формате:

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "error": {
    "code": -32000,
    "message": "Error description"
  }
}
```

**Коды ошибок:**
- `-32700` - Parse error (невалидный JSON)
- `-32600` - Invalid Request
- `-32601` - Method not found
- `-32602` - Invalid params
- `-32000` - Server error / Custom error

## Примеры использования

### Простой запрос

```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Hello!"}
          ]
        }
      }
    }
  }'
```

### Потоковый запрос

```bash
curl -N -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Tell me a story"}
          ]
        }
      }
    }
  }'
```

### Работа с конкретным skill

```bash
curl -X POST https://humanitec.ru/flows/a2a/my-agent \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Help me with math"}
          ]
        }
      },
      "metadata": {
        "skill": "math-helper"
      }
    }
  }'
```

## Дополнительные ресурсы

- [A2A Protocol Specification](https://ai.google.dev/a2a)
- [Agent Card Format](https://ai.google.dev/a2a/docs/agent-card)
- [Streaming Responses](https://ai.google.dev/a2a/docs/streaming)
