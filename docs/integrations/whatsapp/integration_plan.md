# План интеграции WhatsApp в Agents Lab

## Обзор архитектуры

### Текущая архитектура платформы

Платформа Agents Lab использует унифицированную архитектуру интерфейсов для подключения различных каналов коммуникации:

```
┌─────────────────┐
│  BaseInterface  │  ← Базовый класс для всех интерфейсов
└────────┬────────┘
         │
    ┌────┴────┬────────┬──────────┬─────────┐
    │         │        │          │         │
┌───▼───┐ ┌──▼──┐ ┌───▼────┐ ┌───▼────┐ ┌──▼──────┐
│Telegram│ │ API │ │ Web    │ │AmoCRM  │ │WhatsApp │ ← Новый
└────────┘ └─────┘ └────────┘ └────────┘ └─────────┘
```

### Ключевые компоненты

1. **BaseInterface** (`app/interfaces/base.py`)
   - Абстрактный базовый класс
   - Определяет унифицированный API для всех платформ
   - Методы: `handle_message()`, `send_message()`, `send_typing_notification()`

2. **Message** (`app/interfaces/base.py`)
   - Унифицированная модель сообщения
   - Поля: `user_id`, `session_id`, `content`, `flow_id`, `platform`, `metadata`, `files`

3. **InterfaceFactory** (`app/interfaces/factory.py`)
   - Фабрика для создания интерфейсов
   - Регистрация всех доступных платформ
   - Динамическое создание интерфейсов

4. **FlowConfig** (`app/models/core_models.py`)
   - Конфигурация flow с настройками платформ
   - `platforms: Dict[str, Dict[str, Any]]` - конфигурация для каждой платформы

## WhatsApp Cloud API

### Архитектура WhatsApp Business Platform

```
┌──────────────────┐                    ┌─────────────────┐
│  WhatsApp User   │                    │  Agents Lab     │
└────────┬─────────┘                    └────────┬────────┘
         │                                       │
         │  1. Sends message                     │
         ▼                                       │
┌─────────────────────┐                         │
│ WhatsApp Cloud API  │                         │
└──────────┬──────────┘                         │
           │                                     │
           │  2. Webhook POST                    │
           │  /api/v1/webhook/whatsapp/{flow_key}│
           └──────────────────────────────────►  │
                                                 │
                                                 │  3. Process & create task
                                                 ▼
                                          ┌──────────────┐
                                          │ TaskProcessor│
                                          └──────┬───────┘
                                                 │
                                                 │  4. Agent response
                                                 ▼
                                          ┌──────────────┐
                                          │  WhatsApp    │
                                          │  Interface   │
                                          └──────┬───────┘
                                                 │
                                                 │  5. Send message via API
                                                 ▼
┌─────────────────────┐                         │
│ WhatsApp Cloud API  │  ◄──────────────────────┘
└──────────┬──────────┘
           │
           │  6. Delivers message
           ▼
┌──────────────────┐
│  WhatsApp User   │
└──────────────────┘
```

