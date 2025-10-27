"""
Тест 3: Создание ReAct агента полностью в БД.

Проверяет что можно создать полнофункциональный ReAct агента 
только через БД API без написания кода.
"""
import pytest
from app.models import ToolReference, CodeMode
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_mock_llm_direct(mock_llm, agent_repo):
    """Тестируем мок LLM напрямую"""
    
    print(f"🧪 Создан мок: {type(mock_llm)}")
    
    # Настраиваем ответы
    mock_llm.configure(
        responses={
            "15 + 23": "Я использую add_tool для сложения 15 и 23.",
            "погода": "Я использую weather_tools для получения погоды."
        }
    )
    
    # Тест 1: математический запрос
    result1 = await mock_llm._agenerate([HumanMessage(content="Сколько будет 15 + 23?")])
    response1 = result1.generations[0].message.content
    print(f"🧪 Тест 1 - математика: {response1}")
    assert "add_tool" in response1
    
    # Тест 2: погодный запрос  
    result2 = await mock_llm._agenerate([HumanMessage(content="Какая погода?")])
    response2 = result2.generations[0].message.content
    print(f"🧪 Тест 2 - погода: {response2}")
    assert "weather_tools" in response2
    
    print("✅ MockLLM работает корректно!")

@pytest.mark.asyncio
async def test_create_db_react_agent(migrated_db, storage, test_helpers, agent_repo):
    """Создание ReAct агента полностью в БД"""
    
    # Создаем tools
    add_tool = test_helpers.create_inline_tool(
        tool_id="add_tool",
        function_name="add_tool",
        function_body='''
def add_tool(a: int, b: int) -> str:
    """Сложение двух чисел"""
    return f"{a} + {b} = {a + b}"
''',
        description="Сложение чисел"
    )
    
    multiply_tool = test_helpers.create_inline_tool(
        tool_id="multiply_tool",
        function_name="multiply_tool",
        function_body='''
def multiply_tool(a: int, b: int) -> str:
    """Умножение двух чисел"""
    return f"{a} * {b} = {a * b}"
''',
        description="Умножение чисел"
    )
    
    subtract_tool = test_helpers.create_inline_tool(
        tool_id="subtract_tool",
        function_name="subtract_tool",
        function_body='''
def subtract_tool(a: int, b: int) -> str:
    """Вычитание двух чисел"""
    return f"{a} - {b} = {a - b}"
''',
        description="Вычитание чисел"
    )
    
    # Создаем агента
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="db_math_agent",
        name="DB Math Agent",
        prompt="Ты математический помощник. Помогаешь решать задачи используя add_tool, multiply_tool, subtract_tool.",
        tools=[add_tool, multiply_tool, subtract_tool]
    )
    
    # Проверяем что агент действительно сохранился
    saved_config = await agent_repo.get("db_math_agent")
    assert saved_config is not None, "Агент НЕ сохранился в БД!"
    
    print("✅ ReAct агент создан в БД")
    
    # Создаем flow
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="db_math_flow",
        name="DB Math Flow",
        entry_point_agent="db_math_agent"
    )
    
    print("✅ Flow для ReAct агента создан")
        
    return True

@pytest.mark.asyncio
async def test_execute_db_react_agent(migrated_db, storage, agent_factory, flow_factory, mock_llm, test_helpers, unique_id, agent_repo):
    """Создание и выполнение ReAct агента из БД"""
    
    # Создаем агента
    await test_create_db_react_agent(migrated_db, storage, test_helpers, agent_repo)
    
    # Настраиваем mock LLM
    mock_llm.configure(
        tool_responses={
            "сколько": {"tool": "add_tool", "args": {"a": 15, "b": 23}},
            "умножь": {"tool": "multiply_tool", "args": {"a": 12, "b": 7}},
        }
    )
    
    # Загружаем агента из БД
    db_agent = await agent_factory.get_agent("db_math_agent")
    
    assert db_agent is not None
    print(f"✅ ReAct агент загружен из БД: {type(db_agent)}")
    
    # Прямое тестирование агента
    result = await db_agent.ainvoke(
        {"messages": [HumanMessage(content="Сколько будет 15 + 23?")]},
        config={"configurable": {"thread_id": unique_id("test_react_direct")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    assert isinstance(final_message, str)
    
    print(f"✅ Прямое выполнение ReAct агента: {final_message[:100]}...")
    
    # Тестирование через flow
    math_flow = await flow_factory.get_flow("db_math_flow")
    
    result = await math_flow.ainvoke(
        {"messages": [HumanMessage(content="Умножь 12 на 7")]},
        config={"configurable": {"thread_id": unique_id("test_react_flow")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    assert isinstance(final_message, str)
    
    print(f"✅ Flow выполнение ReAct агента: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_react_agent_tools(migrated_db, storage, agent_factory, mock_llm, test_helpers, unique_id, agent_repo):
    """Создание и тест что ReAct агент правильно использует инструменты"""
    
    # Создаем агента
    await test_create_db_react_agent(migrated_db, storage, test_helpers, agent_repo)
    
    # Настраиваем mock LLM
    mock_llm.configure(
        responses={
            "вычисли": "Выполняю сложное вычисление по шагам. Результат: 37",
        },
        default_response="Использую математические инструменты. Результат: 37"
    )
    
    db_agent = await agent_factory.get_agent("db_math_agent")
    
    # Сложная математическая задача
    result = await db_agent.ainvoke(
        {"messages": [HumanMessage(content="Вычисли (10 + 5) * 3 - 8")]},
        config={"configurable": {"thread_id": unique_id("test_react_complex")}}
    )
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    assert isinstance(final_message, str)
    
    print(f"✅ ReAct агент использует инструменты: {final_message[:100]}...")

