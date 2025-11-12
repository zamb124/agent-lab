---
trigger: model_decision
description: "Правила работы с LangGraph"
globs:
---
# Правила работы с LangGraph

## State как единое хранилище

Используй `State` из `app/core/state.py` для всех агентов:
- `messages` - история диалога
- `store` - сессионное хранилище для данных между запросами
- `task_id`, `session_id`, `user_id` - метаданные

<good_example>
from app.core.state import State

def my_node(state: State) -> State:
    state["store"]["user_data"] = "some_value"
    return state
</good_example>

## Запрос данных у пользователя

Используй `ask_user` из `app/tools/standard.py`:
- Вызывает `GraphInterrupt` для приостановки графа
- TaskProcessor отправляет вопрос через Interface
- При ответе граф продолжается с того же места

<good_example>
from app.tools.standard import ask_user

# В агенте
tools = [ask_user]
prompt = """
Если тебе нужна информация от пользователя, используй ask_user:
ask_user("Какой ваш склад?")
"""
</good_example>

## Типы агентов

Поддерживаются два типа агентов:

### 1. ReAct агент
Классический агент с промптом и инструментами:

<good_example>
class MyAgent(BaseAgent):
    agent_id = "my_agent"
    name = "My Agent"
    type = "react"
    prompt = "Ты помощник..."
    tools = [tool1, tool2]
</good_example>

### 2. StateGraph агент
Граф состояний для сложной логики:

<good_example>
class MyAgent(BaseAgent):
    agent_id = "my_graph_agent"
    type = "state_graph"
    graph_definition = GraphDefinition(
        nodes=[...],
        edges=[...],
        entry_point="start"
    )
</good_example>

## Агенты как инструменты

Превращай агенты в инструменты через `as_tool()`:
- Позволяет создавать иерархии агентов
- Supervisor агент может вызывать sub-агентов
- Каждый агент может иметь свои tools и sub-агентов

<good_example>
class SupervisorAgent(BaseAgent):
    agent_id = "supervisor"
    tools = [
        SubAgent1().as_tool(),
        SubAgent2().as_tool(),
        regular_tool
    ]
</good_example>

## Память и история

Используй shared memory:
- Все агенты получают доступ к одному `State`
- История диалога в `state["messages"]`
- Сессионные данные в `state["store"]`
- Не дублируй данные между агентами

<good_example>
# Агент сохраняет
state["store"]["warehouse_id"] = "12345"

# Другой агент читает
warehouse_id = state["store"].get("warehouse_id")
</good_example>

## Checkpointer

Используй PostgreSQL checkpointer для персистентности:
- Автоматически сохраняет состояние графа
- Позволяет возобновлять выполнение после interrupt
- Не используй MemorySaver в production

<good_example>
from app.core.checkpointer import get_checkpointer

checkpointer = await get_checkpointer()
graph = agent.compile_graph(checkpointer=checkpointer)
</good_example>

## Документация

Всегда изучай актуальную документацию LangGraph:
- https://langchain-ai.github.io/langgraph/
- Используй современные паттерны и best practices
- Избегай устаревших подходов
