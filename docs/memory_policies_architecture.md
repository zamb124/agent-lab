# Архитектура памяти и политик памяти для субагентов

## Обзор системы

Система управления памятью для субагентов построена на следующих принципах:

1. **Разделение данных:**
   - **Store** - общее хранилище данных для всего flow (все агенты видят один и тот же `store`)
   - **Messages** - история диалога для каждого агента (может быть изолированной или общей)
   - **State** - состояние агента (messages + store + метаданные)

**ОБЩЕЕ ПРАВИЛО ДЛЯ ВСЕХ ПОЛИТИК:**
- **STORE ВСЕГДА ОБЩИЙ** для всех политик памяти!
- Неважно какая политика (ISOLATED, ACCUMULATED, SNAPSHOT, SHARED) - store работает одинаково
- Неважно кто меняет store (родитель или субагент) - изменения видны всем
- Store общий для всего flow, все агенты работают с одним и тем же store

2. **Формат session_id:**
   - Родитель: `{parent_session_id}`
   - Sub-сессия: `{parent_session_id}:sub:{agent_id}:{policy_marker}:{unique_id}`

3. **Политики памяти определяются из формата session_id:**
   - `ISOLATED`: `parent:sub:agent_id:uuid` (по умолчанию, новый ID для каждого вызова)
   - `ACCUMULATED`: `parent:sub:agent_id:accumulated` (один ID для всех вызовов одного субагента)
   - `SNAPSHOT`: `parent:sub:agent_id:snapshot:uuid` (новый ID для каждого вызова)
   - `SHARED`: `parent` (использует session_id родителя)

**Важно**: 
- `agent_id` - это уникальный идентификатор субагента (например, `app.agents.weather.agent.WeatherAgent`)
- Для ACCUMULATED каждый субагент имеет свой собственный накапливаемый session_id
- Если у родителя есть несколько субагентов с ACCUMULATED, у каждого будет свой session_id для накопления памяти

## Типы политик памяти

### 1. ISOLATED (по умолчанию)

**Характеристики:**
- Каждый вызов субагента создает новую сессию с уникальным ID
- Messages полностью изолированы (каждый вызов начинается с пустого диалога)
- **Store общий** (для всех политик store работает одинаково - общий для всего flow)
- После завершения возвращается только результат (ToolMessage)

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:{unique_uuid}
```

**Алгоритм работы:**

1. **Вызов субагента:**
   - Генерируется новый `sub_session_id = parent:sub:agent:uuid`
   - Загружается состояние: `messages = []` (пустое), `store = parent.store` (общий)
   - Сохраняется состояние родителя перед вызовом

2. **Выполнение:**
   - Субагент работает с изолированными `messages` и общим `store`
   - Если interrupt: сохраняется состояние субагента и `interrupt_context` в родителе

3. **Interrupt (ask_user):**
   - Состояние субагента сохраняется в БД с `sub_session_id`
   - В родителе сохраняется `interrupt_context` с `sub_session_id`, `sub_agent_id`, `tool_call_id`
   - Родитель останавливается, ожидая ответ пользователя

4. **Resume после interrupt:**
   - Загружается состояние родителя (все сообщения от начала диалога)
   - Загружается состояние субагента по `sub_session_id` из `interrupt_context`
   - Добавляется ответ пользователя в `messages` субагента
   - Субагент продолжает работу с сохраненными `messages`
   - После завершения: результат добавляется в родителя как ToolMessage

5. **Завершение:**
   - Store общий (как и для всех политик!), поэтому изменения уже видны всем
   - Messages субагента не возвращаются родителю (только результат)
   - Состояние субагента НЕ сохраняется в БД (для следующего вызова будет новый)

**Пример:**
```python
# Первый вызов
sub_session_id = "parent_123:sub:agent_abc:uuid1"
messages = []  # Пустое
store = parent.store  # Общий

# Субагент: ask_user("Как тебя зовут?") → interrupt
# Сохраняется: sub_state с messages=[...], store={...}
# Сохраняется в родителе: interrupt_context = {sub_session_id, ...}

# Resume
# Загружается: parent_state (все сообщения), sub_state (сохраненные messages)
# Добавляется: HumanMessage("Иван")
# Субагент продолжает работу

# Завершение
# Родитель получает: ToolMessage(content="Имя получено: Иван")
# Store обновляется в родителе

