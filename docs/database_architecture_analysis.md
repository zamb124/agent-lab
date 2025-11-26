# Анализ архитектуры работы с БД и предложения по улучшению

## Текущее состояние

### Принцип изоляции по компаниям

**Главный принцип**: Все данные делятся на компании через префикс `company:{company_id}:` в ключах.

**Механизм изоляции**:
- `Storage._get_company_key()` автоматически добавляет префикс `company:{company_id}:` к ключам
- Исключения: префиксы `company:`, `subdomain:`, `auth_session:`, `auth_state:`, `web_notification:`, `media_group:` - глобальные
- Можно отключить через `force_global=True`

### Текущие проблемы

#### 1. Несогласованность в изоляции

**Проблема**: Разные сущности используют разные подходы к изоляции:

| Сущность | Изоляция | Подход | Проблема |
|----------|----------|--------|----------|
| `agent:`, `flow:`, `tool:` | ✅ Автоматическая | Storage добавляет `company:{company_id}:` | ✅ Правильно |
| `task:` | ❌ Глобальная | `force_global=True` в BaseRepository | ❌ Должна быть изолирована |
| `session:` | ❌ Глобальная | Использует shared_storage, но не force_global явно | ❌ Должна быть изолирована |
| `mcp_server:` | ⚠️ Ручная | Вручную добавляет `company_id` в ключ | ⚠️ Дублирует логику Storage |
| `user:`, `company:` | ❌ Глобальная | `force_global=True` | ✅ Правильно (глобальные) |
| `var:` | ✅ Автоматическая | Storage добавляет `company:{company_id}:` | ✅ Правильно |

#### 2. TABLE_ROUTING не используется для изоляции

**Проблема**: В `TABLE_ROUTING` есть поле `company_specific`, но оно не используется для изоляции:

```python
TABLE_ROUTING = {
    "agent:": {"table": "storage", "company_specific": False},  # Не используется!
    "task:": {"table": "tasks", "company_specific": False},    # Не используется!
    ...
}
```

**Текущее поведение**: `company_specific` влияет только на имя таблицы (`{company_id}_table`), но это не используется.

#### 3. Смешение service БД и shared БД

**Проблема**: Нет четкого правила, какие сущности в какой БД:

| Репозиторий | БД | Обоснование |
|-------------|----|-------------|
| `AgentRepository` | service БД | ✅ Правильно |
| `FlowRepository` | service БД | ✅ Правильно |
| `ToolRepository` | service БД | ✅ Правильно |
| `TaskRepository` | shared БД | ⚠️ Почему shared? |
| `SessionRepository` | shared БД | ⚠️ Почему shared? |
| `MCPServerRepository` | service БД | ✅ Правильно |

**Вопрос**: Почему `task` и `session` в shared БД, а не в service БД?

#### 4. Дублирование логики изоляции

**Проблема**: `MCPServerRepository` вручную добавляет `company_id` в ключ:

```python
def _get_key(self, server_id: str, company_id: Optional[str] = None) -> str:
    if company_id is None:
        company_id = self._get_company_id_from_context()
    return f"mcp_server:{company_id}:{server_id}"  # Вручную!
```

Это дублирует логику `Storage._get_company_key()`, которая автоматически добавляет `company:{company_id}:`.

#### 5. Нет единого правила для force_global

**Проблема**: `force_global` используется хаотично:

- `TaskRepository` - всегда `force_global=True` (в `_get_typed`, `_set_typed`)
- `UserRepository`, `CompanyRepository` - всегда `force_global=True` (правильно, они глобальные)
- `SessionRepository` - не использует `force_global` явно, но использует shared_storage

**Вопрос**: Должны ли `task` и `session` быть изолированы по компаниям?

## Предложения по улучшению

### 1. Четкое разделение: Company-Specific vs Global

**Правило**: Определить, какие сущности изолированы по компаниям, а какие глобальные.

#### Company-Specific (изолированы по компаниям):
- ✅ `agent:` - агенты компании
- ✅ `flow:` - flows компании
- ✅ `tool:` - инструменты компании
- ✅ `mcp_server:` - MCP серверы компании
- ✅ `var:` - переменные компании
- ❓ `task:` - задачи компании? (сейчас глобальные)
- ❓ `session:` - сессии компании? (сейчас глобальные)

#### Global (общие для всех компаний):
- ✅ `user:` - пользователи (могут быть в нескольких компаниях)
- ✅ `company:` - компании (метаданные)
- ✅ `subdomain:` - маппинг поддоменов
- ✅ `auth_session:`, `auth_state:` - сессии аутентификации
- ✅ `otel:` - трейсинг (глобальный)

### 2. Унифицировать подход к изоляции

**Решение**: Использовать единый механизм через `Storage._get_company_key()`:

1. **Убрать ручную логику из MCPServerRepository**:
   ```python
   # Было:
   def _get_key(self, server_id: str) -> str:
       company_id = self._get_company_id_from_context()
       return f"mcp_server:{company_id}:{server_id}"
   
   # Стало:
   def _get_key(self, server_id: str) -> str:
       return f"mcp_server:{server_id}"  # Storage сам добавит company:
   ```

2. **Добавить изоляцию для task и session** (если нужно):
   ```python
   # TaskRepository - убрать force_global
   async def get(self, task_id: str) -> Optional[TaskConfig]:
       return await self._get_typed(task_id)  # Без force_global
   
   # SessionRepository - убрать force_global
   async def get(self, session_id: str) -> Optional[SessionConfig]:
       return await self._get_typed(session_id)  # Без force_global
   ```

### 3. Использовать TABLE_ROUTING для изоляции

**Решение**: Использовать `company_specific` для явного указания изоляции:

