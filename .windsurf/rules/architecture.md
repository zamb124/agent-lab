---
trigger: always_on
description: "Архитектурные принципы Agent Lab"
globs:
---
# Архитектурные принципы Agent Lab

## Database-First подход

**ВСЕГДА** следуй принципу Database-First:
- Вся конфигурация агентов, flows и tools хранится в БД
- Код определяет только поведение, но не структуру
- Используй **Repository Pattern** для работы с данными:
  - `Storage` - низкоуровневый key-value доступ
  - `Repository` - CRUD для конкретных моделей (AgentRepository, FlowRepository, etc)
  - `Factory` - создание объектов со всеми зависимостями
- Фабрики используют репозитории для получения конфигурации: `AgentFactory`, `FlowFactory`, `ToolFactory`

<good_example>
# Создание агента через фабрику из БД
agent_factory = get_container().agent_factory
agent = await agent_factory.get_agent(agent_id)

# Работа с конфигурацией через репозиторий
agent_repo = get_container().agent_repository
config = await agent_repo.get(agent_id)

# В FastAPI роутах используй DI через dependencies
from app.frontend.dependencies import AgentRepositoryDep

@router.get("/{agent_id}")
async def get_agent(agent_id: str, agent_repo: AgentRepositoryDep):
    config = await agent_repo.get(agent_id)
    return config
</good_example>

<bad_example>
# Не хардкодь конфигурацию в коде
agent = MyAgent(prompt="...", tools=[...])

# Не используй прямые импорты сущностей контейнера
from app.core.agent_factory import AgentFactory  # НЕТ!
from app.db.repositories import Storage  # НЕТ!

# Не создавай объекты напрямую
storage = Storage()  # НЕТ!
agent_factory = AgentFactory()  # НЕТ!
</bad_example>

## Асинхронность

Вся архитектура полностью асинхронная:
- Используй `async/await` для всех операций с БД, HTTP, LLM
- Все тулы должны быть асинхронными (`async def`)
- Все фабрики и сервисы - асинхронные

<good_example>
@tool
async def my_tool(query: str) -> str:
    result = await some_async_operation()
    return result
</good_example>

## Контекст выполнения

Используй глобальный контекст (`app/core/context.py`) для доступа к:
- Текущему пользователю (`get_context().user`)
- Активной компании (`get_context().active_company`)
- Переменным flow (`get_context().flow_variables`)
- Текущему state (`get_context().state`)

<good_example>
from app.core.context import get_context

def get_current_user():
    context = get_context()
    return context.user
</good_example>

## Модульность

Каждый компонент независим и заменяем:
- Агенты не должны зависеть от конкретной платформы (Telegram/WhatsApp/Web)
- Interfaces адаптируют платформу к унифицированному `Message`
- Tools работают независимо от агентов

## Единообразие

Агенты из кода и созданные через UI работают идентично:
- Миграция (`app/core/migrator.py`) сканирует код и создает записи в БД
- После миграции агенты работают из БД
- Нет различий между "кодовыми" и "UI" агентами

## LangGraph-native

Используй современные возможности LangGraph:
- Предпочитай встроенные механизмы LangGraph кастомным решениям
- Используй `checkpointer` для персистентности
- Используй `GraphInterrupt` для запроса данных у пользователя
- Используй `State` (TypedDict) как единое хранилище данных

## LLM и Multimodal

### Единый LLM провайдер

Используй OpenRouter через `app/core/llm_factory.py`:

<good_example>
from app.core.llm_factory import get_llm

# Дефолтная модель
llm = get_llm()

# Конкретная модель
llm = get_llm("anthropic/claude-sonnet-4.5")

# Модель для генерации изображений
llm = get_llm("google/gemini-2.5-flash-image-preview")
</good_example>

<bad_example>
# НЕ используй прямой импорт
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(api_key="...", model="...")

# НЕ используй Google SDK напрямую
import google.generativeai as genai
</bad_example>

### Multimodal Output

`ChatOpenAIWithBilling` автоматически обрабатывает файлы от LLM:
- **Изображения** - сохраняются через `file_processor`
- **Аудио** - сохраняются через `audio_processor` с распознаванием речи
- **Файлы** - сохраняются через `file_processor`

<good_example>
# Агент с генерацией изображений
class CreativeAgent(BaseAgent):
    model = "google/gemini-2.5-flash-image-preview"
    prompt = "Ты можешь генерировать изображения"

# LLM вернет: "📎 Файл: generated_image.png (ID: file_xxx, ...)"
# Файл автоматически сохранен в S3
</good_example>

### NanoBanana

Используй `NanoBananaClient` для генерации изображений:

<good_example>
from app.core.core_clients.nano_banana_client import get_default_nano_banana_client

client = await get_default_nano_banana_client()

# Генерация
file_ids = await client.generate_images(
    prompt="Beautiful sunset",
    num_images=1
)

# С референсом
file_ids = await client.generate_images(
    prompt="Make it darker",
    reference_file_ids=["file_abc123"],
    num_images=1
)
</good_example>

**Важно**: NanoBanana теперь работает через OpenRouter, не нужен отдельный Google API key.