# Второй вызов (новый вызов того же субагента)
sub_session_id = "parent_123:sub:agent_abc:uuid2"  # Новый ID!
messages = []  # Снова пустое
store = parent.store  # Общий (но уже с изменениями от первого вызова)
```

---

### 2. ACCUMULATED

**Характеристики:**
- Все вызовы **одного и того же субагента** используют один и тот же `sub_session_id`
- **Каждый субагент имеет свой уникальный session_id**: `{parent_id}:sub:{agent_id}:accumulated`
- Если у родителя есть несколько субагентов с ACCUMULATED, у каждого свой накапливаемый session_id
- Messages накапливаются между вызовами (диалог продолжается)
- **Store общий** (для всех политик store работает одинаково - общий для всего flow)
- После завершения возвращается только результат (ToolMessage)

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:accumulated
```

**Важно**: 
- `agent_id` - это уникальный идентификатор субагента (например, `app.agents.weather.agent.WeatherAgent`)
- Каждый субагент имеет свой собственный `sub_session_id` для накопления памяти
- Если родитель вызывает `WeatherAgent` и `OrderAgent` с ACCUMULATED, у каждого будет свой session_id:
  - `parent:sub:app.agents.weather.agent.WeatherAgent:accumulated`
  - `parent:sub:app.agents.order.agent.OrderAgent:accumulated`

**Алгоритм работы:**

1. **Первый вызов субагента:**
   - Генерируется фиксированный `sub_session_id = parent:sub:agent:accumulated`
   - Загружается состояние: если есть сохраненные `messages` - используем их, иначе `messages = []`
   - `store = parent.store` (общий)
   - Сохраняется состояние родителя перед вызовом

2. **Выполнение:**
   - Субагент работает с накопленными `messages` и общим `store`
   - Если interrupt: сохраняется состояние субагента с текущими `messages`

3. **Interrupt (ask_user):**
   - Состояние субагента сохраняется в БД с `sub_session_id` (включая все `messages`)
   - В родителе сохраняется `interrupt_context` с `sub_session_id`
   - Родитель останавливается

4. **Resume после interrupt:**
   - Загружается состояние родителя
   - Загружается состояние субагента по `sub_session_id` (с накопленными `messages`)
   - Добавляется ответ пользователя в `messages` субагента
   - Субагент продолжает работу с накопленными `messages`

5. **Завершение:**
   - Store общий (как и для всех политик!), поэтому изменения уже видны всем
   - Messages субагента сохраняются в БД для следующего вызова
   - Состояние субагента сохраняется с обновленным `store` из родителя
   - Родитель получает только ToolMessage

6. **Второй вызов (новый запрос к тому же субагенту):**
   - Используется тот же `sub_session_id = parent:sub:agent:accumulated`
   - Загружаются сохраненные `messages` от предыдущих вызовов
   - Добавляется новое сообщение от родителя
   - Субагент продолжает диалог с накопленными `messages`

**Работа с store для ACCUMULATED:**

**Важно**: Store для ACCUMULATED работает так же, как и для всех других политик - он общий!

Особенность только в сохранении состояния:
- Когда субагент изменяет store через `session_set`, изменения сразу видны всем (store общий!)
- После завершения субагента:
  1. `store.ensure_saved()` - сохраняет изменения субагента в БД (это происходит для всех политик)
  2. Загружаются актуальные данные из БД: `updated_store_data = load_store(parent_store_id)`
  3. Создается новый `StoreProxy` с актуальными данными
  4. Обновляется `parent_state["store"]` и `parent_state["store_id"]`
  5. Сохраняется `parent_state` (но store НЕ перезаписывается в `_save_state_direct`, так как это ACCUMULATED)

**Это не меняет того факта, что store общий для всех политик!**

