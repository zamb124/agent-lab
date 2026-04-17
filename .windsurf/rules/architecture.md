---
trigger: always_on
description:
globs:
---
# Архитектурные принципы Humanitec

## Dependency Injection (единый стандарт)

### Контейнер и `@lazy`

DI строится на `BaseContainer` (`core/container/base.py`) с декоратором `@lazy` — property с кешированием на экземпляре. Каждый сервис наследует `BaseContainer` и добавляет свои `@lazy` для репозиториев и сервисов.

Singleton контейнера — модульная переменная `get_*_container()` на процесс; при старте HTTP-сервиса `create_service_app` кладёт тот же объект в `app.state.container`.

### `dependencies.py` + `ContainerDep` (ОБЯЗАТЕЛЬНО для каждого сервиса)

Каждый сервис **обязан** иметь `dependencies.py` с единственным каноничным способом получения контейнера в HTTP-слое:

```python
# apps/<service>/dependencies.py
from typing import Annotated
from fastapi import Depends
from apps.<service>.container import get_<service>_container, <Service>Container

def get_container() -> <Service>Container:
    return get_<service>_container()

ContainerDep = Annotated[<Service>Container, Depends(get_container)]
```

Каждый HTTP-хендлер **обязан** получать контейнер ТОЛЬКО через `ContainerDep`:

```python
from apps.<service>.dependencies import ContainerDep

@router.get("/items")
async def list_items(container: ContainerDep):
    return await container.some_service.list()
```

### Имя параметра

Строго `container` — не `c`, не `cont`, не `svc`. Единое имя упрощает grep и автодополнение.

### ContainerDep обязателен для ВСЕХ HTTP-хендлеров

Включая utility-эндпоинты (health, metadata, certificate и т.д.). Если хендлер не использует контейнер: `_ = container` в теле. Цель — единообразие сигнатур и возможность добавить зависимость без рефакторинга.

### Никаких гранулярных get_*_service() фабрик

Запрещены обёртки типа `get_entity_service()`, `get_graph_service()` в `dependencies.py`. Один хендлер — один `container: ContainerDep`, доступ через `container.entity_service`, `container.graph_service`.

### Запрещено в HTTP-слое

- Прямой вызов `get_*_container()` в теле хендлера
- Локальное определение `get_container_dep()` в файлах роутеров
- Импорт контейнера другого сервиса (`from apps.X.container import get_X_container`)
- Создание репозиториев/сервисов в обход контейнера (`SomeRepository(db_url=...)`)
- Смешанный стиль: `Depends(get_service)` + `get_container()` в одном хендлере

### Допустимые исключения

- В `core/api/*.py` — `request.app.state.container` (core не знает конкретный тип контейнера)
- В TaskIQ задачах — `get_*_container()` напрямую (нет FastAPI request scope)
- В каналах/триггерах flows — `get_container()` (не HTTP-контекст)
- `core/push/delivery.py` — `PushSubscriptionRepository(db_url=...)` (вызывается из HTTP, WebSocket, workers — единый контейнер недоступен)
- `apps/frontend/api/embed_configs.py` — допустимо использует flows container напрямую (монолит, все сервисы в одном процессе)
- WebSocket-эндпоинты (`apps/sync/main.py:ws_endpoint`) — FastAPI `Depends()` не работает с WebSocket route handlers в том же виде, контейнер берётся через `get_*_container()`

### Известные нарушения `core/ → apps/` (требуют архитектурной проработки)

- `core/scheduler/scheduler.py` — импортирует брокеры всех воркеров (`apps.*_worker`)
- `core/api/integrations.py` — `_resume_flow` импортирует `process_flow_task` из flows
- `core/clients/llm/factory.py` — `get_mock_for_llm` из flows (тестовый путь)

## Database-First

Вся конфигурация flows и tools хранится в БД. Код определяет только поведение, но не структуру.

- `Storage` — низкоуровневый key-value доступ
- `Repository` — CRUD для конкретных моделей
- `Factory` — создание объектов со всеми зависимостями из БД

```python
from apps.flows.src.container import get_container

# Через фабрику
flow = await get_container().flow_factory.get_flow(flow_id)

# Через репозиторий
config = await get_container().flow_repository.get(flow_id)
```

Запрещено хардкодить конфигурацию в Python-коде — бизнес-логика живёт в JSON конфигах flows в БД.

## Graph-based execution

Выполнение — граф нод. Класс `Flow` (`apps/flows/src/runtime/flow.py`) обходит граф по рёбрам.
Для прерывания выполнения и запроса данных у пользователя используй `FlowInterrupt`.
Персистентность состояния между запросами — через `StateManager` (`apps/flows/src/state/persistence.py`).

## LLM

Только через `core/clients/llm/factory.py`:

```python
from core.clients.llm import get_llm

llm = get_llm()
llm = get_llm("anthropic/claude-sonnet-4.5")
```

Запрещены прямые импорты LangChain/OpenAI моделей.

## Multimodal Output

`ChatOpenAIWithBilling` автоматически обрабатывает файлы от LLM:
- Изображения → `file_processor` → S3
- Аудио → `audio_processor` → S3 с распознаванием речи
- Файлы → `file_processor` → S3

## NanoBanana

Для генерации изображений:

```python
from core.clients.nano_banana import NanoBananaClient, NanoBananaClientFactory

client = await NanoBananaClientFactory.create()
file_ids = await client.generate_images(prompt="Beautiful sunset", num_images=1)

# С референсом
file_ids = await client.generate_images(
    prompt="Make it darker",
    reference_file_ids=["file_abc123"],
    num_images=1
)
```

NanoBanana работает через OpenRouter.

## Контекст выполнения

`get_context()` для доступа к текущему пользователю, компании, trace_id:

```python
from core.context import get_context

context = get_context()
user = context.user
company_id = context.active_company.id
trace_id = context.trace_id
```

Репозитории берут `company_id` из контекста автоматически.
Межсервисный доступ к данным: приоритет репозитория при общей БД; `ServiceClient` — для намеренного HTTP API (`repository_inter_service.mdc`).
`ServiceClient` передаёт `X-Trace-Id`, `Authorization`, `X-Company-Id`, `X-User-Id` из контекста.