### Webhook формат входящих сообщений

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "+11111111111",
          "phone_number_id": "111111111111111"
        },
        "contacts": [{
          "profile": {
            "name": "John Doe"
          },
          "wa_id": "9111111111111"
        }],
        "messages": [{
          "from": "9111111111111",
          "id": "wamid.HBgNNzExMTExMTExMTExMTExMRAgAQA=",
          "timestamp": "1699000000",
          "text": {
            "body": "Hello, world!"
          },
          "type": "text"
        }]
      },
      "field": "messages"
    }]
  }]
}
```

### API для отправки сообщений

```http
POST https://graph.facebook.com/v18.0/{phone_number_id}/messages
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "9111111111111",
  "type": "text",
  "text": {
    "preview_url": false,
    "body": "Your message here"
  }
}
```

## План реализации

### Этап 1: Создание WhatsAppInterface

**Файл:** `app/interfaces/whatsapp_interface.py`

**Функциональность:**

1. **Наследование от BaseInterface**
   - Реализация всех абстрактных методов
   - Использование единой архитектуры

2. **handle_message()** - обработка входящих webhook'ов
   ```python
   async def handle_message(self, raw_data: Dict[str, Any], flow_id: str) -> Optional[Message]:
       # Парсинг WhatsApp webhook payload
       # Извлечение: user_id (wa_id), text, message_id, profile_name
       # Создание унифицированного Message объекта
       # Обработка разных типов сообщений (text, image, audio, document, location)
   ```

3. **send_message()** - отправка сообщений через WhatsApp API
   ```python
   async def send_message(self, message: Message):
       # Получение phone_number_id из metadata
       # Получение access_token из конфигурации
       # Отправка через Graph API
       # Поддержка разных типов сообщений
   ```

4. **send_typing_notification()** - индикатор "печатает"
   ```python
   async def send_typing_notification(self, session_id: str, is_typing: bool):
       # Отправка typing indicator через WhatsApp API
       # mark_message_as_read для улучшения UX
   ```

5. **Дополнительные методы:**
   - `_extract_message_from_webhook()` - извлечение данных из webhook
   - `_process_single_file()` - обработка медиафайлов (изображения, документы)
   - `_process_single_audio_file()` - обработка голосовых сообщений
   - `_send_text_message()` - отправка текстовых сообщений
   - `_send_media_message()` - отправка медиа
   - `_download_whatsapp_media()` - скачивание медиафайлов от пользователя

6. **Регистрация и верификация webhook:**
   ```python
   @classmethod
   async def register(cls, flow_id: str, username: str, platform_config: Dict[str, Any]) -> Dict[str, Any]:
       # Проверка access_token
       # Валидация phone_number_id
       # Установка webhook URL
       # Настройка webhook subscriptions (messages, messaging_postbacks)
   ```

**Необходимые credentials:**
- `access_token` - токен доступа к WhatsApp Business API
- `phone_number_id` - ID телефонного номера в WhatsApp Business
- `whatsapp_business_account_id` - ID бизнес-аккаунта
- `verify_token` - токен для верификации webhook

### Этап 2: Создание API endpoint для webhook

**Файл:** `app/api/v1/whatsapp.py`

**Endpoints:**

1. **Webhook verification (GET)**
   ```python
   @router.get("/webhook/whatsapp/{flow_key:path}")
   async def whatsapp_webhook_verify(
       flow_key: str,
       hub_mode: str = Query(alias="hub.mode"),
       hub_verify_token: str = Query(alias="hub.verify_token"),
       hub_challenge: str = Query(alias="hub.challenge")
   ):
       # Проверка verify_token из flow config
       # Возврат challenge для валидации webhook
   ```

2. **Webhook handler (POST)**
   ```python
   @router.post("/webhook/whatsapp/{flow_key:path}")
   async def whatsapp_webhook(flow_key: str, request: Request):
       # Получение flow_config из БД
       # Создание WhatsAppInterface
       # Парсинг webhook payload
       # Обработка через handle_message()
       # Создание задачи через create_task()
   ```

3. **Admin endpoint для установки webhook**
   ```python
   @router.post("/admin/whatsapp/set_webhook/{flow_id}")
   async def set_whatsapp_webhook(flow_id: str, webhook_base_url: str):
       # Установка webhook URL в WhatsApp Business API
       # Настройка subscriptions
   ```

4. **Отправка сообщений (опционально)**
   ```python
   @router.post("/admin/whatsapp/send_template/{flow_id}")
   async def send_template_message(flow_id: str, request: TemplateMessageRequest):
       # Отправка template сообщений для инициации диалога
   ```

### Этап 3: Регистрация в InterfaceFactory

**Файл:** `app/interfaces/factory.py`

**Изменения:**

```python
class InterfaceFactory:
    PLATFORM_INTERFACES = {
        "telegram": TelegramInterface,
        "web": WebInterface,
        "api": APIInterface,
        "amocrm": AmoCRMInterface,
        "whatsapp": WhatsAppInterface,  # ← Добавить
    }

    async def create_interface(self, platform: str, config: Dict[str, Any]) -> Optional[BaseInterface]:
        # ...
        elif platform == "whatsapp":
            return await self._create_whatsapp_interface(config)
        # ...

    async def _create_whatsapp_interface(self, config: Dict[str, Any]) -> Optional[WhatsAppInterface]:
        """Создает WhatsApp интерфейс"""
        flow_id = config.get("flow_id")
        if not flow_id:
            logger.error("Нет flow_id для создания WhatsApp интерфейса")
            return None

        flow_config = await self.storage.get_flow_config(flow_id)
        if not flow_config:
            logger.error(f"Flow {flow_id} не найден")
            return None

        whatsapp_config = flow_config.platforms.get("whatsapp")
        if not whatsapp_config:
            logger.error(f"Flow {flow_id} не имеет whatsapp платформы")
            return None

        access_token = await WhatsAppInterface.get_access_token_for_flow(flow_id, whatsapp_config)
        if not access_token:
            logger.error(f"Не найден токен для flow {flow_id}")
            return None

        return WhatsAppInterface(access_token, whatsapp_config)