**Пример:**
```python
# Родитель имеет два субагента с ACCUMULATED:
# - WeatherAgent: agent_id = "app.agents.weather.agent.WeatherAgent"
# - OrderAgent: agent_id = "app.agents.order.agent.OrderAgent"

# Первый вызов WeatherAgent
weather_session_id = "parent_123:sub:app.agents.weather.agent.WeatherAgent:accumulated"
messages = []  # Пустое (первый раз)
store = parent.store  # Общий

# Субагент: session_set("city", "Москва"), ask_user("Страна?") → interrupt
# Сохраняется: sub_state с messages=[...], store={"city": "Москва"}

# Resume
# Загружается: sub_state с messages=[...], store={"city": "Москва"}
# Добавляется: HumanMessage("Россия")
# Субагент: session_set("country", "Россия")
# Store обновляется: store={"city": "Москва", "country": "Россия"}

# Завершение
# Store общий, поэтому изменения уже видны: parent.store = {"city": "Москва", "country": "Россия"}
# Messages сохраняются: weather_state.messages = [все сообщения от начала]

# Второй вызов WeatherAgent (новый запрос)
weather_session_id = "parent_123:sub:app.agents.weather.agent.WeatherAgent:accumulated"  # Тот же ID!
messages = [все сообщения от первого вызова WeatherAgent]  # Продолжение диалога WeatherAgent
store = parent.store  # Общий (с "city" и "country")

# Первый вызов OrderAgent (другой субагент)
order_session_id = "parent_123:sub:app.agents.order.agent.OrderAgent:accumulated"  # Свой ID!
messages = []  # Пустое (первый раз для OrderAgent)
store = parent.store  # Общий (с "city" и "country" от WeatherAgent)

# Второй вызов OrderAgent
order_session_id = "parent_123:sub:app.agents.order.agent.OrderAgent:accumulated"  # Тот же ID OrderAgent
messages = [все сообщения от первого вызова OrderAgent]  # Продолжение диалога OrderAgent
store = parent.store  # Общий (со всеми изменениями)
```

**Важно**: 
- У каждого субагента свой собственный накапливаемый session_id
- WeatherAgent накапливает свою память независимо от OrderAgent
- Но store общий для всех (включая родителя и всех субагентов)

---

### 3. SNAPSHOT

**Характеристики:**
- Каждый вызов создает новую сессию с уникальным ID (но с маркером snapshot)
- Messages изолированы (каждый вызов начинается с пустого диалога)
- **Store общий** (для всех политик store работает одинаково - общий для всего flow)
- После завершения возвращается только результат (ToolMessage)

**Важно**: Несмотря на название "snapshot", store НЕ копируется - он общий для всех, как и для других политик!

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:snapshot:{unique_uuid}
```

**Алгоритм работы:**

1. **Вызов субагента:**
   - Генерируется новый `sub_session_id = parent:sub:agent:snapshot:uuid`
   - **Store общий** (как и для всех политик - общий для всего flow)
   - Messages: `messages = []` (пустое)

2. **Выполнение:**
   - Субагент работает с изолированными `messages` и общим `store`
   - Изменения в store видны всем (store общий)

3. **Interrupt:**
   - Состояние субагента сохраняется с общим store
   - В родителе сохраняется `interrupt_context`

4. **Resume:**
   - Загружается состояние субагента с общим store
   - Субагент продолжает работу

5. **Завершение:**
   - Состояние субагента НЕ сохраняется в БД
   - Родитель получает только ToolMessage
   - Store общий, поэтому изменения уже видны всем

**Пример:**
```python
# Первый вызов
sub_session_id = "parent_123:sub:agent_abc:snapshot:uuid1"
messages = []  # Пустое
store = parent.store  # Общий (как и для всех политик)

# Субагент изменяет store: store = {"new": "value"}
# Родитель видит изменения (store общий)

# Завершение
# Store уже общий, никакой синхронизации не требуется
```

---

### 4. SHARED

**Характеристики:**
- Субагент использует тот же `session_id` что и родитель
- Messages и store полностью общие (один state для всех)
- **Store общий** (для всех политик store работает одинаково - общий для всего flow)
- Субагент работает напрямую в состоянии родителя

**Формат session_id:**
```
{parent_session_id}  # Тот же что у родителя
```

**Алгоритм работы:**

1. **Вызов субагента:**
   - Используется `sub_session_id = parent_session_id` (тот же ID)
   - Загружается состояние родителя: `state = parent_state.copy()`
   - Субагент работает в том же state

2. **Выполнение:**
   - Все изменения (messages, store) сразу видны родителю
   - Это один и тот же state объект
   - Store общий (как и для всех политик!)

3. **Interrupt:**
   - Состояние сохраняется как для родителя (один state)

4. **Resume:**
   - Загружается общее состояние
   - Субагент продолжает работу

5. **Завершение:**
   - Все изменения уже в родительском state
   - Никакой синхронизации не требуется

**Пример:**
```python
# Вызов
sub_session_id = "parent_123"  # Тот же ID!
state = parent_state  # Один и тот же state

# Субагент добавляет message
state["messages"].append(...)
# Родитель сразу видит это сообщение

