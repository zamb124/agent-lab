# Настройка WhatsApp интеграции

## Быстрый старт

WhatsApp интеграция позволяет вашим агентам работать через WhatsApp Business Cloud API с полной поддержкой всех возможностей Telegram: команды, кнопки, медиа (видео, аудио, изображения, документы).

## Получение WhatsApp Business API доступа

### Шаг 1: Facebook Business Manager

1. Создайте аккаунт: https://business.facebook.com
2. Создайте бизнес в Business Manager
3. Пройдите верификацию бизнеса (требуется для production)

### Шаг 2: Meta for Developers

1. Перейдите на https://developers.facebook.com
2. Создайте новое приложение (App):
   - Тип: **Business**
   - Название: например "My Company Bot"

3. Добавьте продукт **WhatsApp**:
   - Dashboard → Add Product → WhatsApp

### Шаг 3: Получение credentials

#### 3.1 Access Token

В разделе `WhatsApp > API Setup`:

**Для тестирования (24 часа):**
```
Temporary access token: EAAxxxx...
```

**Для production (долгосрочный):**
1. Создайте System User в Business Settings
2. Назначьте роли: Admin
3. Сгенерируйте токен для System User
4. Выберите permissions: `whatsapp_business_messaging`, `whatsapp_business_management`

#### 3.2 Phone Number ID

В разделе `WhatsApp > API Setup`:
```
Phone number ID: 111111111111111
```

#### 3.3 Business Account ID

В разделе `WhatsApp > API Setup`:
```
WhatsApp Business Account ID: 123456789
```

#### 3.4 Verify Token

Создайте собственный случайный токен для верификации webhook:
```bash
# Генерация secure token
openssl rand -base64 32
```

Результат (пример): `my_secure_verify_token_abc123xyz`

## Создание переменных в платформе

### Через API

```bash
# 1. Access Token (обязательно is_secret: true!)
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_access_token",
    "value": "EAAxxxx...",
    "is_secret": true,
    "scope": "company"
  }'

# 2. Phone Number ID
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_phone_number_id",
    "value": "111111111111111",
    "scope": "company"
  }'

# 3. Verify Token (is_secret: true!)
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_verify_token",
    "value": "my_secure_verify_token_abc123xyz",
    "is_secret": true,
    "scope": "company"
  }'

# 4. Business Account ID
curl -X POST "https://your-company.agents-lab.ru/api/v1/variables" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "whatsapp_business_account_id",
    "value": "123456789",
    "scope": "company"
  }'
```

### Через Frontend

1. Перейдите в раздел **Variables**
2. Нажмите **Add Variable**
3. Заполните поля:
   - Key: `whatsapp_access_token`
   - Value: ваш токен
   - Is Secret: ✅ (обязательно для токенов!)
   - Scope: `company`

## Настройка FlowConfig

### Пример конфигурации

```python
from app.models import FlowConfig

my_flow = FlowConfig(
    name="Support Bot",
    entry_point_agent="app.agents.support.SupportAgent",
    
    platforms={
        "whatsapp": {
            # Обязательные параметры
            "phone_number_id": "@var:whatsapp_phone_number_id",
            "access_token": "@var:whatsapp_access_token",
            "verify_token": "@var:whatsapp_verify_token",
            
            # Опциональные параметры
            "business_account_id": "@var:whatsapp_business_account_id",
            "display_name": "Support Bot",
            
            # API параметры (можно не указывать, есть значения по умолчанию)
            "graph_api_version": "v18.0",
            "graph_api_url": "https://graph.facebook.com"
        }
    }
)
```

### Минимальная конфигурация

```python
platforms={
    "whatsapp": {
        "phone_number_id": "@var:whatsapp_phone_number_id",
        "access_token": "@var:whatsapp_access_token",
        "verify_token": "@var:whatsapp_verify_token"
    }
}
```

## Регистрация flow в WhatsApp

### 1. Регистрация через API

```bash
curl -X POST "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/register/my_flow_id"
```

Ответ:
```json
{
  "success": true,
  "flow_id": "my_flow_id",
  "result": {
    "platform": "whatsapp",
    "mode": "webhook",
    "phone_number": "+1234567890",
    "webhook_url": "https://your-company.agents-lab.ru/api/v1/webhook/whatsapp/company:xxx:flow:my_flow_id",
    "note": "Configure webhook manually in Meta for Developers"
  }
}
```

