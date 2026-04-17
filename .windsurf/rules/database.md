---
trigger: model_decision
description: "База данных, репозитории, модели и Storage"
globs:
---
# База данных и репозитории

## Главный принцип

**ВСЕ данные ТОЛЬКО через репозитории. Storage - приватный класс.**

Схема PostgreSQL задаётся **только Alembic** (`migrations/<сервис>/`, `make migrate`). В `apps/*` не вызывать `Base.metadata.create_all` и не выполнять скрытые DDL-обходы.

## Три главных правила кода

1. **НИКАКИХ локальных импортов** - все импорты в начале файла
2. **НИКАКИХ лишних if-else** - логика должна быть прозрачной, используй early return
3. **try-except ТОЛЬКО для IO/внешних сервисов** - не для бизнес-логики

## Структура БД (каждый сервис — своя PostgreSQL-база)

| Переменная окружения    | База данных      | Владелец моделей              |
|-------------------------|------------------|-------------------------------|
| DATABASE__SHARED_URL    | platform_shared  | core/db/models/platform.py    |
| DATABASE__FLOWS_URL     | platform_agents  | `migrations/services.json` → `flows_url`, модели `apps/flows/src/db/models.py` |
| DATABASE__CRM_URL       | platform_crm     | apps/crm/db/models.py         |
| DATABASE__SYNC_URL      | platform_sync    | apps/sync/db/models.py        |
| DATABASE__RAG_URL       | platform_rag     | core/db/models/rag.py         |

Таблицы из `core/db/models/platform.py` (в т.ч. `variables`, `users`, `usage`) живут только в **platform_shared**. В `FlowContainer` репозитории к ним — через `shared_storage`, не через `storage` (service БД flows).

```
core/db/
├── models/
│   ├── __init__.py         # реэкспорт Base + всех моделей
│   ├── base.py             # class Base(DeclarativeBase): pass
│   ├── platform.py         # Storage, Users, Variables, Usage, Namespaces, Spans, PushSubscription
│   └── rag.py              # DocumentProcessingStatus, VectorDocument
├── storage.py              # Storage (приватный, только для репозиториев)
├── base_repository.py      # BaseRepository (композиция с Storage)
├── service_registry.py     # реестр: name, get_db_url, alembic_script_location
├── migrations.py           # run_migrations_async(), Alembic helpers
└── repositories/           # core репозитории (shared БД)

См. `scripts/db_migrate.py` — единственная CLI для миграций (argparse).

apps/flows/src/db/
├── models.py               # Flows, FlowsVersions, Nodes, Tools, States,
│                           # EvaluationResults, ScheduledTasks, Resources,
│                           # Stores, FlowStates (+ реляционные таблицы в миграциях)
├── flow_repository.py, node_repository.py, tool_repository.py, state_repository.py,
│   evaluation_repository.py, llm_model_repository.py, scheduled_task_repository.py,
│   mcp_repository.py, resource_repository.py
└── (репозитории лежат в этом каталоге, без подпапки `repositories/`)

apps/crm/db/models.py       # CRMEntity, EntityType, RelationshipType, ...
apps/sync/db/models.py      # SyncSpace, SyncChannel, SyncMessage, ...
```

## BaseRepository - незыблемая логика

```python
class BaseRepository(ABC, Generic[T]):
    is_global: bool = False  # Атрибут класса
    owner_service: str = "core"  # сервис-владелец; в flows-репозиториях обычно `"flows"`
    
    def __init__(self, storage: Storage, model_class: Type[T]):
        self._storage = storage  # Приватная композиция
        self.model_class = model_class
    
    def _build_final_key(self, key: str) -> str:
        if self.is_global:
            return key
        
        context = get_context()
        company_id = context.active_company.company_id
        return f"company:{company_id}:{key}"
    
    # _get_key / _get_prefix / _get_table_name — переопределяются при необходимости (дефолты в BaseRepository)
    
    @abstractmethod
    def _extract_entity_id(self, entity: T) -> str:
        """Извлечение ID из сущности"""
        pass
```

## Все репозитории

### Core репозитории (shared БД):

| Репозиторий | is_global | Таблица | Префикс ключа |
|-------------|-----------|---------|---------------|
| UserRepository | True | users | user: |
| CompanyRepository | True | storage | company: |
| AuthSessionRepository | True | users | auth_session: |
| SubdomainRepository | True | storage | subdomain: |
| VariableRepository | False | variables | company:X:var: |
| UsageRepository | False | usage | company:X:usage: |
| FileRepository | False | storage | company:X:file: |
| DocumentStatusRepository | False | storage | company:X:doc_status: |
| EmbedConfigRepository | False | storage | company:X:embed_config: |
| EmbedMappingRepository | False | storage | company:X:embed_mapping: |
| NamespaceRepository | False | storage | company:X:namespace: |

### Репозитории сервиса flows (service БД `platform_agents`):

