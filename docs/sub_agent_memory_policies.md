# Политики памяти для субагентов

## Обзор

Каждый родительский агент может управлять политикой памяти для своих субагентов. Политика определяет, как обрабатывается состояние (store и messages) при вызове субагента.

## Типы политик

### 1. ISOLATED (по умолчанию)

Каждый вызов субагента создает новую сессию с новой памятью.

**Характеристики:**
- Каждый вызов: новая `sub_session_id` (наследуется от родителя)
- Память: полностью изолирована, каждый вызов начинается с пустого состояния
- Возврат: только результат работы субагента

**Пример:**
```python
# Первый вызов
sub_session_id = "parent:sub:agent:a1b2c3d4"  # Новая сессия
# Второй вызов
sub_session_id = "parent:sub:agent:e5f6g7h8"  # Еще одна новая сессия
```

**Использование:**
```python
ToolReference(
    tool_id="agent:app.agents.weather.agent.WeatherAgent",
    memory_policy=SubAgentMemoryPolicy.ISOLATED  # По умолчанию
)
```

### 2. ACCUMULATED

Субагент накапливает память между вызовами.

**Характеристики:**
- Первый вызов: новая `sub_session_id`
- Последующие вызовы: используется та же `sub_session_id`
- Память: накапливается между вызовами (store и messages сохраняются)
- Возврат: только результат работы субагента

**Пример:**
```python
# Первый вызов
sub_session_id = "parent:sub:agent:accumulated:a1b2c3d4"  # Новая сессия
# Второй вызов
sub_session_id = "parent:sub:agent:accumulated:a1b2c3d4"  # Та же сессия (память сохраняется)
```

**Использование:**
```python
ToolReference(
    tool_id="agent:app.agents.search.agent.SearchAgent",
    memory_policy=SubAgentMemoryPolicy.ACCUMULATED
)
```

### 3. SNAPSHOT

Родитель копирует текущую память при каждом вызове субагента.

**Характеристики:**
- Каждый вызов: новая `sub_session_id`, но с копией текущего store родителя
- Память: субагент получает snapshot родительского store при вызове
- Возврат: только результат работы субагента (store субагента не возвращается)

**Пример:**
```python
# Родитель: store = {"user_id": "123", "query": "test"}
# Вызов субагента с SNAPSHOT
sub_session_id = "parent:sub:agent:snapshot:a1b2c3d4"
sub_state["store"] = {"user_id": "123", "query": "test"}  # Копия родителя

# Субагент работает, изменяет store
# При возврате: только результат, store родителя не изменяется
```

**Использование:**
```python
ToolReference(
    tool_id="agent:app.agents.analyzer.agent.AnalyzerAgent",
    memory_policy=SubAgentMemoryPolicy.SNAPSHOT
)
```

### 4. SHARED

Родитель и субагент работают в одной памяти.

**Характеристики:**
- Сессия: используется `session_id` родителя
- Память: полностью общая (store и messages)
- Возврат: только результат работы субагента
- Изменения: изменения store субагента видны родителю сразу

**Пример:**
```python
# Родитель: session_id = "parent_session"
# Вызов субагента с SHARED
sub_session_id = "parent_session"  # Та же сессия!

# Субагент изменяет store
# Родитель сразу видит изменения
```

**Использование:**
```python
ToolReference(
    tool_id="agent:app.agents.processor.agent.ProcessorAgent",
    memory_policy=SubAgentMemoryPolicy.SHARED
)
```

## Где определяется политика

Политика определяется в `ToolReference` для агента-инструмента:

```python
ToolReference(
    tool_id="agent:app.agents.weather.agent.WeatherAgent",
    memory_policy=SubAgentMemoryPolicy.ACCUMULATED,
    # ... другие поля
)
```

**По умолчанию:** `SubAgentMemoryPolicy.ISOLATED`

## Реализация

### 1. Enum политик

```python
class SubAgentMemoryPolicy(str, Enum):
    ISOLATED = "isolated"      # По умолчанию
    ACCUMULATED = "accumulated"
    SNAPSHOT = "snapshot"
    SHARED = "shared"
```

### 2. Класс управления памятью

`SubAgentMemoryManager` в `app/core/sub_agent_memory.py`:
- Генерирует правильный `sub_session_id` на основе политики
- Подготавливает состояние для субагента
- Обрабатывает возврат результата

### 3. Интеграция в BaseAgent.as_tool

`as_tool` использует `SubAgentMemoryManager` для:
- Определения `sub_session_id` по политике
- Подготовки начального состояния субагента
- Обработки возвращаемого результата

## Важные замечания

1. **Каждый родитель управляет своей политикой** - политика определяется в `ToolReference` родительского агента, а не в конфиге субагента.

2. **Interrupt контекст** - при `AgentInterrupt` используется стандартная логика восстановления независимо от политики.

3. **SHARED требует осторожности** - изменения store видны сразу, что может привести к неожиданному поведению.

4. **SNAPSHOT не копирует messages** - копируется только store, messages остаются изолированными.

