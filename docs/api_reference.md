# API Reference

Полная справка по REST API Agent Lab.

## Интерактивная документация

Agent Lab предоставляет полноценную интерактивную документацию API на базе OpenAPI/Swagger.

**Перейти к интерактивной документации:**

- [Swagger UI →](/api/docs){:target="_blank" .md-button .md-button--primary} - полная интерактивная документация с возможностью тестирования
- [ReDoc →](/api/redoc){:target="_blank" .md-button} - альтернативное представление (более читаемое)
- [OpenAPI JSON →](/api/openapi.json){:target="_blank" .md-button} - спецификация в формате JSON

> **Совет**: Используйте Swagger UI для тестирования API прямо в браузере.

## Базовая информация

**Base URL**: `https://your-domain.com`

**Аутентификация**: Bearer Token

```bash
Authorization: Bearer YOUR_API_TOKEN
```

## Основные endpoints

### Flows (Боты)

**POST /api/v1/flow/{flow_id}/invoke**
Отправить сообщение боту

**POST /api/v1/flow/{flow_id}/stream**
Отправить сообщение с streaming ответом

### Webhooks

**POST /api/v1/webhook/telegram/{flow_key}**
Webhook для Telegram

**POST /api/v1/webhook/whatsapp/{flow_key}**
Webhook для WhatsApp

### Files

**POST /api/v1/files/upload**
Загрузить файл

**GET /api/v1/files/download/{file_id}**
Скачать файл

### Variables

**GET /api/v1/variables**
Получить список переменных

**POST /api/v1/variables**
Создать переменную

**PUT /api/v1/variables/{key}**
Обновить переменную

**DELETE /api/v1/variables/{key}**
Удалить переменную

### Payments

**POST /api/v1/payments/webhook/yoomoney**
Webhook для YooMoney

### Admin

**GET /api/v1/admin/companies**
Список компаний (только admin)

**POST /api/v1/admin/create-my-company**
Создать свою компанию

## Примеры использования

### Отправка сообщения боту

```bash
curl -X POST https://your-domain.com/api/v1/flow/{flow_id}/invoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет!",
    "user_id": "user123",
    "session_id": "session456"
  }'
```

### Загрузка файла

```bash
curl -X POST https://your-domain.com/api/v1/files/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/file.pdf"
```

### Создание переменной

```bash
curl -X POST https://your-domain.com/api/v1/variables \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "MY_API_KEY",
    "value": "secret_value",
    "is_secret": true
  }'
```

## Коды ответов

- **200 OK** - Успешный запрос
- **201 Created** - Ресурс создан
- **400 Bad Request** - Неверные параметры
- **401 Unauthorized** - Требуется аутентификация
- **403 Forbidden** - Доступ запрещен
- **404 Not Found** - Ресурс не найден
- **500 Internal Server Error** - Ошибка сервера

## Rate Limiting

По умолчанию:
- **100 запросов в минуту** для обычных пользователей
- **1000 запросов в минуту** для admin

При превышении лимита возвращается `429 Too Many Requests`.

