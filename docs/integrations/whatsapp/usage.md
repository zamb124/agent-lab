# Использование WhatsApp в агентах

## Обратная совместимость с Telegram

WhatsApp интерфейс полностью совместим с Telegram - все возможности работают одинаково.

## Отправка сообщений

### Простой текст

Агент отправляет обычный текст:

```python
return "Погода в Москве: +15°C, облачно"
```

WhatsApp автоматически форматирует Markdown:
```python
return "**Важно!** Температура: *+15°C*"
# Результат в WhatsApp: *Важно!* Температура: _+15°C_
```

### С кнопками

#### До 3 кнопок (Reply Buttons)

```python
# В агенте
def format_response_with_buttons(self):
    # Возвращаем специальный формат
    return {
        "text": "Выберите действие:",
        "buttons": [
            {"id": "weather", "text": "Узнать погоду"},
            {"id": "forecast", "text": "Прогноз на неделю"},
            {"id": "help", "text": "Помощь"}
        ]
    }
```

Или через state:
```python
# В state агента
state["response_buttons"] = [
    {"id": "yes", "text": "Да"},
    {"id": "no", "text": "Нет"}
]
```

#### 4-10 кнопок (List Message)

```python
# Больше 3 кнопок - автоматически становится списком
buttons = [
    {"id": "city_1", "text": "Москва", "description": "Столица России"},
    {"id": "city_2", "text": "Санкт-Петербург", "description": "Северная столица"},
    {"id": "city_3", "text": "Казань", "description": "Столица Татарстана"},
    {"id": "city_4", "text": "Сочи", "description": "Курортный город"},
]
```

WhatsApp покажет их как интерактивный список с кнопкой "Выбрать".

### Аудио сообщения

Агент может генерировать аудио через `[AUDIO]` блоки:

```python
return "[AUDIO]audio_id:abc123[/AUDIO] Вот голосовое сообщение с прогнозом погоды"
```

WhatsApp:
1. Извлечет audio_id
2. Скачает из S3
3. Загрузит в WhatsApp
4. Отправит как аудио сообщение

### Медиа от пользователя

Когда пользователь отправляет медиа:

#### Изображения

```python
# Агент получает в промпте:
"""
📷 Изображение: whatsapp_image_xyz.jpg
URL: https://your-company.agents-lab.ru/api/v1/files/download/file_123
Размер: 245 KB
"""
```

#### Аудио/голосовые

```python
# Агент получает распознанный текст:
"""
🎤 Голосовое сообщение: whatsapp_voice_xyz.ogg
Распознано: "Какая погода в Москве?"
URL: https://your-company.agents-lab.ru/api/v1/files/download/audio/audio_123
"""
```

#### Документы

```python
# Агент получает:
"""
📎 Документ: report.pdf
URL: https://your-company.agents-lab.ru/api/v1/files/download/file_456
Размер: 1.2 MB
"""
```

#### Локация

```python
# Агент получает:
"""
📍 Локация: Central Park
Адрес: New York, NY
Координаты: 40.785091, -73.968285
"""
```

## Команды

WhatsApp поддерживает те же команды что Telegram:

### /start

Пользователь: `/start`
Ответ: `👋 Привет! Я ИИ агент. Чем могу помочь?`

### /help

Показывает список команд и возможностей бота.

### /clear

Очищает контекст диалога - начинается новая сессия.

## Сценарии использования

### 1. Простой FAQ бот

```python
class FAQAgent(BaseAgent):
    def get_prompt(self) -> str:
        return """
        Ты FAQ бот для службы поддержки.
        Отвечай кратко и по делу.
        Используй кнопки для навигации.
        """
    
    def get_tools(self):
        return [search_faq_tool, create_ticket_tool]
```

Пользователь в WhatsApp:
```
User: Как вернуть товар?
Bot: Для возврата товара нужно:
     1. Заполнить форму возврата
     2. Отправить товар в течение 14 дней
     
     [Кнопки: "Форма возврата" | "Условия возврата" | "Связаться с поддержкой"]
```

### 2. Голосовой ассистент

```python
class VoiceWeatherAgent(BaseAgent):
    def get_prompt(self) -> str:
        return """
        Ты голосовой ассистент погоды.
        Отвечай голосом через [AUDIO] блоки.
        Будь дружелюбным и естественным.
        """
    
    def get_tools(self):
        return [get_weather_tool, generate_voice_tool]
```

Пользователь в WhatsApp:
```
User: [голосовое] "Какая погода в Москве?"
Bot: [аудио] "В Москве сейчас +15 градусов, облачно с прояснениями"
```

### 3. Заказ с изображениями

```python
class OrderAgent(BaseAgent):
    def get_prompt(self) -> str:
        return """
        Ты помощник по оформлению заказов.
        Принимай фото товаров и помогай с заказом.
        """
    
    def get_tools(self):
        return [analyze_image_tool, create_order_tool]
```

Пользователь в WhatsApp:
```
User: [фото платья] "Хочу заказать это"
Bot: Отличный выбор! Это платье артикул #12345.
     Доступные размеры: S, M, L, XL
     
     [Кнопки: "S" | "M" | "L" | "XL"]
```

## Интеграция с агентами

WhatsApp прозрачно работает с агентами:

```python
from app.agents.react_agent import ReActAgent

class WeatherAgent(ReActAgent):
    name = "weather_agent"
    prompt = "Ты помощник по погоде"
    tools = [weather_tool, image_tool, voice_tool]

# Агент автоматически поддерживает WhatsApp
agent = WeatherAgent()
```

Все инструменты работают одинаково в Telegram и WhatsApp:
- `ask_user()` - задать вопрос (с interrupt)
- Любые кастомные tools
- Вложенные агенты (supervisors)

## Специфика WhatsApp

### Conversation Windows

Бесплатные сообщения только в течение 24 часов после сообщения пользователя.

**Мониторинг окон:**
```python
# В metadata сессии автоматически
session.metadata["last_user_message_at"] = "2025-10-09T12:00:00Z"
session.metadata["conversation_window_expires_at"] = "2025-10-10T12:00:00Z"
```

**Re-engagement через template:**
```python
# Когда окно закрылось
if conversation_expired:
    await send_template_message(
        phone_number=user_phone,
        template_name="re_engagement",
        parameters=["Иван", "прогноз погоды"]
    )
```

### Типы контента

WhatsApp не поддерживает:
- ❌ Inline клавиатуры (как в Telegram)
- ❌ Карусели (пока)
- ❌ Polls/опросы
- ❌ Dice/игры

Поддерживает дополнительно к Telegram:
- ✅ Локация с именем и адресом
- ✅ Контакты (vCard)
- ✅ Catalog messages (товары)

### Особенности кнопок

**Telegram:**
- Поддержка inline клавиатур
- Callback data
- URL кнопки

**WhatsApp:**
- Reply buttons (до 3)
- List messages (4-10)
- URL кнопки через Call-to-Action

**Unified подход в агенте:**
```python
# Этот код работает и в Telegram и в WhatsApp
buttons = [
    {"id": "opt1", "text": "Опция 1"},
    {"id": "opt2", "text": "Опция 2"}
]

# Канал сама решает как отобразить
# Telegram → inline keyboard
# WhatsApp → reply buttons
```

## Примеры кода

### Полный пример агента

```python
from app.agents.base import BaseAgent
from app.tools.weather_tools import get_weather

class MultiPlatformWeatherAgent(BaseAgent):
    """Агент работающий и в Telegram и в WhatsApp"""
    
    def get_prompt(self) -> str:
        return """
        Ты {bot_name} - ассистент погоды.
        
        Умеешь:
        - Узнавать погоду в любом городе
        - Давать прогноз на неделю
        - Отвечать голосом (если пользователь спросил голосом)
        
        Используй кнопки для удобства.
        Форматируй ответы красиво с *жирным* и _курсивом_.
        """
    
    def get_tools(self):
        return [get_weather, get_forecast, generate_voice_response]
    
    async def preprocess_input(self, user_input: str, context: dict) -> str:
        """Обработка перед отправкой в LLM"""
        
        # Определяем платформу
        platform = context.get("platform", "api")
        
        # Адаптируем промпт под платформу
        if platform == "whatsapp":
            return f"[WhatsApp пользователь] {user_input}"
        elif platform == "telegram":
            return f"[Telegram пользователь] {user_input}"
        
        return user_input
```

### Работа с файлами

```python
from langchain_core.messages import HumanMessage

@tool
async def analyze_weather_photo(image_url: str) -> str:
    """Анализирует фото погоды"""
    # image_url автоматически доступен из медиа
    # Обрабатываем через Vision API
    return "На фото виден ясный день, солнечно"
```

## Миграция с Telegram на WhatsApp

Если у вас уже есть бот на Telegram - добавить WhatsApp просто:

### 1. Добавьте WhatsApp platform в FlowConfig

```python
# Было
platforms={
    "telegram": {
        "username": "@var:bot_username",
        "token": "@var:telegram_token"
    }
}

# Стало - добавляем WhatsApp
platforms={
    "telegram": {
        "username": "@var:bot_username",
        "token": "@var:telegram_token"
    },
    "whatsapp": {
        "phone_number_id": "@var:whatsapp_phone_id",
        "access_token": "@var:whatsapp_token",
        "verify_token": "@var:whatsapp_verify"
    }
}
```

### 2. Создайте переменные

Создайте WhatsApp credentials через Variables API.

### 3. Зарегистрируйте flow

```bash
curl -X POST "https://your-company.agents-lab.ru/api/v1/admin/whatsapp/register/my_flow_id"
```

### 4. Настройте webhook

Используйте URL из ответа регистрации в Meta for Developers.

**Готово!** Тот же агент теперь работает и в Telegram и в WhatsApp.

## Advanced: Канало-специфичная логика

Если нужна разная логика для платформ:

```python
from app.core.context import get_context

class SmartAgent(BaseAgent):
    async def process(self, user_input: str) -> str:
        context = get_context()
        platform = context.platform
        
        if platform == "whatsapp":
            # WhatsApp специфичная логика
            # Например, больше emoji или короткие ответы
            return self._whatsapp_response(user_input)
        elif platform == "telegram":
            # Telegram специфичная логика
            # Например, inline клавиатуры
            return self._telegram_response(user_input)
        else:
            # Универсальная логика
            return self._generic_response(user_input)
```

Но в большинстве случаев это **не нужно** - платформа делает адаптацию автоматически.