# Субагент изменяет store
state["store"]["key"] = "value"
# Родитель сразу видит это изменение
```

---

## Работа с interrupt

### Общий алгоритм interrupt

1. **Когда происходит interrupt (ask_user):**
   ```python
   # В субагенте
   raise AgentInterrupt("Вопрос пользователю")
   ```

2. **Обработка в agent_runner.py:**
   ```python
   except AgentInterrupt as interrupt:
       session_id = state.get("session_id")
       saved_state = await state_manager.load_state(session_id)
       
       # Для ACCUMULATED сохраняем состояние субагента
       if policy == ACCUMULATED:
           await state_manager.save_state(session_id, saved_state)
       
       raise interrupt
   ```

3. **Обработка в as_tool (BaseAgent):**
   ```python
   except AgentInterrupt as interrupt:
       # Для ACCUMULATED сохраняем состояние субагента перед interrupt
       if policy == ACCUMULATED:
           sub_agent_state = get_state()
           await state_manager.save_state_for_sub_agent(...)
       
       # Сохраняем interrupt_context в родителе
       state_to_save = get_state()  # Текущее состояние родителя
       state_to_save["interrupt_context"] = {
           "type": "tool_call",
           "sub_agent_id": ...,
           "sub_session_id": ...,
           "tool_call_id": ...,
           "interrupt_message": interrupt.value
       }
       await state_manager.save_state(parent_session_id, state_to_save)
       raise interrupt
   ```

4. **Resume после interrupt (BaseAgent.ainvoke):**
   ```python
   interrupt_context = saved_state.get("interrupt_context")
   if interrupt_context and interrupt_context.get("type") == "tool_call":
       # Загружаем состояние субагента
       sub_result = await self._resume_nested_sub_agent(saved_state, input_data, ...)
       
       # Добавляем ToolMessage в родителя
       tool_message = ToolMessage(...)
       saved_state["messages"] = saved_state["messages"] + [tool_message]
       await state_manager.save_state(session_id, saved_state)
       
       # Продолжаем работу родителя
       return await self.ainvoke(saved_state, config)
   ```

### Специфика для каждой политики

#### ISOLATED + interrupt
- При interrupt: состояние субагента сохраняется в БД (для resume)
- При resume: загружается сохраненное состояние субагента
- После завершения: состояние субагента НЕ сохраняется (для следующего вызова будет новый)

#### ACCUMULATED + interrupt
- При interrupt: состояние субагента обязательно сохраняется в БД (включая все messages)
- При resume: загружается сохраненное состояние с накопленными messages
- Store общий (как и для всех политик!), поэтому изменения уже видны всем
- После завершения: состояние субагента сохраняется для следующего вызова

#### SNAPSHOT + interrupt
- При interrupt: состояние субагента сохраняется с общим store (как и для всех политик)
- При resume: загружается сохраненное состояние
- После завершения: состояние субагента НЕ сохраняется

#### SHARED + interrupt
- При interrupt: сохраняется общее состояние (один state для родителя и субагента)
- При resume: загружается общее состояние
- После завершения: никакой синхронизации не требуется

---

## Работа с store

### ОБЩЕЕ ПРАВИЛО ДЛЯ ВСЕХ ПОЛИТИК

**STORE ВСЕГДА ОБЩИЙ** для всех политик памяти!
- Неважно какая политика (ISOLATED, ACCUMULATED, SNAPSHOT, SHARED) - store работает одинаково
- Неважно кто меняет store (родитель или субагент) - изменения видны всем
- Store общий для всего flow, все агенты работают с одним и тем же store

### Хранение store

Store всегда хранится в таблице `stores` по `store_id`:
- Для родителя: `store_id = session_id`
- Для sub-сессий: `store_id = parent_session_id` (наследуется от родителя)

### StoreProxy

`StoreProxy` - это обертка над словарем, которая:
- Автоматически сохраняет изменения в БД при изменении через `_dirty` флаг
- Метод `ensure_saved()` гарантирует сохранение в БД
- Метод `refresh()` загружает актуальные данные из БД

### Синхронизация store для всех политик

**Для всех политик (ISOLATED, ACCUMULATED, SNAPSHOT, SHARED):**
- Store общий, поэтому изменения сразу видны всем
- `StoreProxy.ensure_saved()` автоматически сохраняет изменения в БД
- После завершения субагента может потребоваться `parent_store.refresh()` для обновления из БД

**Особенность для ACCUMULATED:**
- При сохранении `parent_state` store НЕ перезаписывается в `_save_state_direct` (проверка на ACCUMULATED)
- Это нужно, чтобы не перезаписать store старыми данными из `parent_state`
- Store уже сохранен через `StoreProxy.ensure_saved()`, поэтому перезапись не нужна

---

## Важные моменты

### 1. Сохранение состояния родителя перед вызовом субагента

Для правильной работы interrupt важно сохранить состояние родителя перед вызовом субагента:

```python
# В as_tool, перед вызовом субагента
await state_manager.save_state(parent_session_id, parent_state)
```

Это гарантирует, что при resume у родителя будут все сообщения от начала диалога.

### 2. Определение политики из session_id

Политика определяется из формата `session_id`:

```python
def _detect_memory_policy(self, session_id: str) -> Optional[SubAgentMemoryPolicy]:
    if ":sub:" not in session_id:
        return None
    
    parts = session_id.split(":")
    if len(parts) >= 4 and parts[3] == "accumulated":
        return SubAgentMemoryPolicy.ACCUMULATED
    elif len(parts) >= 4 and parts[3] == "snapshot":
        return SubAgentMemoryPolicy.SNAPSHOT
    
    return SubAgentMemoryPolicy.ISOLATED
