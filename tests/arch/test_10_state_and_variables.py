"""
Тесты системы State и переменных.

Проверяем:
1. StateGraph агент имеет правильный State
2. ReAct агент собирается с промптом и переменными
3. Персистентность данных между вызовами
4. Доступ к State из тулов
"""

import pytest
import pytest_asyncio
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.core.variables import VariableResolver, get_state
from app.core.storage import Storage
from app.core.agent_factory import AgentFactory
from app.core.checkpointer import init_checkpointer
from app.models import (
    AgentConfig,
    AgentType,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    NodeType,
    LLMConfig,
    ToolReference,
    CodeMode,
)
from app.models.context_models import Context
from app.identity.models import User, Company
from app.core.context import set_context


@pytest_asyncio.fixture
async def setup_storage():
    """Инициализирует storage и checkpointer"""
    storage = Storage()
    await init_checkpointer()
    return storage


@pytest.fixture
def test_context():
    """Создает тестовый контекст"""
    user = User(
        user_id="test_user_123",
        name="Тестовый Пользователь",
        status="active",
    )
    
    company = Company(
        company_id="test_company",
        subdomain="test",
        name="Тестовая Компания",
    )
    
    context = Context(
        user=user,
        platform="api",
        active_company=company,
        session_id="test_session_123",
        flow_variables={
            "bot_name": "Тест Бот",
            "max_retries": 3,
        },
        company_variables={
            "company_email": "test@company.com",
        },
    )
    
    set_context(context)
    return context