```python
TABLE_ROUTING = {
    # Company-specific (изолированы)
    "agent:": {"table": "storage", "company_specific": True},
    "flow:": {"table": "storage", "company_specific": True},
    "tool:": {"table": "storage", "company_specific": True},
    "mcp_server:": {"table": "storage", "company_specific": True},
    "var:": {"table": "variables", "company_specific": True},
    "task:": {"table": "tasks", "company_specific": True},  # Если изолируем
    "session:": {"table": "storage", "company_specific": True},  # Если изолируем
    
    # Global (общие)
    "user:": {"table": "users", "company_specific": False},
    "company:": {"table": "storage", "company_specific": False},
    "subdomain:": {"table": "storage", "company_specific": False},
    "auth_session:": {"table": "users", "company_specific": False},
    "auth_state:": {"table": "users", "company_specific": False},
    "task:": {"table": "tasks", "company_specific": False},  # Если глобальные
    "otel:": {"table": "otel_spans", "company_specific": False},
    
    "_default": {"table": "storage", "company_specific": True},  # По умолчанию изолируем
}
```

**Логика**: `Storage._get_company_key()` должен проверять `company_specific` из `TABLE_ROUTING`:

```python
def _get_company_key(self, key: str, force_global: bool = False) -> tuple[str, Optional[str]]:
    if force_global:
        return key, None
    
    # Проверяем TABLE_ROUTING
    routing_config = self._get_routing_config(key)
    if routing_config and not routing_config.get("company_specific", True):
        return key, None  # Глобальный
    
    # Автоматическая изоляция
    if self.get_context_func:
        context = self.get_context_func()
        if context and context.active_company:
            company_id = context.active_company.company_id
            return f"company:{company_id}:{key}", company_id
    
    return key, None
```

### 4. Четкое разделение service БД и shared БД

**Правило**: Определить, какие сущности в какой БД.

#### Service БД (apps/agents):
- `agent:`, `flow:`, `tool:`, `mcp_server:` - бизнес-логика сервиса

#### Shared БД (core):
- `user:`, `company:`, `subdomain:` - общие данные
- `auth_session:`, `auth_state:` - аутентификация
- `task:`, `session:` - если они глобальные (не изолированы)
- `var:` - переменные (если изолированы, то в service БД?)

**Вопрос**: Где должны быть `task` и `session`?
- Если изолированы по компаниям → service БД
- Если глобальные → shared БД

### 5. Упростить BaseRepository

**Решение**: Убрать специальную логику для `task` из `BaseRepository`:

```python
# Было:
async def _get_typed(self, entity_id: str, **kwargs) -> Optional[T]:
    get_kwargs = {}
    prefix = self._get_prefix().rstrip(':')
    if prefix == 'task':
        get_kwargs['force_global'] = True  # Специальная логика!
    ...

# Стало:
async def _get_typed(self, entity_id: str, **kwargs) -> Optional[T]:
    # Нет специальной логики, все через TABLE_ROUTING
    ...
```

### 6. Документировать правила изоляции

**Решение**: Создать четкую документацию:

```markdown
## Изоляция по компаниям

### Company-Specific (изолированы):
- `agent:`, `flow:`, `tool:`, `mcp_server:`, `var:`
- Ключи: `company:{company_id}:agent:{agent_id}`
- Автоматическая изоляция через Storage

### Global (общие):
- `user:`, `company:`, `subdomain:`, `auth_session:`, `auth_state:`, `otel:`
- Ключи: `user:{user_id}` (без префикса компании)
- Используют `force_global=True` в репозиториях
```

## План миграции

### Этап 1: Унификация MCPServerRepository
1. Убрать ручную логику `company_id` из `MCPServerRepository._get_key()`
2. Использовать стандартный подход через Storage
3. Обновить все вызовы `MCPServerRepository.get/set/delete` (убрать `company_id` параметр)

### Этап 2: Решить вопрос с task и session
1. Определить: должны ли `task` и `session` быть изолированы?
2. Если да - убрать `force_global=True` из `TaskRepository` и `SessionRepository`
3. Если нет - оставить как есть, но документировать

### Этап 3: Использовать TABLE_ROUTING для изоляции
1. Обновить `TABLE_ROUTING` с правильными `company_specific` флагами
2. Обновить `Storage._get_company_key()` для использования `TABLE_ROUTING`
3. Убрать `force_global` из репозиториев, где возможно

### Этап 4: Упростить BaseRepository
1. Убрать специальную логику для `task` из `BaseRepository`
2. Все через `TABLE_ROUTING`

### Этап 5: Документировать
1. Обновить документацию по изоляции
2. Добавить примеры использования

## Вопросы для обсуждения

1. **Должны ли `task` и `session` быть изолированы по компаниям?**
   - Сейчас они глобальные (`force_global=True`)
   - Если изолируем - нужно убрать `force_global` и обновить логику

2. **Где должны быть `task` и `session` - в service БД или shared БД?**
   - Сейчас `task` и `session` в shared БД
   - Если изолируем - логично перенести в service БД

3. **Должны ли `var:` быть в service БД или shared БД?**
   - Сейчас они изолированы по компаниям
   - Если изолированы - логично в service БД

4. **Нужна ли физическая изоляция таблиц (`{company_id}_table`)?**
   - Сейчас `company_specific` не используется для физической изоляции
   - Только логическая изоляция через префикс ключа

## Рекомендации

1. ✅ **Унифицировать MCPServerRepository** - убрать ручную логику
2. ✅ **Использовать TABLE_ROUTING для изоляции** - явное указание
3. ❓ **Решить вопрос с task и session** - изолировать или оставить глобальными?
4. ✅ **Упростить BaseRepository** - убрать специальную логику
5. ✅ **Документировать правила** - четкие правила изоляции