```

### Этап 4: Конфигурация

**Файл:** `app/core/config.py`

**Добавить WhatsAppConfig:**

```python
class WhatsAppConfig(BaseModel):
    """Конфигурация WhatsApp интеграции"""
    enabled: bool = True
    verify_token: Optional[str] = None  # Токен для верификации webhook
    graph_api_version: str = "v18.0"
    graph_api_url: str = "https://graph.facebook.com"

class Settings(BaseSettings):
    # ...
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
```

**Формат конфигурации в FlowConfig.platforms:**

```python
flow_config = FlowConfig(
    flow_id="my_flow",
    name="My Flow",
    entry_point_agent="my_agent",
    platforms={
        "whatsapp": {
            "enabled": True,
            "phone_number_id": "111111111111111",  # От WhatsApp Business
            "access_token": "@var:whatsapp_access_token",  # Ссылка на переменную
            "business_account_id": "123456789",
            "verify_token": "@var:whatsapp_verify_token",
            "display_name": "My Business Bot"
        }
    }
)
```

### Этап 5: Подключение роутера

**Файл:** `app/main.py`

**Изменения:**

```python
# Импорт
from app.api.v1 import webhooks, admin, telegram, whatsapp, ...  # ← Добавить whatsapp

# Подключение роутера
app.include_router(whatsapp.router, prefix="/api/v1", tags=["whatsapp"])  # ← Добавить
```

### Этап 6: Middleware поддержка

**Файл:** `app/middleware/auth.py`

**Добавить обработку WhatsApp webhooks:**

```python
async def _create_request_context(self, request: Request) -> Context:
    path = request.url.path
    
    # ...
    
    elif "/webhook/whatsapp/" in path:
        logger.info("📱 WhatsApp контекст")
        return await self._create_whatsapp_context(request, requested_company)
    
    # ...

async def _create_whatsapp_context(
    self, request: Request, requested_company: str
) -> Context:
    """Создает контекст для WhatsApp webhook"""
    # Извлекаем flow_id из URL
    flow_key = request.url.path.split("/webhook/whatsapp/")[1]
    
    if ":flow:" in flow_key:
        flow_id = flow_key.split(":flow:")[1]
    else:
        flow_id = flow_key

    # Загружаем flow config
    flow_config = await self.storage.get_flow_config(flow_id)
    if not flow_config:
        raise HTTPException(404, f"Flow {flow_id} не найден")

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        raise HTTPException(400, f"Flow {flow_id} не поддерживает WhatsApp")

    # Создаем контекст для системного пользователя
    return Context(
        user=User(
            user_id="whatsapp_system",
            username="WhatsApp System"
        ),
        platform="whatsapp",
        session_id=None,
        active_company=Company(
            company_id=requested_company,
            subdomain=requested_company,
            name=f"Company {requested_company}"
        )
    )