Сохраните `webhook_url` - он понадобится в следующем шаге!

### 2. Настройка webhook в Meta for Developers

1. Откройте ваше приложение в Meta for Developers
2. Перейдите в `WhatsApp > Configuration`
3. В разделе **Webhook**:

   **Callback URL:**
   ```
   https://your-company.agents-lab.ru/api/v1/webhook/whatsapp/company:xxx:flow:my_flow_id
   ```

   **Verify Token:**
   ```
   my_secure_verify_token_abc123xyz
   ```
   (тот же токен что в переменной `whatsapp_verify_token`)

4. Нажмите **Verify and Save**

5. В **Webhook Fields** включите:
   - ✅ **messages** (входящие сообщения)
   - ✅ **message_template_status** (статусы template)

### 3. Проверка регистрации

```bash
curl "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/phone_info/my_flow_id"
```

Ответ должен содержать информацию о номере:
```json
{
  "success": true,
  "phone_data": {
    "verified_name": "My Company",
    "display_phone_number": "+1234567890",
    "quality_rating": "GREEN",
    "id": "111111111111111"
  }
}
```

## Локальная разработка с ngrok

Для локальной разработки используйте ngrok:

### 1. Запуск ngrok

```bash
ngrok http 8001
```

Получите публичный URL:
```
Forwarding: https://abc123.ngrok.io -> http://localhost:8001
```

### 2. Настройка webhook

Используйте ngrok URL для webhook:
```
https://abc123.ngrok.io/api/v1/webhook/whatsapp/company:xxx:flow:my_flow_id
```

### 3. Тестовые номера

В Meta for Developers можно добавить до 5 тестовых номеров бесплатно:
1. `WhatsApp > API Setup > To`
2. Нажмите **Add phone number**
3. Введите номер для тестирования
4. Подтвердите через SMS код

## Возможности WhatsApp интеграции

### Поддерживаемые типы сообщений

#### Входящие (от пользователя):
- ✅ Текст
- ✅ Изображения (JPEG, PNG)
- ✅ Видео (MP4, 3GPP)
- ✅ Аудио (AAC, MP3, AMR, OGG)
- ✅ Голосовые сообщения
- ✅ Документы (PDF, DOC, XLS, PPT)
- ✅ Локация (GPS координаты)
- ✅ Контакты
- ✅ Стикеры
- ✅ Кнопки (interactive button reply)
- ✅ Списки (interactive list reply)

#### Исходящие (от агента):
- ✅ Текст с форматированием (*bold*, _italic_, ~strikethrough~)
- ✅ Интерактивные кнопки (до 3)
- ✅ Интерактивные списки (4-10 опций)
- ✅ Аудио сообщения
- ✅ Изображения с caption
- ✅ Видео с caption
- ✅ Документы
- ✅ Template messages (для re-engagement)

### Команды

WhatsApp поддерживает те же команды что и Telegram:
- `/start` - начать диалог
- `/help` - показать справку
- `/clear` - очистить контекст

Команды обрабатываются автоматически через `BaseInterface.process_command()`.

### Форматирование текста

WhatsApp поддерживает Markdown:
```
*жирный текст*
_курсив_
~зачеркнутый~
```monospace```
```

Агенты могут использовать обычный Markdown - он автоматически конвертируется в WhatsApp формат.

### Кнопки

Агенты могут отправлять кнопки через metadata:

```python
message = Message(
    content="Выберите действие:",
    metadata={
        "phone_number": "1234567890",
        "buttons": [
            {"id": "btn_1", "text": "Узнать погоду"},
            {"id": "btn_2", "text": "Помощь"},
            {"id": "btn_3", "text": "Настройки"}
        ]
    }
)
```

**Ограничения:**
- До 3 кнопок → Reply Buttons
- 4-10 кнопок → List Message
- Более 10 → обрезается до 10

### Медиафайлы

#### Размеры и форматы

| Тип | Форматы | Максимум |
|-----|---------|----------|
| Изображение | JPEG, PNG | 5 MB |
| Видео | MP4, 3GPP | 16 MB |
| Аудио | AAC, MP3, AMR, OGG | 16 MB |
| Документ | PDF, DOC, XLS, PPT | 100 MB |

#### Обработка медиа

Все медиафайлы автоматически:
- Скачиваются от WhatsApp API
- Загружаются в S3
- Обрабатываются через `FileProcessor` и `AudioProcessor`
- Аудио распознается через Cloud Voice API
- Добавляются в контекст агента

