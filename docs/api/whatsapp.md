# whatsapp

### <span class="http-method get">GET</span> `/api/v1/webhook/whatsapp/{flow_key}`

**Whatsapp Webhook Verify**

Верификация webhook для WhatsApp Business API.

WhatsApp отправляет GET запрос с параметрами для верификации.
Необходимо вернуть hub.challenge если verify_token совпадает.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `flow_key` | string |  |

#### Query параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `hub.mode` | string | Да |  |
| `hub.verify_token` | string | Да |  |
| `hub.challenge` | string | Да |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method post">POST</span> `/api/v1/webhook/whatsapp/{flow_key}`

**Whatsapp Webhook**

Обработка webhook от WhatsApp Business API.
Получает входящие сообщения, статусы доставки и другие события.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `flow_key` | string |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method post">POST</span> `/api/v1/admin/whatsapp/register/{flow_id}`

**Register Whatsapp Flow**

Регистрирует WhatsApp для flow.

Проверяет credentials и возвращает информацию для настройки webhook.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `flow_id` | string |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method post">POST</span> `/api/v1/admin/whatsapp/send_template/{flow_id}`

**Send Template Message**

Отправляет template сообщение для инициации диалога.

Template messages требуют предварительного одобрения в Meta.
Используются для инициации разговора вне 24-часового окна.

Args:
    flow_id: ID flow
    phone_number: Номер получателя
    template_name: Название template
    language_code: Код языка (ru, en, etc.)
    parameters: Параметры для подстановки в template

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `flow_id` | string |  |

#### Query параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `phone_number` | string | Да |  |
| `template_name` | string | Да |  |
| `language_code` | string | Нет |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---

### <span class="http-method get">GET</span> `/api/v1/admin/whatsapp/phone_info/{flow_id}`

**Get Phone Info**

Получает информацию о телефонном номере WhatsApp Business.

Полезно для проверки статуса и лимитов.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| `flow_id` | string |  |

#### Ответы

| Код | Описание |
|-----|----------|
| `200` | Successful Response |
| `422` | Validation Error |

---