```

### Этап 7: Обработка медиафайлов

WhatsApp поддерживает различные типы медиа:

1. **Изображения** (image)
   - Форматы: JPEG, PNG
   - Максимум: 5MB

2. **Документы** (document)
   - Форматы: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX
   - Максимум: 100MB

3. **Аудио** (audio)
   - Форматы: AAC, MP3, AMR, OGG (opus)
   - Максимум: 16MB

4. **Видео** (video)
   - Форматы: MP4, 3GPP
   - Максимум: 16MB

5. **Локация** (location)
   - Координаты latitude/longitude

**Реализация в WhatsAppInterface:**

```python
async def _process_media_message(
    self, message_data: Dict[str, Any], user_id: str
) -> List[str]:
    """Обрабатывает медиа-сообщения из WhatsApp"""
    media_type = message_data.get("type")
    
    if media_type in ["image", "document", "audio", "video"]:
        media_data = message_data.get(media_type, {})
        media_id = media_data.get("id")
        
        # Скачиваем медиа через WhatsApp API
        media_url = await self._get_media_url(media_id)
        media_bytes = await self._download_media(media_url)
        
        # Обрабатываем через существующие процессоры
        if media_type == "audio":
            return await self.process_audio_files([{
                "content": media_bytes,
                "content_type": media_data.get("mime_type"),
                "name": f"whatsapp_audio_{media_id}"
            }], user_id)
        else:
            return await self.process_files([{
                "content": media_bytes,
                "content_type": media_data.get("mime_type"),
                "name": media_data.get("filename", f"whatsapp_{media_type}_{media_id}")
            }], user_id)
    
    return []
```

### Этап 8: Типы сообщений WhatsApp

**Входящие типы:**
- `text` - текстовое сообщение
- `image` - изображение
- `audio` - голосовое/аудио
- `video` - видео
- `document` - документ
- `location` - геолокация
- `contacts` - контакты
- `sticker` - стикер
- `button` - нажатие кнопки
- `interactive` - интерактивное сообщение (list, button reply)

**Исходящие типы:**
- `text` - текст с опциональной ссылкой preview
- `image` - изображение с caption
- `audio` - аудио
- `video` - видео с caption
- `document` - документ с caption
- `template` - template сообщение (для инициации диалога)
- `interactive` - интерактивные кнопки и списки
- `reaction` - эмодзи-реакция на сообщение

### Этап 9: Обработка статусов доставки

WhatsApp отправляет webhook'и со статусами:
- `sent` - отправлено на сервер WhatsApp
- `delivered` - доставлено на устройство получателя
- `read` - прочитано получателем
- `failed` - ошибка отправки

```python
async def handle_status_update(self, status_data: Dict[str, Any]):
    """Обрабатывает обновления статусов сообщений"""
    message_id = status_data.get("id")
    status = status_data.get("status")
    recipient_id = status_data.get("recipient_id")
    
    # Логирование или сохранение статуса
    logger.info(f"WhatsApp message {message_id} status: {status} for {recipient_id}")
    
    # Опционально: обновление статуса в БД для истории
```

## Настройка WhatsApp Business API

### Требования

1. **Facebook Business Manager аккаунт**
   - Создание через https://business.facebook.com

2. **WhatsApp Business аккаунт**
   - Связывается с Facebook Business Manager
   - Требуется верификация бизнеса

3. **App в Meta for Developers**
   - Создание через https://developers.facebook.com
   - Тип: Business
   - Добавить продукт: WhatsApp

4. **Phone Number**
   - Телефонный номер для WhatsApp Business
   - Не должен использоваться в обычном WhatsApp

### Получение credentials

1. **Access Token**
   ```
   Settings > WhatsApp > API Setup
   > Temporary access token (24 часа, для тестирования)
   > System User Access Token (долгосрочный, для продакшена)
   ```

2. **Phone Number ID**
   ```
   Settings > WhatsApp > API Setup
   > Phone number ID
   ```

3. **Business Account ID**
   ```
   Settings > WhatsApp > API Setup
   > WhatsApp Business Account ID
   ```

4. **Verify Token**
   ```
   Генерируется на вашей стороне
   Любая случайная строка для верификации webhook
   ```

### Настройка Webhook

1. В Meta for Developers:
   ```
   WhatsApp > Configuration > Webhook
   ```

2. Callback URL:
   ```
   https://your-domain.com/api/v1/webhook/whatsapp/{flow_key}
   ```

3. Verify Token:
   ```
   Ваш кастомный токен из конфигурации
   ```

4. Webhook Fields (подписки):
   - ✅ messages (входящие сообщения)
   - ✅ message_template_status (статусы template)
   - ✅ messaging_postbacks (кнопки и интерактив)

## Переменные и безопасность

### Хранение credentials

**Используем систему переменных платформы:**

```python
# В FlowConfig.platforms
platforms={
    "whatsapp": {
        "phone_number_id": "111111111111111",
        "access_token": "@var:whatsapp_access_token",  # Ссылка на переменную
        "verify_token": "@var:whatsapp_verify_token"
    }
}