| Репозиторий | is_global | Таблица | Ключ / примечание |
|-------------|-----------|---------|-------------------|
| FlowRepository | False | `flows` (+ версии в `flows_versions`) | база `flow:{flow_id}` → `company:{id}:flow:{flow_id}` |
| NodeRepository | False | `nodes` | `node:{id}` |
| ToolRepository | False | `tools` | `tool:{id}` |
| DatabaseStateRepository | False | `states` | `state:{session_id}` |
| ResourceRepository | False | `resources` | `resource:{id}` |
| MCPServerRepository | False | `mcp_servers` | `mcp_server:{id}` |
| LLMModelRepository | **True** | **`storage`** | **`llm_model:{provider}:{model_id}`** без префикса компании |
| EvaluationRepository | — | **`evaluation_results`** | не KV: прямые INSERT/SELECT (см. `evaluation_repository.py`) |
| ScheduledTaskRepository | — | **`scheduled_tasks`** | не наследует `BaseRepository`: SQL по `ScheduledTasks` |

Web Push: **`push_subscription_repository`** в `BaseContainer` (**shared** БД, таблица `push_subscriptions` в `core/db/models/platform.py`), не репозиторий flows service DB.

## is_global определяет поведение

**is_global=True (глобальные сущности):**
- User, Company, AuthSession, Subdomain
- Ключ: `user:{user_id}` (без префикса компании)
- Таблица: обычно `users` или `storage`

**is_global=False (изолированные по компании в flows БД):**
- FlowConfig → таблица **`flows`**, ключ `flow:{flow_id}`
- Node, Tool, State (сессии), Resource, MCP — свои таблицы (`nodes`, `tools`, `states`, …)
- Переменные (**Variable**), Usage, File, Embed* — **shared** БД (`VariableRepository` и др. через `shared_storage`), не таблицы flows-only

**is_global=True (пример в flows):** `LLMModelRepository` — ключи без `company:`, таблица **`storage`**.

## Использование репозиториев

```python
from apps.flows.src.container import get_container

container = get_container()

# Получить сущность
flow_config = await container.flow_repository.get("flow_id")
user = await container.user_repository.get("user_id")

# Сохранить
await container.flow_repository.set(flow_config)
await container.user_repository.set(user)

# Удалить
await container.flow_repository.delete("flow_id")

# Список всех
flows = await container.flow_repository.list_all(limit=100)

# Получить несколько
flows_batch = await container.flow_repository.get_many(["id1", "id2"])
```

## Service БД vs Shared БД

**Service БД** (`container.storage`):
- Конфиги flow (**таблица `flows`**, не `agents`), ноды, тулы, state, ресурсы, MCP, KV в **`storage`** (в т.ч. глобальные LLM models)

**Shared БД** (`container.shared_storage`):
- User, Company, variables, usage, файлы, push subscriptions и др. из `core/db/models/platform.py`

```python
container = FlowContainer(
    db_url="postgresql://localhost/platform_agents",
    shared_db_url="postgresql://localhost/platform_shared",
)
# допустим алиас: service_db_url=... (эквивалент db_url в BaseContainer)

# Маршрутизация:
flow_repo = container.flow_repository      # → service БД
user_repo = container.user_repository        # → shared БД
state_repo = container.state_repository      # → service БД
company_repo = container.company_repository  # → shared БД
```

## Изоляция данных

**Автоматическая через `is_global`:**

```python
# FlowRepository (is_global=False)
await flow_repo.set(flow_config)
# Хранится: company:{subdomain|company_id}:flow:my_flow

# UserRepository (is_global=True)
await user_repo.set(user)
# Хранится: user:user_123
```

**НЕТ ручного добавления префикса:**

```python
# НЕТ! Не добавляй префикс вручную
key = f"company:{company_id}:flow:{flow_id}"
await storage.set(key, data)

# ДА! Репозиторий сам добавит префикс
await flow_repo.set(flow_config)
```

## Storage - ТОЛЬКО для репозиториев

**Storage теперь приватный класс:**

```python
# Внутри BaseRepository
self._storage._get_with_session_and_table(key, table)
self._storage._set_with_table(key, value, table)
```

```python
# НЕ используй Storage напрямую
storage = container.storage
await storage.get("flow:my_flow")  # НЕТ!

# Используй репозиторий
flow_repo = container.flow_repository
await flow_repo.get("my_flow")  # ДА!
```

## Создание нового репозитория

**Шаги:**

1. Создай класс репозитория
2. Определи `is_global` (True или False)
3. Реализуй все абстрактные методы
4. Добавь в контейнер
5. Добавь dependency (опционально)

```python
# 1. Создать репозиторий
class MyRepository(BaseRepository[MyModel]):
    is_global = False
    owner_service = "flows"
    
    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=MyModel)
    
    def _get_key(self, entity_id: str) -> str:
        return f"my:{entity_id}"
    
    def _get_prefix(self) -> str:
        return "my:"
    
    def _get_table_name(self) -> str:
        return "storage"
    
    def _extract_entity_id(self, entity: MyModel) -> str:
        return entity.id

# 2. Добавить в контейнер
class FlowContainer(BaseContainer):
    def __getattr__(self, name):
        if name == 'my_repository':
            if self._my_repository is None:
                self._my_repository = MyRepository(storage=self.storage)
            return self._my_repository
        return super().__getattr__(name)

# 3. Добавить dependency
async def get_my_repository() -> MyRepository:
    return get_container().my_repository

MyRepositoryDep = Annotated[MyRepository, Depends(get_my_repository)]
```