```

### 3. Не перезаписывать store для ACCUMULATED

В `_save_state_direct` для ACCUMULATED не перезаписываем store в БД:

```python
async def _save_state_direct(self, session_id: str, state: State) -> None:
    policy = self._detect_memory_policy(session_id)
    
    if policy == SubAgentMemoryPolicy.ACCUMULATED:
        store = state.get("store")
        if isinstance(store, StoreProxy):
            await store.ensure_saved()  # Только сохраняем, не перезаписываем
    else:
        # Для других политик перезаписываем store из state
        ...
```

Это важно, чтобы не потерять изменения, сделанные субагентом в общий store.

---

## Примеры использования

### Пример 1: ISOLATED (по умолчанию)

```python
# Родитель вызывает субагента
sub_result = await sub_agent.ainvoke({
    "messages": [HumanMessage("Привет")],
    "session_id": "parent:sub:agent:uuid1"
})

# Субагент: новый session_id, пустые messages, общий store
# После завершения: только ToolMessage возвращается родителю
```

### Пример 2: ACCUMULATED

```python
# Первый вызов
sub_result = await sub_agent.ainvoke({
    "messages": [HumanMessage("Сохрани city=Москва")],
    "session_id": "parent:sub:agent:accumulated"
})

# Субагент сохраняет city в общий store
# Messages накапливаются

# Второй вызов (новый запрос)
sub_result = await sub_agent.ainvoke({
    "messages": [HumanMessage("Какой city?")],
    "session_id": "parent:sub:agent:accumulated"  # Тот же ID!
})

# Субагент видит сохраненные messages от первого вызова
# Может использовать session_get("city") → "Москва"
```

### Пример 3: Interrupt в ACCUMULATED

```python
# agent_id = "app.agents.weather.agent.WeatherAgent"
# sub_session_id = "parent_123:sub:app.agents.weather.agent.WeatherAgent:accumulated"

# Субагент вызывает ask_user("Страна?")
# → interrupt

# Сохраняется:
# - sub_state с messages=[все сообщения от начала этого субагента]
# - store={"city": "Москва"}
# - interrupt_context в родителе с sub_session_id

# Пользователь отвечает "Россия"

# Resume:
# - Загружается sub_state с накопленными messages этого субагента
# - Добавляется HumanMessage("Россия")
# - Субагент продолжает работу
# - session_set("country", "Россия")
# - Store обновляется: {"city": "Москва", "country": "Россия"}

# Завершение:
# - Store общий, поэтому изменения уже видны всем
# - Messages этого субагента сохраняются для следующего вызова
# - При следующем вызове WeatherAgent: будет использован тот же sub_session_id
# - Загрузятся все накопленные messages этого субагента
```

---

## Заключение

Архитектура памяти для субагентов обеспечивает:
1. Гибкость управления памятью через политики
2. Правильную работу interrupt для всех политик
3. Синхронизацию store между родителем и субагентом
4. Накопление messages для ACCUMULATED политики

Ключевые моменты:
- **STORE ВСЕГДА ОБЩИЙ** для всех политик памяти (ISOLATED, ACCUMULATED, SNAPSHOT, SHARED)!
- Неважно какая политика - store работает одинаково для всех
- Неважно кто меняет store - изменения видны всем агентам в flow
- Messages могут быть изолированными, накапливаемыми или общими (в зависимости от политики)
- Политика определяется из формата session_id
- Для ACCUMULATED каждый субагент имеет свой собственный накапливаемый session_id: `{parent_id}:sub:{agent_id}:accumulated`
- Если у родителя несколько субагентов с ACCUMULATED, у каждого свой независимый накапливаемый session_id, но store общий для всех