# Создание переменной через API
POST /api/v1/variables
{
    "key": "whatsapp_access_token",
    "value": "EAAxxxx...",
    "is_secret": true,  # Шифрование в БД
    "scope": "company"  # Или "flow" для специфичных токенов
}
```

### Безопасность

1. **Верификация webhook подписи (опционально)**
   ```python
   import hmac
   import hashlib

   def verify_signature(payload: bytes, signature: str, app_secret: str) -> bool:
       expected_signature = hmac.new(
           app_secret.encode(),
           payload,
           hashlib.sha256
       ).hexdigest()
       return hmac.compare_digest(signature, expected_signature)
   ```

2. **Rate limiting**
   - Ограничение запросов от одного номера
   - Использование существующей системы биллинга

3. **Валидация webhook source**
   - Проверка IP адресов от Meta/WhatsApp
   - Использование verify_token

## Интеграция с существующей системой

### Биллинг

WhatsApp API имеет свою систему тарификации:
- **Conversation-based pricing** - оплата за 24-часовые окна диалога
- **Business-initiated conversations** - дороже
- **User-initiated conversations** - дешевле

```python
# В ToolReference или отдельная конфигурация
whatsapp_billing = {
    "cost_per_conversation": 0.05,  # $0.05 за conversation
    "free_tier": 1000,  # Первые 1000 бесплатно в месяц
    "tariff_limits": {
        "free": 100,
        "basic": 1000,
        "premium": -1  # Безлимит
    }
}
```

### Мультиязычность

WhatsApp поддерживает международные номера:

```python
# Определение языка по региону номера
def detect_language_from_phone(phone_number: str) -> str:
    country_code = phone_number[:2]
    language_map = {
        "7": "ru",   # Россия
        "1": "en",   # США
        "44": "en",  # Великобритания
        # ...
    }
    return language_map.get(country_code, "en")
```

### История диалогов

Использование существующей системы checkpointer:

```python
# Импорт истории при первом сообщении
async def _import_whatsapp_history(
    self,
    session_id: str,
    phone_number: str
):
    """Опционально: импорт истории из WhatsApp Business API"""
    # WhatsApp не предоставляет историю через API
    # Но можно сохранять локально для continuity
    pass
```

## Тестирование

### Локальная разработка

1. **Использование ngrok для webhook:**
   ```bash
   ngrok http 8001
   ```

2. **Настройка тестового номера:**
   - В Meta for Developers можно добавить до 5 тестовых номеров
   - Бесплатно для тестирования

3. **Test credentials:**
   ```python
   # В conf.json или .env
   WHATSAPP_TEST_PHONE_NUMBER_ID=xxx
   WHATSAPP_TEST_ACCESS_TOKEN=xxx
   WHATSAPP_TEST_VERIFY_TOKEN=test_token_123
   ```

### Unit тесты

```python
# tests/interfaces/test_whatsapp_interface.py
import pytest
from app.interfaces.whatsapp_interface import WhatsAppInterface

@pytest.mark.asyncio
async def test_handle_text_message():
    interface = WhatsAppInterface(
        access_token="test_token",
        platform_config={
            "phone_number_id": "123456",
            "verify_token": "test"
        }
    )
    
    webhook_data = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1234567890",
                        "type": "text",
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }
    
    message = await interface.handle_message(webhook_data, "test_flow")
    
    assert message is not None
    assert message.content == "Hello"
    assert message.platform == "whatsapp"
```

### Integration тесты

```python
@pytest.mark.asyncio
async def test_whatsapp_webhook_flow(client):
    """Тест полного flow: webhook → обработка → ответ"""
    
    # 1. Симуляция webhook от WhatsApp
    response = await client.post(
        "/api/v1/webhook/whatsapp/test_flow",
        json={...}  # Webhook payload
    )
    assert response.status_code == 200
    
    # 2. Проверка создания задачи
    # 3. Проверка отправки ответа