## Модели

### Разделение: Shared vs Service-specific

**Shared модели (в core/models/)**:
- `identity_models.py`: User, Company, AuthSession
- `context_models.py`: Context
- `files/models.py`: FileRecord, AudioRecord, AudioAttachmentContent, AudioTranscriptionStatus (единый аудио/STT контракт: `duration_ms`, `transcription_status`, `transcription_text`, `transcription_error`)

**Service-specific модели (в apps/flows/src/models/)**:
- `flow_config.py`: FlowConfig, NodeConfig, SkillConfig, …
- `enums.py`: NodeType, CodeMode, …
- `evaluation_result.py`, `llm_model.py`, `resource.py`, `mcp.py`, …

**ExecutionState** — в **`core/state/`** (Pydantic), не в `apps/flows/src/models/`.

### Правило: НЕТ дубликатов

```python
# НЕ создавай эти файлы в apps/flows/src/models/:
# context_models.py - Context в core!
# identity_models.py - User, Company в core!
# file_models.py - FileRecord в core!
```

### Импорты моделей

```python
from core.models import User, Company
from core.files.models import FileRecord
from apps.flows.src.models import FlowConfig, NodeConfig
```

### Кастомный Field

**КРИТИЧНО**: Используй `from core.fields import Field` вместо `from pydantic import Field`

```python
from core.fields import Field

class User(BaseModel):
    user_id: str = Field(
        title="ID",
        readonly=True,        # → json_schema_extra
        placeholder="user_123"  # → json_schema_extra
    )
```

Кастомные поля автоматически переносятся в json_schema_extra:
- readonly
- placeholder
- groups
- widget_attrs
- exclude_from_form
- editable_in_table
- hidden

### Хранение моделей через репозитории

**Каждая модель имеет свой репозиторий:**

```python
# User → UserRepository (core/db/repositories/)
# Company → CompanyRepository (core/db/repositories/)
# FlowConfig → FlowRepository (apps/flows/src/db/flow_repository.py)
# NodeConfig → NodeRepository (apps/flows/src/db/node_repository.py)
# ExecutionState → DatabaseStateRepository (apps/flows/src/db/state_repository.py)
```

**НИКОГДА не работай с моделями через Storage напрямую:**

```python
# НЕТ!
storage = container.storage
data = await storage.get("flow:my_flow")
flow_config = FlowConfig.model_validate_json(data)

# ДА!
flow_repo = container.flow_repository
flow_config = await flow_repo.get("my_flow")
```

## API репозиториев

Для классов **`BaseRepository`**: `get`, `set`, `delete`, `list_all`, `get_many` (где реализовано).

`EvaluationRepository` / `ScheduledTaskRepository` — свои методы (`save`, `list_tasks`, …), без унифицированного `set` как у KV-репозиториев.

## В API endpoints

```python
from fastapi import APIRouter, HTTPException

from apps.flows.src.container import get_container

router = APIRouter()

@router.get("/{flow_id}")
async def get_flow(flow_id: str):
    flow_config = await get_container().flow_repository.get(flow_id)
    if flow_config is None:
        raise HTTPException(status_code=404)
    return flow_config
```

## В тестах

```python
async def test_example(
    app,
    unique_id,         # Генератор уникальных ID для изоляции
):
    container = get_container()
    flow_repo = container.flow_repository
    
    flow_id = f"test_flow_{unique_id}"
    flow_config = FlowConfig(
        flow_id=flow_id,
        name="Test flow",
        ...
    )
    
    await flow_repo.set(flow_config)
    
    loaded = await flow_repo.get(flow_id)
    assert loaded.name == "Test flow"
```

## КРИТИЧНЫЕ ПРАВИЛА

1. **ВСЕГДА** через репозитории, НИКОГДА напрямую Storage
2. **НИКОГДА** не добавляй префикс `company:` вручную
3. **ВСЕГДА** определяй `is_global` в классе
4. **НИКОГДА** не обходи изоляцию через `force_global` у **`Storage`** из прикладного кода (репозитории используют `BaseRepository._build_final_key`)
5. **ВСЕГДА** получай репозитории из контейнера
6. **НЕТ дубликатов** между core и apps
7. **Shared модели** (User, Company, FileRecord) → core → shared БД
8. **Модели конфигов flows** (FlowConfig, NodeConfig, …) → apps/flows; **ExecutionState** (тип) → core/state; персист состояния → `DatabaseStateRepository` → service БД
9. Используй **core.fields.Field** везде (Pydantic v2 совместимый)

**Нарушение приведет к ошибкам изоляции и дублированию данных!**