## Template Messages

Template messages используются для:
- Инициации диалога вне 24-часового окна
- Отправки уведомлений
- Маркетинговых рассылок

### Создание template

1. В Meta for Developers → `WhatsApp > Message Templates`
2. Создайте template (требуется одобрение)
3. Пример template:

```
Name: greeting
Category: UTILITY
Language: Russian

Body:
Привет {{1}}! Я бот поддержки. Чем могу помочь?
```

### Отправка template

```bash
curl -X POST "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/send_template/my_flow_id" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "1234567890",
    "template_name": "greeting",
    "language_code": "ru",
    "parameters": ["Иван"]
  }'
```

## Ограничения и Best Practices

### 24-часовое окно разговора

**Правило:** Можно отправлять free-form сообщения только в течение 24 часов после последнего сообщения пользователя.

**Решения:**
- Используйте template messages для re-engagement
- Настройте напоминания пользователям
- Мониторьте активные conversation windows

### Rate Limits

WhatsApp API имеет лимиты:
- Tier 1: 1,000 unique customers/день
- Tier 2: 10,000 unique customers/день
- Tier 3: 100,000 unique customers/день
- Tier 4: Unlimited

**Best practices:**
- Реализуйте retry logic с exponential backoff
- Мониторьте rate limit headers
- Используйте очередь сообщений

### Стоимость

WhatsApp использует conversation-based pricing:
- **User-initiated:** ~$0.01-0.02 за conversation
- **Business-initiated:** ~$0.02-0.05 за conversation
- **Первые 1000 conversations/месяц:** бесплатно

Conversation = 24-часовое окно диалога.

## Мониторинг

### Логи

WhatsApp события логируются с префиксами:
```
📱 WhatsApp webhook для flow_id
✅ WhatsApp сообщение отправлено: msg_id → phone
❌ WhatsApp API ошибка: code - message
📬 WhatsApp статус: msg_id → delivered
```

### Статусы доставки

WhatsApp автоматически отправляет webhook'и со статусами:
- `sent` - отправлено на сервер WhatsApp
- `delivered` - доставлено на устройство
- `read` - прочитано пользователем
- `failed` - ошибка доставки

Все статусы логируются автоматически.

### Проверка health

```bash
# Проверка номера и лимитов
curl "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/phone_info/my_flow_id"
```

## Troubleshooting

### Webhook не получает сообщения

**Проверки:**
1. Webhook URL правильный в Meta for Developers
2. Verify token совпадает
3. Webhook fields включены (messages)
4. Сервер доступен публично (проверьте через curl)
5. SSL сертификат валиден (WhatsApp требует HTTPS для production)

**Локальная отладка:**
```bash
# Проверка webhook вручную
curl -X GET "http://localhost:8001/api/v1/webhook/whatsapp/company:xxx:flow:my_flow_id?hub.mode=subscribe&hub.verify_token=my_verify_token&hub.challenge=test"

# Должен вернуть: test
```

### Сообщения не отправляются

**Проверки:**
1. Access token валиден (не истек)
2. Phone number ID правильный
3. Номер получателя в правильном формате (без +, с кодом страны)
4. В пределах 24-часового окна (или используйте template)
5. Лимиты rate limit не превышены

**Отладка:**
```bash
# Проверка токена
curl -X GET "https://graph.facebook.com/v18.0/{phone_number_id}" \
  -H "Authorization: Bearer {access_token}"
```

### Ошибки доступа

**Ошибка 403:**
- Неверный verify_token
- Неверная подпись webhook (если используется)

**Ошибка 401:**
- Истек access_token
- Неверный access_token

**Ошибка 404:**
- Неверный phone_number_id
- Flow не найден

## Дополнительная информация

### Полезные ссылки

- [WhatsApp Business Platform](https://developers.facebook.com/docs/whatsapp)
- [Cloud API Reference](https://developers.facebook.com/docs/whatsapp/cloud-api/reference)
- [Webhook Reference](https://developers.facebook.com/docs/whatsapp/webhooks)
- [Message Templates](https://developers.facebook.com/docs/whatsapp/message-templates)
- [Error Codes](https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes)

### Следующие шаги

1. [Использование WhatsApp в агентах](usage.md)
2. [Работа с template messages](templates.md)
3. [Обработка медиафайлов](media.md)