```

## Мониторинг и логирование

### Метрики

```python
# Логирование для мониторинга
logger.info(f"📱 WhatsApp webhook: {phone_number} → flow:{flow_id}")
logger.info(f"✅ WhatsApp message sent: {message_id} → {recipient}")
logger.error(f"❌ WhatsApp error: {error_code} - {error_message}")
```

### Dashboard метрики

- Количество входящих сообщений
- Количество исходящих сообщений
- Ошибки доставки
- Средн время ответа
- Активные conversation окна

## Документация для пользователей

Создать руководства:

1. **docs/integrations/whatsapp/setup.md**
   - Как получить WhatsApp Business API доступ
   - Пошаговая настройка
   - Примеры конфигурации

2. **docs/integrations/whatsapp/usage.md**
   - Как добавить WhatsApp к flow
   - Примеры использования
   - Best practices

3. **docs/integrations/whatsapp/templates.md**
   - Работа с message templates
   - Создание и утверждение templates
   - Отправка template сообщений

4. **docs/integrations/whatsapp/media.md**
   - Работа с медиафайлами
   - Ограничения и форматы
   - Примеры кода

## Roadmap и будущие улучшения

### Phase 1 (MVP) - Базовая интеграция
- ✅ Текстовые сообщения (входящие/исходящие)
- ✅ Webhook обработка
- ✅ Typing indicator
- ✅ Базовая обработка медиа (image, document, audio)

### Phase 2 - Расширенный функционал
- 🔄 Interactive messages (кнопки, списки)
- 🔄 Template messages
- 🔄 Статусы доставки и read receipts
- 🔄 Location messages
- 🔄 Contact sharing

### Phase 3 - Advanced features
- 📋 WhatsApp Business Profile integration
- 📋 Rich media (карусели, продукты)
- 📋 WhatsApp Flows (форм внутри чата)
- 📋 Аналитика и insights

### Phase 4 - Enterprise features
- 📋 Multi-agent handoff
- 📋 Broadcast списки
- 📋 Campaign management
- 📋 Advanced analytics

## Возможные проблемы и решения

### 1. Rate limits
**Проблема:** WhatsApp API имеет rate limits
**Решение:** 
- Реализовать очередь сообщений
- Использовать exponential backoff
- Мониторинг rate limit headers

### 2. Template approval
**Проблема:** Message templates требуют одобрения Meta
**Решение:**
- Заранее создавать и одобрять templates
- Иметь fallback на обычные сообщения
- Документировать процесс создания templates

### 3. 24-hour window
**Проблема:** Можно отправлять free-form сообщения только в течение 24 часов после последнего сообщения пользователя
**Решение:**
- Использовать template messages для re-engagement
- Уведомлять пользователей о необходимости инициировать диалог
- Tracking conversation windows

### 4. Media размеры
**Проблема:** Ограничения на размер медиа
**Решение:**
- Валидация перед отправкой
- Автоматическое сжатие изображений
- Понятные сообщения об ошибках

### 5. Webhook reliability
**Проблема:** Webhook'и могут приходить с задержкой или дублироваться
**Решение:**
- Idempotency keys для предотвращения дублей
- Timeout механизмы
- Retry logic с exponential backoff

## Заключение

Интеграция WhatsApp в Agents Lab платформу - это естественное расширение существующей архитектуры. Благодаря унифицированному подходу к интерфейсам, основная работа заключается в:

1. Реализации WhatsAppInterface с поддержкой специфики WhatsApp API
2. Создании webhook endpoints
3. Регистрации платформы в фабрике
4. Настройке конфигурации

После реализации пользователи смогут легко добавлять WhatsApp к своим flow через простую конфигурацию в `FlowConfig.platforms`.

## Приложения

### A. Полезные ссылки

- [WhatsApp Business Platform Documentation](https://developers.facebook.com/docs/whatsapp)
- [WhatsApp Cloud API Reference](https://developers.facebook.com/docs/whatsapp/cloud-api/reference)
- [WhatsApp Webhooks](https://developers.facebook.com/docs/whatsapp/webhooks)
- [Message Templates Guide](https://developers.facebook.com/docs/whatsapp/message-templates)
- [Getting Started Guide](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)

### B. Примеры кода

См. файлы:
- `examples/whatsapp_basic.py` - базовый пример
- `examples/whatsapp_media.py` - работа с медиа
- `examples/whatsapp_interactive.py` - интерактивные сообщения

### C. Конфигурационные шаблоны

См. `examples/configs/whatsapp_flow_config.json`