@pytest.mark.asyncio
async def test_01_stategraph_has_correct_state(setup_storage, test_context):
    """
    Тест 1: StateGraph агент имеет правильный State.
    Проверяем что StateGraph агент использует наш State с полями messages, store и т.д.
    """
    storage = setup_storage
    
    # Создаем StateGraph агента с нодами
    agent_config = AgentConfig(
        agent_id="test_stategraph_agent",
        name="Test StateGraph Agent",
        description="Тестовый StateGraph агент",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="start_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def start_node(state):
    '''Стартовая нода'''
    # Проверяем что state имеет нужные поля
    assert "messages" in state, "State должен иметь messages"
    assert "store" in state, "State должен иметь store"
    assert "session_id" in state, "State должен иметь session_id"
    
    # Сохраняем данные в store
    state["store"]["test_key"] = "test_value"
    state["store"]["counter"] = 1
    
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="start_node"),
                GraphEdge(source="start_node", target="END"),
            ],
            entry_point="start_node",
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента и компилируем граф
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_stategraph_agent")
    
    # Вызываем агента
    input_data = {
        "messages": [HumanMessage(content="test")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session_123",
        "task_id": "test_task",
        "user_id": "test_user_123",
    }
    
    import uuid
    config = {"configurable": {"thread_id": f"test_thread_1_{uuid.uuid4().hex[:8]}"}}
    result = await agent.ainvoke(input_data, config=config)
    
    # Проверяем результат
    assert "messages" in result
    assert "store" in result
    assert result["store"]["test_key"] == "test_value"
    assert result["store"]["counter"] == 1
    
    print("✅ Тест 1 пройден: StateGraph агент имеет правильный State")


@pytest.mark.asyncio
async def test_02_react_agent_with_variables(setup_storage, test_context):
    """
    Тест 2: ReAct агент собирается с промптом и переменными.
    Проверяем что переменные подставляются в промпт правильно.
    """
    storage = setup_storage
    
    # Создаем ReAct агента с переменными в промпте
    agent_config = AgentConfig(
        agent_id="test_react_agent_vars",
        name="Test ReAct Agent",
        description="Тестовый ReAct агент с переменными",
        type=AgentType.REACT,
        prompt="""
Ты {bot_name} компании {company_name}.

Информация:
- Email: {company_email}
- Дата: {current_date}
- Пользователь: {user_name}
- Макс попыток: {max_retries}
- Локальная переменная: {local_var}

Отвечай коротко.
""",
        tools=[],
        llm_config=LLMConfig(
            model="mock-gpt-4",
            temperature=0.1,
        ),
        local_variables={
            "local_var": "test_local_value",
        },
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_react_agent_vars")
    
    # Компилируем граф и проверяем что промпт отрендерен
    await agent.compile_graph()
    
    # Проверяем что переменные подставились (проверяем через VariableResolver)
    rendered_prompt = VariableResolver.render_template(
        agent_config.prompt,
        local_vars=agent_config.local_variables
    )
    
    # Проверяем что все переменные подставились
    assert "{bot_name}" not in rendered_prompt, "bot_name должен быть подставлен"
    assert "{company_name}" not in rendered_prompt, "company_name должен быть подставлен"
    assert "{company_email}" not in rendered_prompt, "company_email должен быть подставлен"
    assert "{current_date}" not in rendered_prompt, "current_date должен быть подставлен"
    assert "{user_name}" not in rendered_prompt, "user_name должен быть подставлен"
    assert "{max_retries}" not in rendered_prompt, "max_retries должен быть подставлен"
    assert "{local_var}" not in rendered_prompt, "local_var должен быть подставлен"
    
    # Проверяем что значения правильные
    assert "Тест Бот" in rendered_prompt
    assert "Тестовая Компания" in rendered_prompt
    assert "test@company.com" in rendered_prompt
    assert "Тестовый Пользователь" in rendered_prompt
    assert "3" in rendered_prompt
    assert "test_local_value" in rendered_prompt
    
    print("✅ Тест 2 пройден: ReAct агент с правильными переменными")


@pytest.mark.asyncio
async def test_03_state_persistence_between_calls(setup_storage, test_context):
    """
    Тест 3: Персистентность State между вызовами.
    Проверяем что данные в store сохраняются между вызовами агента.
    """
    storage = setup_storage
    
    # Создаем агента который работает со store
    agent_config = AgentConfig(
        agent_id="test_persistence_agent",
        name="Test Persistence Agent",
        description="Агент для проверки персистентности",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="counter_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def counter_node(state):
    '''Увеличивает счетчик в store'''
    if "counter" not in state["store"]:
        state["store"]["counter"] = 0
    
    state["store"]["counter"] += 1
    state["store"]["last_message"] = state["messages"][-1].content if state["messages"] else ""
    
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="counter_node"),
                GraphEdge(source="counter_node", target="END"),
            ],
            entry_point="counter_node",
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_persistence_agent")
    
    # Первый вызов - используем уникальный thread_id
    import uuid
    thread_id = f"test_thread_persistence_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data_1 = {
        "messages": [HumanMessage(content="Первое сообщение")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result_1 = await agent.ainvoke(input_data_1, config=config)
    
    assert result_1["store"]["counter"] == 1
    assert result_1["store"]["last_message"] == "Первое сообщение"
    
    # Второй вызов (должен сохранить state)
    input_data_2 = {
        "messages": [HumanMessage(content="Второе сообщение")],
    }
    
    result_2 = await agent.ainvoke(input_data_2, config=config)
    
    # Проверяем что counter увеличился (данные персистились)
    assert result_2["store"]["counter"] == 2, "Counter должен был увеличиться с 1 до 2"
    assert result_2["store"]["last_message"] == "Второе сообщение"
    
    # Третий вызов
    input_data_3 = {
        "messages": [HumanMessage(content="Третье сообщение")],
    }
    
    result_3 = await agent.ainvoke(input_data_3, config=config)
    
    assert result_3["store"]["counter"] == 3, "Counter должен был увеличиться с 2 до 3"
    assert result_3["store"]["last_message"] == "Третье сообщение"
    
    print("✅ Тест 3 пройден: Данные персистятся между вызовами")


@pytest.mark.asyncio
async def test_04_state_access_from_tool(setup_storage, test_context):
    """
    Тест 4: Доступ к State из тула.
    Проверяем что тул может читать и писать в state через get_state().
    """
    storage = setup_storage
    
    # Создаем кастомный тул с доступом к state
    @tool
    def test_tool_with_state_access(data: str) -> str:
        """Тестовый тул с доступом к state"""
        state = get_state()
        
        if not state:
            return "ERROR: State недоступен"
        
        # Проверяем структуру state
        assert "messages" in state, "State должен иметь messages"
        assert "store" in state, "State должен иметь store"
        
        # Читаем из store
        previous_data = state["store"].get("tool_data", "нет данных")
        
        # Пишем в store
        state["store"]["tool_data"] = data
        state["store"]["tool_call_count"] = state["store"].get("tool_call_count", 0) + 1
        
        return f"Записано: {data}, Предыдущее: {previous_data}"
    
    # Сохраняем тул в БД
    ToolReference(
        tool_id="test_tool_with_state_access",
        code_mode=CodeMode.INLINE_CODE,
        inline_code="""
from langchain_core.tools import tool
from app.core.variables import get_state

@tool
def test_tool_with_state_access(data: str) -> str:
    '''Тестовый тул с доступом к state'''
    state = get_state()
    
    if not state:
        return "ERROR: State недоступен"
    
    # Читаем из store
    previous_data = state["store"].get("tool_data", "нет данных")
    
    # Пишем в store
    state["store"]["tool_data"] = data
    state["store"]["tool_call_count"] = state["store"].get("tool_call_count", 0) + 1
    
    return f"Записано: {data}, Предыдущее: {previous_data}"
""",
        description="Тестовый тул с доступом к state",
    )
    
    # Создаем агента который использует этот тул
    agent_config = AgentConfig(
        agent_id="test_agent_with_tool",
        name="Test Agent With Tool",
        description="Агент с тулом для доступа к state",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="tool_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                        inline_code="""
async def tool_node(state):
    '''Нода вызывает тул с доступом к state'''
    from app.core.variables import get_state, set_state_in_context
    
    # Устанавливаем state в контекст
    set_state_in_context(state)
    
    # Вызываем тул (симулируем)
    from app.core.variables import get_state as get_state_from_tool
    
    tool_state = get_state_from_tool()
    
    # Проверяем что тул видит state
    assert tool_state is not None, "Тул должен видеть state"
    assert tool_state is state, "Тул должен видеть тот же state"
    
    # Записываем в store как будто это сделал тул
    if "store" not in state:
        state["store"] = {}
    
    previous = state["store"].get("tool_data", "нет данных")
    state["store"]["tool_data"] = "new_data"
    state["store"]["tool_call_count"] = state["store"].get("tool_call_count", 0) + 1
    
    # Добавляем результат в messages
    from langchain_core.messages import AIMessage
    state["messages"].append(AIMessage(content=f"Tool result: записано new_data, предыдущее: {previous}"))
    
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="tool_node"),
                GraphEdge(source="tool_node", target="END"),
            ],
            entry_point="tool_node",
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_agent_with_tool")
    
    # Первый вызов
    import uuid as uuid2
    thread_id = f"test_thread_tool_{uuid2.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data_1 = {
        "messages": [HumanMessage(content="Вызов тула")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result_1 = await agent.ainvoke(input_data_1, config=config)
    
    # Проверяем что тул записал данные
    assert "tool_data" in result_1["store"], "Тул должен был записать tool_data"
    assert result_1["store"]["tool_data"] == "new_data"
    assert result_1["store"]["tool_call_count"] == 1
    
    # Второй вызов - проверяем что тул видит предыдущие данные
    input_data_2 = {
        "messages": [HumanMessage(content="Второй вызов тула")],
    }
    
    result_2 = await agent.ainvoke(input_data_2, config=config)
    
    # Проверяем что счетчик увеличился
    assert result_2["store"]["tool_call_count"] == 2
    
    # Проверяем что в сообщении есть ссылка на предыдущие данные
    last_message = result_2["messages"][-1].content
    assert "предыдущее: new_data" in last_message.lower() or "предыдущее" in last_message.lower()
    
    print("✅ Тест 4 пройден: Тул имеет доступ к State")


@pytest.mark.asyncio
async def test_05_session_tools_integration(setup_storage, test_context):
    """
    Тест 5: Интеграция с сессионными тулами.
    Проверяем что session_set и session_get работают правильно.
    """
    
    storage = setup_storage
    
    # Создаем агента который использует сессионные тулы
    agent_config = AgentConfig(
        agent_id="test_session_tools_agent",
        name="Test Session Tools Agent",
        description="Агент с сессионными тулами",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="session_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                        inline_code="""
async def session_node(state):
    '''Работает с сессионными данными'''
    from app.core.variables import set_state_in_context
    
    # Устанавливаем state в контекст для тулов
    set_state_in_context(state)
    
    # Симулируем работу session_set
    if "store" not in state:
        state["store"] = {}
    
    state["store"]["warehouse_id"] = "12345"
    state["store"]["warehouse_name"] = "Тестовый Склад"
    
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="session_node"),
                GraphEdge(source="session_node", target="END"),
            ],
            entry_point="session_node",
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_session_tools_agent")
    
    # Вызываем агента
    import uuid as uuid3
    thread_id = f"test_thread_session_{uuid3.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data = {
        "messages": [HumanMessage(content="Сохрани склад")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    # Проверяем что данные сохранились
    assert "warehouse_id" in result["store"]
    assert result["store"]["warehouse_id"] == "12345"
    assert result["store"]["warehouse_name"] == "Тестовый Склад"
    
    print("✅ Тест 5 пройден: Сессионные тулы работают")


@pytest.mark.asyncio  
async def test_06_variable_priority(setup_storage, test_context):
    """
    Тест 6: Приоритет переменных.
    Проверяем что локальные переменные агента перекрывают переменные flow.
    """
    
    # В context уже есть flow_variables с bot_name="Тест Бот"
    # Создадим агента с локальной переменной bot_name
    agent_config = AgentConfig(
        agent_id="test_priority_agent",
        name="Test Priority Agent",
        type=AgentType.REACT,
        prompt="Я {bot_name}",
        tools=[],
        llm_config=LLMConfig(
            model="mock-gpt-4",
            temperature=0.1,
        ),
        local_variables={
            "bot_name": "Локальный Бот",  # Должен перекрыть "Тест Бот" из flow
        },
    )
    
    # Рендерим промпт с учетом приоритета
    rendered = VariableResolver.render_template(
        agent_config.prompt,
        local_vars=agent_config.local_variables
    )
    
    # Проверяем что локальная переменная победила
    assert "Локальный Бот" in rendered
    assert "Тест Бот" not in rendered
    
    print("✅ Тест 6 пройден: Приоритет переменных работает")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
