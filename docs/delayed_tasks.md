# Отложенные задачи (Delayed Tasks)

Система отложенных задач позволяет агентам создавать задачи для автоматического выполнения в будущем.

## Архитектура

### База данных

- **Отдельная таблица `tasks`** для физической изоляции
- **Индексы** на JSONB полях:
  - `status` - для фильтрации по статусу
  - `execute_at` - для отложенных задач
  - `session_id + flow_id` - для поиска по сессии
  - Композитный индекс для ready задач

### Модель TaskConfig

```python
class TaskConfig(BaseModel):
    task_id: str
    flow_id: str
    context: Context
    status: TaskStatus
    input_data: Dict[str, Any]
    
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execute_at: Optional[datetime]  # Когда выполнить (None = сразу)
    skip_agent: bool  # Отправить напрямую без вызова агента
```

### TaskProcessor

Воркер обрабатывает задачи:
- Фильтрует по `status=pending` и `execute_at <= now()`
- Если `skip_agent=True` - отправляет сообщение напрямую без агента
- Если `skip_agent=False` - вызывает агента

## Использование

### Тулы (только для кода)

```python
from app.tools.task.delayed_task_tools import DELAYED_TASK_TOOLS
```

**create_delayed_task(delay_seconds, message?, tool_name?, tool_args?)**
- ВАРИАНТ 1: Текстовое напоминание → `skip_agent=True`
- ВАРИАНТ 2: Вызов тула → `skip_agent=False`

**list_delayed_tasks()** - список задач сессии (is_public=True)

**cancel_delayed_task(task_id)** - отменить задачу

**get_delayed_task_status(task_id)** - проверить статус

### Правильное использование

**✅ ВАРИАНТ 1: Текстовое напоминание (skip_agent=True)**

```python
class OrderProcessingAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS]
    
    prompt = '''
    После создания заказа создай напоминание:
    create_delayed_task(
        delay_seconds=3600,
        message="Напоминание: проверить статус заказа #123"
    )
    '''
```

**✅ ВАРИАНТ 2: Вызов тула (skip_agent=False)**

```python
class AutomationAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS, check_order_status, send_email]
    
    prompt = '''
    После создания заказа запланируй проверку:
    create_delayed_task(
        delay_seconds=86400,
        tool_name="check_order_status",
        tool_args={"order_id": "123", "notify": true}
    )
    
    Через сутки агент автоматически вызовет check_order_status!
    '''
```

**❌ Неправильно:**

```python
class FAQAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS]  # ❌ Пользователь напишет "напомни" → цикл!
```

### Форматы задач

**ВАРИАНТ 1: message** (skip_agent=True)
- Отправляется как AIMessage напрямую
- БЕЗ вызова агента
- Быстро, для простых напоминаний

**ВАРИАНТ 2: tool_call** (skip_agent=False)
- Агент вызывает указанный тул
- Может выполнить сложную логику
- Для автоматизации бизнес-процессов

**Формат сообщения для message:**

✅ Правильно - контекст/действие:
- "Напоминание: позвонить маме"
- "Напоминание: встреча в 15:00"

❌ Неправильно - текст пользователя:
- "напомни позвонить" → создаст цикл!

## State персистентность

### Глобальное решение для всех тулов

Декоратор `@tool(state_aware=True)` автоматически:
1. Инжектит актуальный `state` и `tool_call_id` в тул
2. Устанавливает state в `context.state` 
3. Если тул модифицирует `state["store"]` → оборачивает в `Command`
4. State сохраняется в checkpointer между вызовами

**Пример:**

```python
@tool(state_aware=True)
def my_custom_tool(key: str, value: str) -> str:
    """Мой тул с автоматической персистентностью"""
    state = get_state()
    
    # Просто модифицируем state
    state["store"][key] = value
    
    # Декоратор автоматически обернет в Command!
    return f"Saved: {key}"
```

## Примеры сценариев

### 1. Текстовое напоминание

```python
# Простое напоминание пользователю
create_delayed_task(
    delay_seconds=3600,
    message="Напоминание: встреча в 15:00"
)
```

### 2. Автоматическая проверка статуса

```python
# Вызов тула через час
create_delayed_task(
    delay_seconds=3600,
    tool_name="check_order_status",
    tool_args={"order_id": "123", "notify_user": True}
)
```

### 3. Follow-up email

```python
# Отправка письма через неделю
create_delayed_task(
    delay_seconds=604800,
    tool_name="send_followup_email",
    tool_args={
        "client_id": "456",
        "template": "followup_after_week",
        "subject": "Как дела с заявкой?"
    }
)
```

### 4. Комбинированный сценарий

```python
class OrderAgent(BaseAgent):
    tools = [DELAYED_TASK_TOOLS, check_status, send_email]
    
    prompt = '''
    После создания заказа:
    
    1. Напоминание пользователю через 10 минут:
       create_delayed_task(600, message="Напоминание: проверьте email")
    
    2. Проверка статуса через час:
       create_delayed_task(3600, tool_name="check_status", tool_args={"order_id": "{order_id}"})
    
    3. Follow-up через день:
       create_delayed_task(86400, tool_name="send_email", tool_args={"template": "followup"})
    '''
```

## Технические детали

### TaskRepository

```python
# Получить готовые к выполнению задачи
pending_tasks = await task_repo.list_pending(limit=10)

# Фильтр: status=pending AND (execute_at IS NULL OR execute_at <= NOW())
```

### Маршрутизация Storage

```python
TABLE_ROUTING = {
    "task:": {"table": "tasks", "company_specific": False},
    ...
}
```

Задачи записываются с `force_global=True` - БЕЗ префикса компании, в глобальную таблицу `tasks`.

## Тестирование

```bash
uv run pytest tests/integration/test_state_persistence.py -v
```

Тест проверяет:
- Создание задачи → запись в БД и state
- Второй вызов → задача загружается из checkpointer
- State персистится между вызовами ✅

