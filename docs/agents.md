# Агенты в Agent Lab

Полное руководство по созданию и управлению агентами на базе LangGraph.

## Оглавление

1. [Архитектура агентов](#архитектура-агентов)
2. [Типы агентов](#типы-агентов)
3. [ReAct агенты](#react-агенты)
4. [StateGraph агенты](#stategraph-агенты)
5. [Миграция агентов](#миграция-агентов)
6. [Агенты как инструменты](#агенты-как-инструменты)
7. [Работа с tools](#работа-с-tools)
8. [Переменные и state](#переменные-и-state)
9. [Примеры](#примеры)

---

## Архитектура агентов

### Database-First подход

Все агенты в Agent Lab следуют принципу **Database-First**:

```
Код агента (Python класс)
    ↓ миграция
Конфигурация в БД (AgentConfig)
    ↓ фабрика
Живой экземпляр агента (LangGraph граф)
```

**Ключевые принципы:**
- Код определяет только **поведение** (prompt, логика графа)
- БД хранит **конфигурацию** (name, tools, параметры)
- После миграции агенты работают **только из БД**
- Агенты из кода и UI **идентичны**

### Базовый класс BaseAgent

Все агенты наследуются от `BaseAgent` и реализуют:

```python
from app.agents.base import BaseAgent

class MyAgent(BaseAgent):
    # Статические атрибуты для миграции
    name = "my_agent"
    description = "Описание агента"
    prompt = "Промпт агента..."
    tools = [...]
    
    async def compile_graph(self) -> Runnable:
        """Компиляция LangGraph графа"""
        pass
```

**Обязательные атрибуты:**
- `name` - уникальное имя агента
- `description` - описание (опционально)

**Ключевые методы:**
- `compile_graph()` - создание и компиляция LangGraph графа
- `ainvoke()` - унифицированный метод вызова
- `get_tools()` - загрузка инструментов из БД
- `as_tool()` - превращение агента в инструмент

---

## Типы агентов

Agent Lab поддерживает три типа агентов:

### 1. ReAct агенты (простые)

**Когда использовать:**
- Простые задачи с последовательным использованием tools
- Агенты с четким промптом и набором инструментов
- Линейная логика без сложных условных переходов

**Преимущества:**
- Быстрая разработка (только prompt и tools)
- Автоматическая компиляция через `create_react_agent`
- Поддержка динамических переменных в промпте

**Пример:** `app/agents/weather/agent.py`, `app/agents/calculator/agent.py`

### 2. StateGraph агенты (кастомные)

**Когда использовать:**
- Сложная логика с условными переходами
- Необходим полный контроль над графом
- Нестандартные State или структура графа

**Преимущества:**
- Полный контроль над LangGraph
- Кастомные State типы
- Гибкая структура графа

**Пример:** `app/flows/smart_flow.py`

### 3. StateGraph агенты (декларативные)

**Когда использовать:**
- Сложные multi-agent системы
- Граф с многими нодами и условиями
- Легко изменяемая структура

**Преимущества:**
- Декларативное описание через `GraphDefinition`
- Автоматическая компиляция через `GraphBuilder`
- Легкое изменение структуры графа

**Пример:** `app/agents/research/coordinator.py`

---

## ReAct агенты

### Структура ReAct агента

```python
from app.agents.react_agent import ReActAgent
from app.tools.misc.standard import ask_user

class WeatherAgent(ReActAgent):
    """Агент для работы с погодой"""
    
    name = "weather_agent"
    description = "Помогает с погодой и путешествиями"
    is_public = True  # Доступен для всех компаний
    
    # Конфигурация LLM
    llm_config = {
        "model": "anthropic/claude-sonnet-4.5",
        "temperature": 0.3,
        "max_tokens": 4000
    }
    
    # Промпт с поддержкой переменных
    # ВАЖНО: store НЕ задается в агенте, только в FlowConfig!
    prompt = """
Ты помощник по погоде компании {?company_name|Weather Service}.

📊 КОНТЕКСТ:
- Пользователь: {?user_name|Гость}
- Дата: {current_date}
- Запросов: {?store.requests_count|0}

ТВОЯ ЗАДАЧА:
1. Получить город от пользователя
2. Проверить погоду
3. Дать рекомендации
"""
    
    # Инструменты (list или строки-ссылки)
    tools = [
        ask_user,
        "app.tools.misc.weather_tools.get_weather",
        "agent:app.agents.weather.agent.TravelInfoAgent"
    ]
```

### Динамические переменные в промпте

ReActAgent поддерживает систему переменных:

**Глобальные переменные:**
- `{company_name}` - название компании
- `{user_name}` - имя пользователя
- `{current_date}` - текущая дата
- `{current_time}` - текущее время

**Переменные из store:**
- `{store.key}` - обязательная переменная (ошибка если нет)
- `{?store.key|default}` - опциональная с дефолтом

**Условные блоки:**
```
{?store.last_city:
  КОНТЕКСТ: Ранее пользователь спрашивал про {store.last_city}
}
```

**Счетчики:**
- `{#messages.count}` - количество сообщений в диалоге

### Компиляция графа

ReActAgent автоматически компилирует граф через `create_react_agent`:

```python
# Внутри ReActAgent.compile_graph()
from langgraph.prebuilt import create_react_agent

graph = create_react_agent(
    model=llm,
    tools=tools,
    prompt=dynamic_prompt,  # Функция для динамического рендеринга
    checkpointer=checkpointer,
    state_schema=State
)
```

**Что происходит:**
1. Создается LLM на основе `llm_config`
2. Загружаются tools из БД по ссылкам
3. Промпт рендерится с переменными
4. Создается ReAct граф с автоматическим циклом

---

## StateGraph агенты

### Кастомные StateGraph агенты

Для полного контроля переопределяй `build_graph()`:

```python
from app.agents.stategraph_agent import StateGraphAgent
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List
from langchain_core.messages import BaseMessage

class RouterState(TypedDict):
    messages: List[BaseMessage]
    selected_agent: str

class SmartFlowAgent(StateGraphAgent):
    """Кастомный граф с роутингом"""
    
    name = "smart_flow"
    description = "Граф с условным роутингом"
    
    def build_graph(self):
        """Создание кастомного графа"""
        graph = StateGraph(RouterState)
        
        # Добавляем ноды
        graph.add_node("router", self.router_function)
        graph.add_node("agent_a", self.agent_a_node)
        graph.add_node("agent_b", self.agent_b_node)
        
        # Добавляем edges
        graph.add_edge(START, "router")
        
        # Условный переход
        graph.add_conditional_edges(
            "router",
            self.router_condition,
            {
                "agent_a": "agent_a",
                "agent_b": "agent_b"
            }
        )
        
        graph.add_edge("agent_a", END)
        graph.add_edge("agent_b", END)
        
        return graph
    
    def router_function(self, state):
        """Функция роутера"""
        if "math" in state["messages"][0].content:
            state["selected_agent"] = "agent_a"
        else:
            state["selected_agent"] = "agent_b"
        return state
    
    def router_condition(self, state):
        """Условие для выбора"""
        return state["selected_agent"]
    
    async def agent_a_node(self, state):
        """Нода с вызовом другого агента"""
        from app.core.agent_factory import AgentFactory
        
        factory = AgentFactory()
        agent = await factory.get_agent("app.agents.calculator.agent.CalculatorAgent")
        result = await agent.ainvoke({"messages": state["messages"]})
        
        state["messages"] = result["messages"]
        return state
    
    async def compile_graph(self):
        """Компиляция с checkpointer"""
        from app.core.checkpointer import get_checkpointer
        
        checkpointer = await get_checkpointer()
        return self.build_graph().compile(checkpointer=checkpointer)
```

**Ключевые моменты:**
- Переопределяй `build_graph()` для создания графа
- Используй `StateGraph` из LangGraph
- Обязательно реализуй `compile_graph()` с checkpointer
- Можешь использовать любой TypedDict как State

### Декларативные StateGraph агенты

Для сложных систем используй `GraphDefinition`:

```python
from app.agents.stategraph_agent import StateGraphAgent
from app.models.core_models import (
    GraphDefinition, GraphNode, GraphEdge, 
    NodeType, ConditionType
)

def check_quality_decision(state):
    """Условная функция для роутера"""
    decision = state.get("store", {}).get("decision", "complete")
    
    if decision == "need_more":
        return "retry"
    return "finish"

class ResearchCoordinatorAgent(StateGraphAgent):
    """Координатор с декларативным графом"""
    
    name = "research_coordinator"
    description = "Многоэтапное исследование"
    
    graph_definition = GraphDefinition(
        nodes=[
            # Агент-нода
            GraphNode(
                id="analyze",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.query_analyzer.QueryAnalyzerAgent"},
                description="Анализ запроса"
            ),
            
            # Еще агент-нода
            GraphNode(
                id="search",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.search_agent.SearchAgent"},
                description="Поиск информации"
            ),
            
            # Функция-нода
            GraphNode(
                id="finish",
                type=NodeType.FUNCTION_NODE,
                params={"function": "app.agents.research.coordinator.return_final_report"},
                description="Возврат результата"
            ),
        ],
        edges=[
            # Обычные edges
            GraphEdge(source="START", target="analyze"),
            GraphEdge(source="analyze", target="search"),
            
            # Условный переход
            GraphEdge(
                source="search",
                target="retry",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.research.coordinator.check_quality_decision"
            ),
            GraphEdge(
                source="search",
                target="finish",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.research.coordinator.check_quality_decision"
            ),
            
            # Завершение
            GraphEdge(source="finish", target="END"),
        ],
        entry_point="analyze"
    )
```

**Типы нод:**

1. **AGENT_NODE** - вызов другого агента
   ```python
   GraphNode(
       id="my_agent",
       type=NodeType.AGENT_NODE,
       params={"agent_id": "app.agents.my.agent.MyAgent"}
   )
   ```

2. **FUNCTION_NODE** - вызов функции
   ```python
   GraphNode(
       id="my_func",
       type=NodeType.FUNCTION_NODE,
       params={"function": "module.path.my_function"}
   )
   ```

3. **TOOL_NODE** - вызов tool
   ```python
   GraphNode(
       id="my_tool",
       type=NodeType.TOOL_NODE,
       params={"tool_id": "app.tools.my_tool.do_something"}
   )
   ```

**Типы edges:**

1. **Обычный edge** - прямой переход
   ```python
   GraphEdge(source="node_a", target="node_b")
   ```

2. **Условный edge (ROUTER)** - переход по условию
   ```python
   GraphEdge(
       source="node_a",
       target="node_b",
       condition_type=ConditionType.ROUTER,
       condition="module.path.condition_function"
   )
   ```

**Условные функции:**

```python
def my_condition(state: State) -> str:
    """
    Возвращает ID ноды куда переходить.
    Должна быть зарегистрирована в edges.
    """
    if state.get("store", {}).get("result") == "success":
        return "success_node"
    return "failure_node"
```

---

## Миграция агентов

### Автоматическая миграция

При старте приложения `Migrator` сканирует код и мигрирует агенты в БД:

```python
# app/core/migrator.py
async def _migrate_all_agents(self):
    """Мигрирует все агенты из кода в БД"""
    # 1. Сканирует app/agents/ и app/flows/
    # 2. Находит все классы наследующие BaseAgent
    # 3. Извлекает атрибуты (name, prompt, tools)
    # 4. Создает AgentConfig
    # 5. Сохраняет в Storage
```

**Что мигрируется:**
- `name` → agent_id
- `description` → description
- `prompt` → prompt
- `tools` → список ToolReference
- `llm_config` → LLMConfig
- `graph_definition` → GraphDefinition
- `store` → начальные данные store

### Процесс миграции

```
1. Код агента (Python класс)
     ↓
2. Migrator.scan() - сканирование кода
     ↓
3. AgentConfig.migrate() - создание конфигурации
     ↓
4. Storage.set("agent:...") - сохранение в БД
     ↓
5. AgentFactory.get_agent() - создание из БД
```

### Миграция tools

Tools мигрируются как `ToolReference`:

```python
# В коде агента
tools = [
    ask_user,  # Прямая ссылка на функцию
    "app.tools.misc.weather_tools.get_weather",  # Строка-путь
    "agent:app.agents.weather.agent.TravelInfoAgent"  # Агент как tool
]

# После миграции в БД
config.tools = [
    ToolReference(tool_id="app.tools.misc.standard.ask_user", params={}),
    ToolReference(tool_id="app.tools.misc.weather_tools.get_weather", params={}),
    ToolReference(tool_id="agent:app.agents.weather.agent.TravelInfoAgent", params={})
]
```

**Типы ToolReference:**
- Обычный tool: `tool_id="app.tools.module.function"`
- Агент как tool: `tool_id="agent:app.agents.module.AgentClass"`

---

## Агенты как инструменты

### Превращение агента в tool

Любой агент можно использовать как инструмент:

```python
class MainAgent(ReActAgent):
    name = "main_agent"
    
    tools = [
        # Агент TravelInfoAgent станет tool для MainAgent
        "agent:app.agents.weather.agent.TravelInfoAgent"
    ]
```

### Как это работает

1. **В коде агента:**
   ```python
   "agent:app.agents.weather.agent.TravelInfoAgent"
   ```

2. **При миграции:**
   ```python
   ToolReference(
       tool_id="agent:app.agents.weather.agent.TravelInfoAgent",
       params={}
   )
   ```

3. **При загрузке tools:**
   ```python
   # ToolFactory распознает префикс "agent:"
   # Создает через BaseAgent.as_tool()
   tool = await sub_agent.as_tool()
   ```

4. **LLM видит tool:**
   ```json
   {
     "name": "travel_info_agent",
     "description": "Определяет куда пользователь хочет поехать",
     "parameters": {
       "request": {
         "type": "string",
         "description": "Запрос к агенту"
       }
     }
   }
   ```

### as_tool() метод

Внутри `BaseAgent.as_tool()`:

```python
async def as_tool(self) -> StructuredTool:
    """Превращает агента в LangChain tool"""
    
    async def agent_wrapper(request: str) -> str:
        """Обертка для вызова агента"""
        try:
            result = await self.ainvoke({
                "messages": [{"role": "user", "content": request}]
            })
            
            # GraphInterrupt - пробрасываем дальше
            if "__interrupt__" in result:
                raise GraphInterrupt(...)
            
            # Извлекаем ответ
            if result.get("messages"):
                return result["messages"][-1].content
                
            return str(result)
            
        except GraphInterrupt as e:
            # Субагент запросил данные у пользователя
            raise e
    
    return StructuredTool.from_function(
        func=agent_wrapper,
        name=self.config.name,
        description=self.config.description
    )
```

**Ключевые моменты:**
- Субагент может вызывать `ask_user()` → GraphInterrupt пробрасывается
- Родительский агент получит вопрос и сможет передать его пользователю
- После ответа выполнение продолжится с места прерывания

---

## Работа с tools

### Ссылки на tools

В атрибуте `tools` используй:

**1. Прямые импорты (для миграции):**
```python
from app.tools.misc.standard import ask_user

tools = [ask_user]
```

**2. Строковые пути:**
```python
tools = [
    "app.tools.misc.weather_tools.get_weather",
    "app.tools.session.session_tools.session_set"
]
```

**3. Агенты как tools:**
```python
tools = [
    "agent:app.agents.sub.agent.SubAgent"
]
```

### Создание tools

Tool создается через декоратор `@tool`:

```python
from app.core.tool_decorator import tool

@tool(
    cost=0.1,  # Стоимость использования
    billing_name="weather_api",  # Имя для биллинга
    is_public=True  # Доступен для всех компаний
)
async def get_weather(city: str) -> str:
    """
    Получить погоду в городе.
    
    Args:
        city: Название города
        
    Returns:
        Описание погоды
    """
    # Реализация
    return f"Погода в {city}: солнечно"
```

**Обязательные элементы:**
- Типизация параметров и возврата
- Docstring с описанием
- Async функция (все тулы асинхронные)

### Сессионные tools

Для работы с `store` используй готовые tools:

```python
from app.tools.session.session_tools import (
    session_set,
    session_get,
    session_has,
    session_delete
)

class MyAgent(ReActAgent):
    tools = [session_set, session_get]
    
    prompt = """
    Сохраняй данные через session_set:
    - session_set("user_city", "Москва")
    - session_get("user_city")
    """
```

---

## Переменные и state

### Store (общая память flow)

`store` - dict в State для хранения данных между вызовами агентов.

**ВАЖНО:** Store задается **ТОЛЬКО в FlowConfig**, НЕ в агентах!

```python
# В FlowConfig (НЕ в агенте!)
flow_config = FlowConfig(
    name="My Flow",
    entry_point_agent="app.agents.my.MyAgent",
    
    # Общая память для ВСЕХ агентов в flow
    store={
        "counter": 0,
        "user_preferences": {},
        "max_iterations": 3
    }
)

# В промпте агента можно использовать
class MyAgent(ReActAgent):
    prompt = """
    Счетчик запросов: {?store.counter|0}
    Максимум итераций: {?store.max_iterations|3}
    
    Используй session_set для изменения:
    - session_set("counter", {?store.counter|0} + 1)
    """
```

**Как работает:**
1. Flow инициализирует `store` из `flow_config.store`
2. Все агенты в flow получают один общий `store`
3. Агент A делает `session_set("key", "value")` → сохраняется в общий store
4. Агент B может использовать `{?store.key}` в промпте или `session_get("key")`

### State структура

Унифицированный State для всех агентов:

```python
from app.core.state import State

State = {
    "messages": List[BaseMessage],  # История сообщений
    "store": dict,  # Сессионное хранилище
    "user_id": str,  # ID пользователя
    "session_id": str,  # ID сессии
    "task_id": str,  # ID задачи
}
```

### Доступ к контексту

Через `get_context()`:

```python
from app.core.context import get_context

def my_function(state):
    context = get_context()
    
    user = context.user
    company = context.active_company
    flow_config = context.flow_config
```

### Доступ к state

Через `get_state()`:

```python
from app.core.variables import get_state, set_state

def my_function():
    state = get_state()
    store = state.get("store", {})
    
    store["new_value"] = "data"
    set_state(state)
```

---

## Примеры

### Пример 1: Простой ReAct агент

```python
from app.agents.react_agent import ReActAgent
from app.tools.misc.standard import ask_user

class GreeterAgent(ReActAgent):
    """Простой агент приветствия"""
    
    name = "greeter_agent"
    description = "Приветствует пользователей"
    is_public = True
    
    prompt = """
Ты дружелюбный помощник компании {?company_name|Наша компания}.

Приветствуй пользователя {?user_name|Гость} и спроси как дела.
Если пользователь ответил - пожелай хорошего дня.
"""
    
    tools = [ask_user]
```

### Пример 2: Агент с субагентом

```python
from app.agents.react_agent import ReActAgent

class MainAgent(ReActAgent):
    """Главный агент с делегированием"""
    
    name = "main_agent"
    description = "Главный агент с субагентами"
    
    prompt = """
Ты главный агент.

Если пользователь спрашивает про погоду - используй weather_info_agent.
Если про путешествие - используй travel_agent.
"""
    
    tools = [
        "agent:app.agents.weather.info.WeatherInfoAgent",
        "agent:app.agents.travel.TravelAgent"
    ]
```

### Пример 3: Кастомный граф с циклом

```python
from app.agents.stategraph_agent import StateGraphAgent
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class LoopState(TypedDict):
    messages: list
    iteration: int
    max_iterations: int

class IterativeAgent(StateGraphAgent):
    """Агент с циклической обработкой"""
    
    name = "iterative_agent"
    
    def build_graph(self):
        graph = StateGraph(LoopState)
        
        graph.add_node("process", self.process_node)
        graph.add_node("check", self.check_node)
        
        graph.add_edge(START, "process")
        graph.add_edge("process", "check")
        
        # Условный переход: продолжить или завершить
        graph.add_conditional_edges(
            "check",
            self.should_continue,
            {
                "continue": "process",
                "end": END
            }
        )
        
        return graph
    
    async def process_node(self, state):
        """Обработка данных"""
        state["iteration"] = state.get("iteration", 0) + 1
        # Логика обработки
        return state
    
    async def check_node(self, state):
        """Проверка условия"""
        return state
    
    def should_continue(self, state):
        """Решение продолжать или нет"""
        if state["iteration"] >= state.get("max_iterations", 3):
            return "end"
        return "continue"
    
    async def compile_graph(self):
        from app.core.checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        return self.build_graph().compile(checkpointer=checkpointer)
```

### Пример 4: Декларативный multi-agent

```python
from app.agents.stategraph_agent import StateGraphAgent
from app.models.core_models import *

async def return_result(state):
    """Финальная функция возврата результата"""
    from langchain_core.messages import AIMessage
    
    result = state.get("store", {}).get("final_result", "")
    
    if "messages" not in state:
        state["messages"] = []
    state["messages"].append(AIMessage(content=result))
    
    return state

def router_decision(state):
    """Условная функция роутинга"""
    task_type = state.get("store", {}).get("task_type", "general")
    
    if task_type == "math":
        return "calculator"
    elif task_type == "research":
        return "research"
    return "general"

class MultiAgentCoordinator(StateGraphAgent):
    """Координатор с несколькими агентами"""
    
    name = "multi_agent_coordinator"
    description = "Координирует несколько специализированных агентов"
    
    graph_definition = GraphDefinition(
        nodes=[
            GraphNode(
                id="router",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.router.RouterAgent"},
                description="Анализ и выбор агента"
            ),
            GraphNode(
                id="calculator",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.calculator.agent.CalculatorAgent"},
                description="Математические вычисления"
            ),
            GraphNode(
                id="research",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.research.coordinator.ResearchCoordinatorAgent"},
                description="Исследование темы"
            ),
            GraphNode(
                id="general",
                type=NodeType.AGENT_NODE,
                params={"agent_id": "app.agents.general.GeneralAgent"},
                description="Общие вопросы"
            ),
            GraphNode(
                id="return_result",
                type=NodeType.FUNCTION_NODE,
                params={"function": "app.agents.multi.return_result"},
                description="Возврат результата"
            ),
        ],
        edges=[
            GraphEdge(source="START", target="router"),
            
            # Условный роутинг
            GraphEdge(
                source="router",
                target="calculator",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.multi.router_decision"
            ),
            GraphEdge(
                source="router",
                target="research",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.multi.router_decision"
            ),
            GraphEdge(
                source="router",
                target="general",
                condition_type=ConditionType.ROUTER,
                condition="app.agents.multi.router_decision"
            ),
            
            # Все ведут к возврату результата
            GraphEdge(source="calculator", target="return_result"),
            GraphEdge(source="research", target="return_result"),
            GraphEdge(source="general", target="return_result"),
            
            GraphEdge(source="return_result", target="END"),
        ],
        entry_point="router"
    )
```

---

## Лучшие практики

### 1. Выбор типа агента

- **ReAct** - для 90% случаев (простота + гибкость)
- **StateGraph кастомный** - когда нужна специфичная логика
- **StateGraph декларативный** - для больших multi-agent систем

### 2. Проектирование промптов

```python
prompt = """
Ты [роль] для [цель].

📊 КОНТЕКСТ:
- Пользователь: {?user_name}
- Важные данные: {?store.key}

ТВОЯ ЗАДАЧА:
1. Шаг 1
2. Шаг 2
3. Шаг 3

ВАЖНО:
- Правило 1
- Правило 2
"""
```

### 3. Именование

- Агенты: `{Domain}{Purpose}Agent` (WeatherAgent, ResearchCoordinator)
- Субагенты: `{Domain}{Specific}Agent` (TravelInfoAgent)
- Flows: `{Purpose}Flow` (SmartFlow, ResearchFlow)

### 4. Миграция

После изменений в коде:
```bash
# Перезапуск автоматически мигрирует
uv run python run.py

# Или вручную
uv run python -m app.core.migrator
```

### 5. Тестирование

```python
# Тестирование агента
from app.core.agent_factory import AgentFactory

factory = AgentFactory()
agent = await factory.get_agent("app.agents.my.agent.MyAgent")

result = await agent.ainvoke({
    "messages": [{"role": "user", "content": "Тест"}]
})

assert result["messages"][-1].content
```

---

## Troubleshooting

### Агент не мигрируется

**Проблема:** Агент не появляется в БД после миграции

**Решение:**
1. Проверь что класс наследует `BaseAgent`
2. Проверь что у класса есть `name` атрибут
3. Проверь что файл находится в `app/agents/` или `app/flows/`
4. Смотри логи миграции при старте

### Tools не загружаются

**Проблема:** `get_tools()` возвращает пустой список

**Решение:**
1. Проверь что tools есть в config после миграции
2. Проверь правильность путей к tools
3. Проверь что tools помечены `@tool` декоратором
4. Смотри логи `AgentFactory._create_tool_from_reference`

### GraphInterrupt не работает

**Проблема:** `ask_user()` не запрашивает данные

**Решение:**
1. Проверь что агент скомпилирован с `checkpointer`
2. Проверь что у задачи есть `session_id`
3. Убедись что `TaskProcessor` ловит `GraphInterrupt`

### Переменные не подставляются

**Проблема:** `{?store.key}` показывает `{?store.key}` вместо значения

**Решение:**
1. Проверь синтаксис: `{?store.key|default}`
2. Убедись что агент наследует `ReActAgent`
3. Проверь что используется `_create_dynamic_prompt()`

---

## См. также

- [Архитектура](architecture.md) - общая архитектура платформы
- [Flows](flows.md) - создание и управление flows
- [State и переменные](state_and_variables.md) - работа с данными
- [API Reference](api_reference.md) - документация API

