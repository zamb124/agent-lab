---
trigger: model_decision
description: "Правила работы с базой данных"
globs:
---
# Правила работы с базой данных

## Repository Pattern (основной способ)

**Используй репозитории** для работы с моделями:

<good_example>
from app.core.container import get_container

# Получить репозиторий через контейнер
container = get_container()
agent_repo = container.agent_repository

# CRUD операции (единообразный API как в Storage)
agent = await agent_repo.get("agent_id")
await agent_repo.set(agent_config)
await agent_repo.delete("agent_id")
agents = await agent_repo.list_all(limit=100)
</good_example>

### В API endpoints используй DI:

<good_example>
from app.frontend.dependencies import AgentRepositoryDep

@router.get("/{agent_id}")
async def get_agent(agent_id: str, agent_repo: AgentRepositoryDep):
    agent = await agent_repo.get(agent_id)
    return agent
</good_example>

## Storage (низкоуровневый key-value)

Используй `Storage` напрямую только для:
- Специфичных ключей без модели (`var:*`, `token:*`)
- Операций `list_by_prefix` для поиска ключей
- Временных данных

### Префиксы ключей:
- `agent:{agent_id}` - конфигурации агентов (используй AgentRepository)
- `flow:{flow_id}` - конфигурации flows (используй FlowRepository)
- `task:{task_id}` - задачи (используй TaskRepository)
- `session:{session_id}` - сессии (используй SessionRepository)
- `tool:{tool_id}` - инструменты (используй ToolRepository)
- `user:{user_id}` - пользователи
- `company:{company_id}` - компании
- `subdomain:{subdomain}` - маппинг поддоменов
- `var:{key}` - переменные (используй напрямую Storage)

<good_example>
from app.core.container import get_container

container = get_container()
storage = container.storage

# Для специфичных ключей
await storage.set("var:api_key", value)
var_keys = await storage.list_by_prefix("var:")

# Для моделей используй репозитории
agent_repo = container.agent_repository
agent = await agent_repo.get("agent_id")
</good_example>

## Изоляция по компаниям

Все данные изолированы по компаниям:
- Ключи содержат company_id: `company:{company_id}:flow:{flow_id}`
- Используй `get_context().active_company` для текущей компании
- Не смешивай данные разных компаний

<good_example>
from app.core.context import get_context

context = get_context()
company_id = context.active_company.company_id
key = f"company:{company_id}:flow:{flow_id}"
</good_example>

## Асинхронные операции

Все операции с БД асинхронные:
- Используй `await` для всех запросов
- Не блокируй event loop синхронными вызовами

<good_example>
from app.core.container import get_container

async def get_agent_config(agent_id: str) -> AgentConfig:
    # Для специфичных ключей используй Storage напрямую
    container = get_container()
    storage = container.storage
    data = await storage.get(f"agent:{agent_id}")
    return AgentConfig(**data)

# Для моделей всегда используй репозитории
async def get_agent(agent_id: str) -> AgentConfig:
    container = get_container()
    agent_repo = container.agent_repository
    return await agent_repo.get(agent_id)
</good_example>

## PostgreSQL Checkpointer

Для LangGraph используй PostgreSQL checkpointer:
- Не используй MemorySaver в production
- Checkpointer создается через `get_checkpointer()`
- Автоматически сохраняет state графов

<good_example>
from app.core.checkpointer import get_checkpointer

checkpointer = await get_checkpointer()
graph = graph.compile(checkpointer=checkpointer)
</good_example>

## Транзакции

Используй SQLAlchemy транзакции для атомарных операций:

<good_example>
from app.db.database import get_db_session

async with get_db_session() as session:
    async with session.begin():
        # Операции с БД
        session.add(obj)
        await session.flush()
</good_example>
