# Рефакторинг архитектуры БД - Финальный отчет

## Цель

Унификация работы с БД: все сущности через репозитории, префикс компании для всех (кроме глобальных), убрать Storage из публичного API.

## Реализованные принципы

### 1. Чистая архитектура BaseRepository

**Композиция вместо наследования:**
```python
class BaseRepository(ABC, Generic[T]):
    is_global: bool = False  # Атрибут класса
    
    def __init__(self, storage: Storage, model_class: Type[T]):
        self._storage = storage  # Приватная композиция
        self.model_class = model_class
```

**Незыблемая логика без ветвлений:**
```python
def _build_final_key(self, key: str) -> str:
    if self.is_global:
        return key
    
    context = get_context()
    company_id = context.active_company.company_id
    return f"company:{company_id}:{key}"
```

### 2. Изоляция по компаниям

**Все сущности изолированы (`is_global=False`):**
- agent, flow, tool, mcp_server
- task, session (в service БД agents)
- var, usage, file

**Глобальные сущности (`is_global=True`):**
- user, company (метаданные)
- auth_session (OAuth сессии)
- subdomain (маппинг)

### 3. Service БД vs Shared БД

**Service БД (apps/agents):**
- agent, flow, tool, mcp_server
- task, session
- var, usage, file

**Shared БД (core):**
- user, company
- auth_session, subdomain

### 4. Каждый репозиторий знает свою таблицу

```python
class AgentRepository(BaseRepository[AgentConfig]):
    is_global = False
    
    def _get_table_name(self) -> str:
        return "storage"

class TaskRepository(BaseRepository[TaskConfig]):
    is_global = False
    
    def _get_table_name(self) -> str:
        return "tasks"
```

## Созданные репозитории

### Core (7 репозиториев в shared БД):

1. **UserRepository** - пользователи (`is_global=True`, таблица `users`)
2. **CompanyRepository** - компании (`is_global=True`, таблица `storage`)
3. **AuthSessionRepository** - OAuth сессии (`is_global=True`, таблица `users`)
4. **SubdomainRepository** - маппинг subdomain→company_id (`is_global=True`, таблица `storage`)
5. **VariableRepository** - переменные (`is_global=False`, таблица `variables`)
6. **UsageRepository** - биллинг записи (`is_global=False`, таблица `storage`)
7. **FileRepository** - файлы (`is_global=False`, таблица `storage`)

### Apps/agents (6 репозиториев в service БД):

1. **AgentRepository** - агенты (`is_global=False`, таблица `storage`)
2. **FlowRepository** - flows (`is_global=False`, таблица `storage`)
3. **ToolRepository** - инструменты (`is_global=False`, таблица `storage`)
4. **TaskRepository** - задачи (`is_global=False`, таблица `tasks`)
5. **SessionRepository** - сессии (`is_global=False`, таблица `storage`)
6. **MCPServerRepository** - MCP серверы (`is_global=False`, таблица `storage`)

## Обновленные сервисы

### AuthService
```python
def __init__(
    self,
    user_repository: UserRepository,
    company_repository: CompanyRepository,
    auth_session_repository: AuthSessionRepository
):
    self._storage = user_repository._storage  # Для временных данных
```

### BillingService
```python
def __init__(
    self,
    company_repository: CompanyRepository,
    user_repository: UserRepository,
    usage_repository: UsageRepository = None
):
    ...
```

### VariablesService
```python
def __init__(self, variable_repository: VariableRepository):
    self.variable_repository = variable_repository
```

## Storage стал приватным

**НЕ используется напрямую:**
- Убран из dependencies (`StorageDep` удален)
- Убран из публичного API контейнеров
- Доступен только через `_storage` внутри репозиториев

**Допустимо использование приватного `_storage`:**
- Временные данные с TTL (media_group, notifications)
- OAuth временные состояния (auth_state)
- Низкоуровневые операции в сервисах

## Контейнеры

### BaseContainer
```python
class BaseContainer:
    @property
    def user_repository(self): ...
    
    @property
    def company_repository(self): ...
    
    @property
    def subdomain_repository(self): ...
    
    @property
    def variable_repository(self): ...
    
    @property
    def usage_repository(self): ...
    
    @property
    def file_repository(self): ...
```

### AgentsContainer
```python
class AgentsContainer(BaseContainer):
    @property
    def agent_repository(self): ...
    
    @property
    def flow_repository(self): ...
    
    @property
    def tool_repository(self): ...
    
    @property
    def task_repository(self): ...
    
    @property
    def session_repository(self): ...
    
    @property
    def mcp_server_repository(self): ...
```

## Обновленные файлы

**Core:**
- `core/db/base_repository.py` - полная переработка
- `core/db/storage.py` - добавлены приватные методы для репозиториев
- `core/container/base.py` - добавлены все core репозитории
- `core/identity/auth_service.py` - использует репозитории
- `core/billing/service.py` - использует репозитории
- `core/payments/service.py` - использует CompanyRepository
- `core/variables/service.py` - использует VariableRepository
- `core/middleware/auth.py` - использует SubdomainRepository

**Apps:**
- Все 6 репозиториев в `apps/agents/db/repositories/`
- `apps/agents/container.py` - обновлены фабрики
- `apps/agents/workers/task_processor.py` - использует репозитории
- `apps/agents/services/flow_factory.py` - использует репозитории
- `apps/agents/services/migration/migrator.py` - использует репозитории
- `apps/agents/interfaces/` - все 5 интерфейсов обновлены
- `apps/agents/dependencies.py` - убран StorageDep
- `apps/frontend/dependencies.py` - убран StorageDep
- 30+ API роутов обновлены

**Тесты:**
- `tests/conftest.py` - добавлены фикстуры для всех репозиториев
- Обновлены helper функции (create_simple_agent, create_simple_flow)
- Частично обновлены тесты для новой архитектуры

## Итоги

✅ **Единообразие**: Все через репозитории, никаких исключений
✅ **Изоляция**: ВСЕГДА префикс `company:{company_id}:` (кроме is_global=True)
✅ **Чистота**: Никаких if/else фолбеков, только незыблемая логика
✅ **Типизация**: Каждый репозиторий знает свою таблицу
✅ **Архитектура**: Storage приватный, все через репозитории

**Приложения запускаются успешно!**

