# WhatsApp Business API Интеграция

Полная интеграция WhatsApp Business Cloud API в платформу Agent Lab с обратной совместимостью с Telegram.

## Документация

1. **[План интеграции](integration_plan.md)** - детальная архитектура и технический план
2. **[Настройка](setup.md)** - пошаговое руководство по настройке
3. **[Использование](usage.md)** - работа с WhatsApp в агентах

## Быстрый старт

### 1. Получите WhatsApp Business API доступ

- Перейдите на https://developers.facebook.com
- Создайте приложение типа "Business"
- Добавьте продукт "WhatsApp"
- Получите credentials

### 2. Создайте переменные в платформе

```bash
# Access Token (обязательно is_secret!)
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_access_token",
    "value": "EAAxxxx...",
    "is_secret": true,
    "scope": "company"
  }'

# Phone Number ID
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_phone_number_id",
    "value": "111111111111111",
    "scope": "company"
  }'

# Verify Token
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_verify_token",
    "value": "ваш_случайный_токен",
    "is_secret": true,
    "scope": "company"
  }'
```

### 3. Добавьте WhatsApp к flow

```python
flow_config = FlowConfig(
    name="Support Bot",
    entry_point_agent="app.agents.support.SupportAgent",
    platforms={
        "whatsapp": {
            "phone_number_id": "@var:whatsapp_phone_number_id",
            "access_token": "@var:whatsapp_access_token",
            "verify_token": "@var:whatsapp_verify_token",
            "display_name": "Support Bot"
        }
    }
)
```

### 4. Зарегистрируйте flow

```bash
curl -X POST "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/register/my_flow_id"
```

### 5. Настройте webhook в Meta for Developers

В разделе WhatsApp → Configuration → Webhook:

**Callback URL:**
```
https://your-company.agents-lab.ru/api/v1/webhook/whatsapp/company:xxx:flow:my_flow_id
```

**Verify Token:** Ваш verify_token из переменных

## Возможности

### Полная совместимость с Telegram

WhatsApp поддерживает все возможности Telegram:

✅ **Команды**: `/start`, `/help`, `/clear`  
✅ **Форматирование**: *bold*, _italic_, ~strikethrough~  
✅ **Кнопки**: до 3 reply buttons или списки до 10 элементов  
✅ **Медиа**: изображения, видео, аудио, документы  
✅ **Голосовые сообщения**: с автоматическим распознаванием  
✅ **Локация**: GPS координаты  
✅ **Контакты**: обмен контактной информацией  

### Дополнительные возможности

- Template messages для re-engagement
- Статусы доставки (sent, delivered, read)
- Interactive messages (кнопки и списки)
- Conversation windows tracking

## Тестирование

Канал включает 80+ тестов для WhatsApp интеграции:

```bash
# Запуск всех тестов WhatsApp
uv run pytest tests/interfaces/whatsapp/ -v

# Unit тесты интерфейса
uv run pytest tests/interfaces/whatsapp/test_whatsapp_interface.py -v

# Тесты webhook endpoints
uv run pytest tests/interfaces/whatsapp/test_whatsapp_webhooks.py -v

# Интеграционные тесты
uv run pytest tests/interfaces/whatsapp/test_whatsapp_integration.py -v
```

**Результат:** 80 passed, 1 skipped

## Архитектура

```
┌──────────────┐                    ┌─────────────┐
│ WhatsApp User│                    │ Agent Lab   │
└──────┬───────┘                    └──────┬──────┘
       │                                   │
       │ 1. Send message                   │
       ▼                                   │
┌──────────────┐                          │
│WhatsApp Cloud│                          │
│     API      │                          │
└──────┬───────┘                          │
       │                                   │
       │ 2. Webhook POST                   │
       │ /api/v1/webhook/whatsapp/{flow}   │
       └───────────────────────────────────►
                                           │
                                           │ 3. Process
                                           ▼
                                    ┌─────────────┐
                                    │TaskProcessor│
                                    └──────┬──────┘
                                           │
                                           │ 4. Response
                                           ▼
                                    ┌──────────────┐
                                    │  WhatsApp    │
                                    │  Interface   │
                                    └──────┬───────┘
                                           │
                                           │ 5. Send via API
                                           ▼
┌──────────────┐                          │
│WhatsApp Cloud│ ◄────────────────────────┘
│     API      │
└──────┬───────┘
       │
       │ 6. Deliver
       ▼
┌──────────────┐
│ WhatsApp User│
└──────────────┘
```

## Файлы интеграции

**Бэкенд:**
- `app/interfaces/whatsapp_interface.py` - WhatsApp интерфейс (874 строки)
- `app/api/v1/whatsapp.py` - Webhook endpoints (318 строк)
- `app/core/config.py` - WhatsAppConfig
- `app/middleware/auth.py` - WhatsApp context
- `app/interfaces/factory.py` - Регистрация в фабрике

**Фронтенд:**
- `app/frontend/modules/bots/templates/bot_details.html` - UI для WhatsApp полей
- `app/frontend/shared/static/bots/js/bots.js` - Логика добавления WhatsApp
- `app/frontend/shared/static/bots/css/bots.css` - Стили для WhatsApp badge

**Примеры:**
- `app/flows/weather_flow.py` - Пример конфигурации с WhatsApp

**Тесты:**
- `tests/interfaces/whatsapp/test_whatsapp_interface.py` - 45 unit тестов
- `tests/interfaces/whatsapp/test_whatsapp_webhooks.py` - 18 тестов endpoints
- `tests/interfaces/whatsapp/test_whatsapp_integration.py` - 18 интеграционных

**Документация:**
- `docs/integrations/whatsapp/integration_plan.md` - Технический план
- `docs/integrations/whatsapp/setup.md` - Руководство по настройке
- `docs/integrations/whatsapp/usage.md` - Использование в агентах

## Ограничения и Best Practices

### 24-часовое окно разговора

Можно отправлять free-form сообщения только в течение 24 часов после последнего сообщения пользователя.

**Решение:** Используйте template messages для re-engagement.

### Rate Limits

WhatsApp API имеет лимиты по количеству сообщений в день.

**Решение:** Мониторьте использование и реализуйте retry logic.

### Стоимость

- User-initiated: ~$0.01-0.02 за conversation
- Business-initiated: ~$0.02-0.05 за conversation  
- Первые 1000 conversations/месяц бесплатно

## Поддержка

При возникновении проблем:

1. Проверьте [Troubleshooting](setup.md#troubleshooting) в setup.md
2. Посмотрите логи: ищите префикс `📱 WhatsApp`
3. Проверьте что все credentials правильные
4. Убедитесь что webhook настроен в Meta for Developers

## Лицензия

Интеграция является частью платформы Agent Lab.

