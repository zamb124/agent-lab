# Конфигурация агента (Config)

## Обзор

`config` - это словарь конфигурации, который передается в метод `ainvoke` агента для управления выполнением и персистентностью состояния.

## Структура config

```python
config = {
    "configurable": {
        "thread_id": "session_id_или_thread_id"
    },
    "task_id": "опциональный_id_задачи",
    "session_id": "опциональный_id_сессии"
}
```

### Ключевые поля

- **`configurable.thread_id`** - идентификатор потока выполнения, используется для персистентности состояния в StateManager. Соответствует `session_id` агента.
- **`task_id`** - опциональный идентификатор задачи для отслеживания выполнения.
- **`session_id`** - опциональный идентификатор сессии (альтернативный способ передачи).

## Как строится config

### 1. Автоматическое построение в BaseAgent.ainvoke

Если `config` не передан явно, он создается автоматически на основе `session_id`:

```python
session_id = input_data.get("session_id")
if not session_id:
    context = get_context()
    session_id = context.session_id if context else None

run_config = config or ({"configurable": {"thread_id": session_id}} if session_id else {})
```

**Приоритет получения `session_id`:**
1. Из `input_data.get("session_id")` - явно переданный в `input_data`
2. Из `context.session_id` - из глобального контекста выполнения
3. Автоматическая генерация: `f"agent_{self.config.agent_id}"` - если ничего не найдено

### 2. Явная передача config

Можно передать `config` явно при вызове `ainvoke`:

```python
result = await agent.ainvoke(
    {"messages": [HumanMessage(content="Привет")]},
    config={"configurable": {"thread_id": "my_session_id"}}
)
```

Если `config` передан явно, он используется как есть, автоматическое построение не выполняется.

## Зачем нужен config

### 1. Персистентность состояния (checkpointing)

`config["configurable"]["thread_id"]` используется для:
- Сохранения состояния агента в StateManager (PostgreSQL)
- Загрузки сохраненного состояния при повторном вызове
- Восстановления после `AgentInterrupt`

```python
# StateManager использует thread_id для сохранения/загрузки
state_manager = await get_state_manager()
saved_state = await state_manager.load_state(session_id)  # session_id = thread_id
await state_manager.save_state(session_id, state)
```

### 2. Суммаризация контекста

`ContextWindowManager` использует `thread_id` для обновления checkpoint при суммаризации длинных диалогов:

```python
# ContextWindowManager требует thread_id для обновления checkpoint
thread_id = config.get("configurable", {}).get("thread_id")
if not thread_id:
    raise ValueError("thread_id обязателен для обновления checkpoint")
```

### 3. Трекинг выполнения

`task_id` может использоваться для отслеживания выполнения агента в рамках задачи.

## Использование в разных сценариях

### Сценарий 1: Вызов агента из Flow

Ноды в StateGraph просто вызывают агента без передачи `config`:

```python
async def calculator_node(state: State) -> State:
    calculator = await factory.get_agent("app.agents.calculator.agent.CalculatorAgent")
    result = await calculator.ainvoke({
        "messages": [HumanMessage(content=original_question)]
        # session_id автоматически берется из context.session_id
    })
    return state
```

`BaseAgent.ainvoke` автоматически создаст `config` на основе `context.session_id`.

### Сценарий 2: Вызов агента как инструмента (sub-agent)

При вызове агента как инструмента в другом агенте, создается уникальная сессия субагента:

```python
# В BaseAgent.as_tool
sub_session_id = f"{parent_session_id}:sub:{agent_id}:{uuid.uuid4()}"
result = await self.ainvoke(
    {"messages": [HumanMessage(content=input_text)], "session_id": sub_session_id},
    config={"configurable": {"thread_id": sub_session_id}}
)
```

### Сценарий 3: Прямой вызов агента

При прямом вызове агента из API или другого места:

```python
# session_id можно передать в input_data или config
result = await agent.ainvoke(
    {"messages": [HumanMessage(content="Привет")], "session_id": "user_session_123"},
    config={"configurable": {"thread_id": "user_session_123"}}
)
```

## Важные моменты

1. **Ноды не должны знать про config** - они просто вызывают `agent.ainvoke(input_data)`, а `config` строится автоматически.

2. **Если `session_id` отсутствует** - агент пытается взять его из контекста, если и там нет - создается новый на основе `agent_id`.

3. **`thread_id` и `session_id` синхронизированы** - `config["configurable"]["thread_id"]` должен соответствовать `session_id` в `input_data`.

4. **Config не обязателен** - если не передан и нет `session_id`, агент выполнится без персистентности (состояние не сохранится).

## Примеры

### Пример 1: Автоматическое создание config

```python
# input_data содержит session_id
result = await agent.ainvoke({
    "messages": [HumanMessage(content="Привет")],
    "session_id": "session_123"
})
# config автоматически создастся: {"configurable": {"thread_id": "session_123"}}
```

### Пример 2: Явная передача config

```python
# config передан явно
result = await agent.ainvoke(
    {"messages": [HumanMessage(content="Привет")]},
    config={"configurable": {"thread_id": "custom_thread_id"}}
)
# Используется переданный config
```

### Пример 3: Без session_id (без персистентности)

```python
# Нет session_id ни в input_data, ни в context
result = await agent.ainvoke({
    "messages": [HumanMessage(content="Привет")]
})
# config = {}, состояние не сохранится
```

