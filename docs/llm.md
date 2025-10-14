# LLM в Agent Lab

Agent Lab использует [OpenRouter](https://openrouter.ai) как единый шлюз для доступа к различным LLM провайдерам (OpenAI, Anthropic, Google, и др.).

## Преимущества OpenRouter

- **Единый API** для всех провайдеров (OpenAI, Anthropic, Google, Meta, Mistral и др.)
- **Автоматический фоллбэк** при недоступности модели
- **Прозрачное ценообразование** - платишь по факту использования
- **Без vendor lock-in** - легко менять модели
- **Встроенная балансировка** нагрузки

## Быстрый старт

### 1. Получить API ключ

1. Зарегистрируйся на [openrouter.ai](https://openrouter.ai)
2. Пополни баланс (минимум $5)
3. Создай API ключ в [Keys](https://openrouter.ai/keys)

### 2. Настроить конфигурацию

**Через conf.json:**

```json
{
  "llm": {
    "openrouter": {
      "api_key": "sk-or-v1-...",
      "enabled": true,
      "base_url": "https://openrouter.ai/api/v1",
      "site_url": "https://agents-lab.ru",
      "site_name": "Agent Lab",
      "timeout": 60,
      "max_retries": 3
    },
    "default_model": "anthropic/claude-sonnet-4.5",
    "models": {
      "anthropic/claude-sonnet-4.5": {
        "temperature": 0.2,
        "max_tokens": 10000,
        "description": "Claude Sonnet 4.5 - баланс скорости и качества",
        "input_cost_per_token": 0.00003,
        "output_cost_per_token": 0.00015
      },
      "anthropic/claude-opus-4": {
        "temperature": 0.2,
        "max_tokens": 10000,
        "description": "Claude Opus 4 - максимальное качество",
        "input_cost_per_token": 0.00015,
        "output_cost_per_token": 0.00075
      },
      "openai/gpt-4o": {
        "temperature": 0.7,
        "max_tokens": 4096,
        "description": "GPT-4 Omni - мультимодальная модель",
        "input_cost_per_token": 0.00025,
        "output_cost_per_token": 0.0001
      }
    }
  }
}
```

**Через переменные окружения:**

```bash
export LLM__OPENROUTER__API_KEY="sk-or-v1-..."
export LLM__OPENROUTER__ENABLED=true
export LLM__DEFAULT_MODEL="anthropic/claude-sonnet-4.5"
```

### 3. Использовать в коде

```python
from app.core.llm_factory import get_llm

# Дефолтная модель
llm = get_llm()

# Конкретная модель
llm = get_llm("anthropic/claude-opus-4")

# С переопределением параметров
llm = get_llm("openai/gpt-4o", temperature=0.9, max_tokens=2000)
```

## Конфигурация моделей

### Параметры OpenRouter

| Параметр | Описание | Дефолт |
|----------|----------|--------|
| `api_key` | API ключ OpenRouter | - |
| `enabled` | Включить OpenRouter | `true` |
| `base_url` | URL API | `https://openrouter.ai/api/v1` |
| `site_url` | URL вашего сайта для статистики | `https://agents-lab.ru` |
| `site_name` | Название для статистики | `Agent Lab` |
| `timeout` | Таймаут запроса в секундах | `60` |
| `max_retries` | Максимум повторных попыток | `3` |

### Параметры модели

| Параметр | Описание | Дефолт |
|----------|----------|--------|
| `temperature` | Креативность ответов (0.0-1.0) | `0.2` |
| `max_tokens` | Максимум токенов в ответе | - |
| `description` | Описание модели | - |
| `input_cost_per_token` | Стоимость входного токена в ₽ | `0.00001` |
| `output_cost_per_token` | Стоимость выходного токена в ₽ | `0.00001` |

## Биллинг

Agent Lab автоматически отслеживает использование LLM и списывает стоимость с баланса компании.

### Как работает

1. **До запроса**: проверяется доступ к модели на текущем тарифе и наличие баланса
2. **После запроса**: подсчитываются токены и списывается стоимость
3. **Логирование**: все запросы сохраняются в `billing_transactions`

### Стоимость запроса

```
Стоимость = (input_tokens × input_cost_per_token) + (output_tokens × output_cost_per_token)
```

### Пример

Запрос к `anthropic/claude-sonnet-4.5`:
- Input: 1000 токенов × 0.00003₽ = 0.03₽
- Output: 500 токенов × 0.00015₽ = 0.075₽
- **Итого**: 0.105₽

### Тарифные ограничения

В `TariffService` можно настроить доступные модели для каждого тарифа:

```python
# app/services/tariff_service.py
TARIFF_LIMITS = {
    TariffPlan.FREE: {
        "llm:anthropic/claude-sonnet-4.5": True,  # Доступно
        "llm:anthropic/claude-opus-4": False,      # Недоступно
    },
    TariffPlan.PREMIUM: {
        "llm:anthropic/claude-sonnet-4.5": True,
        "llm:anthropic/claude-opus-4": True,       # Доступно
    }
}
```

## Выбор модели

### Рекомендации

| Задача | Модель | Почему |
|--------|--------|--------|
| Общение с клиентами | `anthropic/claude-sonnet-4.5` | Быстро, качественно, недорого |
| Сложный анализ | `anthropic/claude-opus-4` | Максимальное качество рассуждений |
| Работа с изображениями | `openai/gpt-4o` | Мультимодальность |
| Простые задачи | `openai/gpt-4o-mini` | Самая дешевая |
| Код и математика | `anthropic/claude-sonnet-4.5` | Отличная работа с кодом |

### Популярные модели на OpenRouter

```json
{
  "anthropic/claude-sonnet-4.5": "Универсальная модель, оптимальное соотношение цена/качество",
  "anthropic/claude-opus-4": "Максимальное качество для сложных задач",
  "openai/gpt-4o": "Мультимодальная модель (текст + изображения)",
  "openai/gpt-4o-mini": "Быстрая и дешевая для простых задач",
  "google/gemini-pro-1.5": "Большой контекст (до 1M токенов)",
  "meta-llama/llama-3.1-405b": "Open source, мощная модель"
}
```

Полный список: [openrouter.ai/models](https://openrouter.ai/models)

## Multimodal Support

Agent Lab поддерживает **multimodal output** от LLM - автоматическую обработку файлов, которые генерирует модель.

### Поддерживаемые типы

- **Изображения** (`images`) - модели могут генерировать картинки
- **Аудио** (`audio`) - модели могут генерировать звук (если поддерживается)
- **Файлы** (`files`) - документы, CSV, JSON и т.д.
- **Видео** (`video`) - видеофайлы (если поддерживается)

### Как работает

1. LLM возвращает файл в response (например, `images` field)
2. `ChatOpenAIWithBilling` автоматически:
   - Извлекает base64 данные из ответа
   - Сохраняет через `file_processor` или `audio_processor`
   - Добавляет описание файла в content
3. Агент получает в ответе: `📎 Файл: generated_image.png (ID: file_xxx, ...)`

### Генерация изображений

```python
from app.core.llm_factory import get_llm

# Модель для генерации изображений
llm = get_llm("google/gemini-2.5-flash-preview-image")

# Просто попросить сгенерировать
response = await llm.ainvoke([{
    "role": "user",
    "content": "Generate an image of a red circle"
}])

# В response.content будет описание файла
# "📎 Файл: generated_image.png (ID: file_abc123, [Скачать](...), ...)"
```

### NanoBanana (Gemini Image Generation)

NanoBanana теперь работает через OpenRouter (без зависимости от Google SDK):

```python
from app.core.core_clients.nano_banana_client import get_default_nano_banana_client

client = await get_default_nano_banana_client()

# Генерация изображения
file_ids = await client.generate_images(
    prompt="Create a beautiful landscape",
    num_images=1
)

# С референсным изображением
file_ids = await client.generate_images(
    prompt="Make this image darker",
    reference_file_ids=["file_xyz123"],
    num_images=1
)
```

**Конфигурация**:

```json
{
  "nano_banana": {
    "enabled": true,
    "model_name": "google/gemini-2.5-flash-preview-image",
    "timeout": 60
  }
}
```

### Любой агент может генерировать изображения

```python
class CreativeAgent(BaseAgent):
    id = "creative_agent"
    name = "Creative Agent"
    model = "google/gemini-2.5-flash-preview-image"
    prompt = """
    Ты креативный агент. Можешь генерировать изображения.
    Когда пользователь просит картинку - просто опиши её,
    и система автоматически сгенерирует и сохранит файл.
    """

# Пользователь: "Создай логотип компании"
# Агент: "Generate a modern logo with blue and green colors"
# LLM генерирует изображение
# Агент получает: "📎 Файл: generated_image.png (ID: file_xxx, ...)"
# Пользователь получает изображение
```

## Использование в агентах

### ReAct агент

```python
from app.agents.base import BaseAgent
from app.models.core_models import AgentConfig, AgentType

class MyAgent(BaseAgent):
    id = "my_agent"
    name = "My Agent"
    prompt = "Ты умный ассистент"
    
    @staticmethod
    def get_config() -> AgentConfig:
        return AgentConfig(
            agent_id="my_agent",
            name="My Agent",
            agent_type=AgentType.REACT,
            model="anthropic/claude-sonnet-4.5",
            temperature=0.2,
            max_tokens=10000,
        )
```

### Переопределение модели в runtime

```python
from app.core.agent_factory import AgentFactory

factory = AgentFactory()

# Создать агента с дефолтной моделью
agent = await factory.create_agent("my_agent")

# Создать агента с другой моделью
agent = await factory.create_agent("my_agent", model="anthropic/claude-opus-4")
```

## Mock модели для тестов

Для тестов используются специальные `mock-*` модели, которые не делают реальных запросов к API.

### Настройка mock ответов

```python
from app.core.llm_factory import setup_mock_responses

# Настроить текстовые ответы
setup_mock_responses(
    responses={
        "привет": "Здравствуйте! Чем могу помочь?",
        "погода": "Сегодня солнечно, +20°C"
    },
    default_response="Я mock LLM"
)

# Настроить tool calls
setup_mock_responses(
    tool_responses={
        "сложи": {"tool": "add_tool", "args": {"a": 15, "b": 23}},
        "погода": {"tool": "weather_tool", "args": {"city": "Москва"}}
    }
)
```

### Пример теста

```python
import pytest
from app.core.llm_factory import setup_mock_responses, get_llm

@pytest.mark.asyncio
async def test_agent_greeting():
    # Настраиваем mock
    setup_mock_responses(
        responses={"привет": "Здравствуйте! Как дела?"}
    )
    
    # Используем mock LLM
    llm = get_llm("mock-gpt-4")
    
    # Тестируем
    from langchain_core.messages import HumanMessage
    response = await llm.ainvoke([HumanMessage(content="привет")])
    
    assert "Здравствуйте" in response.content
```

### Логика Mock LLM

Mock LLM использует счетчик вызовов для эмуляции последовательности tool call → результат:

1. **Первый вызов** с ключом → возвращает tool_call
2. **Второй вызов** с тем же ключом → возвращает текстовый ответ

Это позволяет тестировать полный цикл работы агента с инструментами.

## Отладка

### Логирование

```python
import logging

# Включить подробное логирование LLM
logging.getLogger("app.core.llm_factory").setLevel(logging.DEBUG)
logging.getLogger("app.core.llm_billing_wrapper").setLevel(logging.DEBUG)
```

### Проверка конфигурации

```python
from app.core.config import get_settings

settings = get_settings()

print(f"OpenRouter enabled: {settings.llm.openrouter.enabled}")
print(f"API key: {settings.llm.openrouter.api_key[:20]}...")
print(f"Default model: {settings.llm.default_model}")
print(f"Available models: {list(settings.llm.models.keys())}")
```

### Мониторинг использования

```python
from app.db.database import get_async_session
from app.db.models import BillingTransaction

async with get_async_session() as session:
    # Последние 10 LLM запросов
    result = await session.execute(
        "SELECT * FROM billing_transactions "
        "WHERE usage_type = 'llm_request' "
        "ORDER BY created_at DESC LIMIT 10"
    )
    transactions = result.fetchall()
    
    for tx in transactions:
        print(f"{tx.created_at}: {tx.resource_name}, cost={tx.cost}₽")
```

## Миграция с других LLM

### С Yandex GPT

```python
# Было
from app.llms.yandex.yandex_llm import YandexGPT
llm = YandexGPT(model_name="yandexgpt")

# Стало
from app.core.llm_factory import get_llm
llm = get_llm("anthropic/claude-sonnet-4.5")
```

### С прямого OpenAI

```python
# Было
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(api_key="sk-...", model="gpt-4")

# Стало
from app.core.llm_factory import get_llm
llm = get_llm("openai/gpt-4o")
```

## FAQ

### Как добавить новую модель?

Добавь в `conf.json`:

```json
{
  "llm": {
    "models": {
      "google/gemini-pro-1.5": {
        "temperature": 0.7,
        "max_tokens": 8192,
        "input_cost_per_token": 0.0000125,
        "output_cost_per_token": 0.0000375
      }
    }
  }
}
```

И используй:

```python
llm = get_llm("google/gemini-pro-1.5")
```

### Как узнать стоимость модели?

1. Зайди на [openrouter.ai/models](https://openrouter.ai/models)
2. Найди модель и посмотри цены
3. Конвертируй в рубли (умножь на ~90-100)
4. Раздели на 1,000,000 для получения cost_per_token

Пример: GPT-4 Omni
- Input: $2.50 / 1M tokens = 0.0000025 USD/token × 90 = 0.000225₽/token
- Output: $10.00 / 1M tokens = 0.00001 USD/token × 90 = 0.0009₽/token

### Что делать при ошибке "недостаточно средств"?

1. Проверь баланс компании: `company.balance`
2. Пополни баланс через `/payments`
3. Или переключись на более дешевую модель

### Как ограничить расходы на LLM?

1. Установи месячный бюджет в `company.monthly_budget`
2. Используй более дешевые модели для simple задач
3. Настрой тарифные ограничения в `TariffService`

### Mock LLM не работает в тестах

Проверь что:
1. Модель начинается с `mock-`: `get_llm("mock-gpt-4")`
2. Вызвал `setup_mock_responses()` перед тестом
3. Сбрасываешь счетчики между тестами (делается автоматически в `setup_mock_responses()`)

## Дальше

- [Биллинг →](billing.md) - подробнее о системе биллинга
- [Архитектура →](architecture.md) - общая архитектура системы
- [Конфигурация →](configuration.md) - настройка через ENV и JSON

