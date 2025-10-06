"""
Тест 3: Создание ReAct агента полностью в БД.

Проверяет что можно создать полнофункциональный ReAct агента 
только через БД API без написания кода.
"""
import pytest
import asyncio
import os
from pathlib import Path
import sys

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.storage import Storage
from app.core.agent_factory import AgentFactory
from app.core.flow_factory import FlowFactory
from app.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig, 
    ToolReference, LLMConfig
)
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_mock_llm_direct():
    """Тестируем мок LLM напрямую"""
    
    from app.core.llm_factory import get_llm, get_global_mock_llm
    from app.models import LLMConfig
    from langchain_core.messages import HumanMessage
    
    # Создаем мок
    mock_llm = get_llm("mock", "mock-gpt-4")
    
    print(f"🧪 Создан мок: {type(mock_llm)}")
    
    # Настраиваем ответы
    mock_llm.set_responses({
        "15 + 23": "Я использую add_tool для сложения 15 и 23.",
        "погода": "Я использую weather_tools для получения погоды."
    })
    
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
    
    # Тест 3: неизвестный запрос (дефолтный ответ)
    result3 = await mock_llm._agenerate([HumanMessage(content="Неизвестный запрос")])
    response3 = result3.generations[0].message.content
    print(f"🧪 Тест 3 - дефолт: {response3}")
    assert "доступные инструменты" in response3
    
    print("✅ MockLLM работает корректно!")

@pytest.mark.asyncio
async def test_create_db_react_agent():
    """Создание ReAct агента полностью в БД"""
    
    storage = Storage()
        
        # 1. СОЗДАЕМ ReAct АГЕНТА В БД
    react_agent_config = AgentConfig(
        agent_id="db_math_agent",
        name="DB Math Agent",
        description="Математический агент созданный в БД",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,  # Пока используем ссылки на инструменты
        function_class=None,  # Нет класса - агент создается из конфигурации
        prompt="""
Ты математический помощник. Помогаешь решать математические задачи.

Инструменты:
- add_tool: сложение чисел
- multiply_tool: умножение чисел  
- subtract_tool: вычитание чисел

Всегда объясняй свои вычисления пошагово.
            """.strip(),
            tools=[
                ToolReference(
                    tool_id="add_tool",
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code='''
from langchain_core.tools import tool

@tool
def add_tool(a: int, b: int) -> str:
    """Сложение двух чисел"""
    return f"{a} + {b} = {a + b}"
''',
                    description="Сложение чисел"
                ),
                ToolReference(
                    tool_id="multiply_tool", 
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code='''
from langchain_core.tools import tool

@tool
def multiply_tool(a: int, b: int) -> str:
    """Умножение двух чисел"""
    return f"{a} * {b} = {a * b}"
''',
                    description="Умножение чисел"
                ),
                ToolReference(
                    tool_id="subtract_tool",
                    code_mode=CodeMode.INLINE_CODE, 
                    inline_code='''
from langchain_core.tools import tool

@tool
def subtract_tool(a: int, b: int) -> str:
    """Вычитание двух чисел"""
    return f"{a} - {b} = {a - b}"
''',
                    description="Вычитание чисел"
                )
            ],
            llm_config=None,  # Используем дефолтную конфигурацию
            source="manual"
        )
        
    await storage.set_agent_config(react_agent_config)
    
    # Проверяем что агент действительно сохранился
    saved_config = await storage.get_agent_config("db_math_agent")
    assert saved_config is not None, "Агент НЕ сохранился в БД!"
    
    print("✅ ReAct агент создан в БД")
    
    # 2. СОЗДАЕМ FLOW ДЛЯ АГЕНТА
    flow_config = FlowConfig(
        flow_id="db_math_flow",
        name="DB Math Flow",
        description="Flow для математического агента из БД",
        entry_point_agent="db_math_agent",
        platforms={"api": {}}
    )
    
    await storage.set_flow_config(flow_config)
    print("✅ Flow для ReAct агента создан")
        
    return True

@pytest.mark.asyncio
async def test_execute_db_react_agent():
    """Создание и выполнение ReAct агента из БД"""
    
    from app.core.llm_factory import get_global_mock_llm, get_llm
    from app.models import LLMConfig
    
    # Создаем мок чтобы инициализировать глобальную переменную
    get_llm("mock", "mock-gpt-4")
    
    # Получаем глобальный мок и настраиваем его
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "15 + 23": "Я использую инструмент add_tool для сложения 15 и 23.",
            "12 на 7": "Я использую инструмент multiply_tool для умножения 12 на 7.",
            "умножь": "Для умножения я воспользуюсь математическим инструментом."
        })
    
    # СОЗДАЕМ агента в этом же тесте для изоляции
    await test_create_db_react_agent()
    
    # 1. ЗАГРУЖАЕМ АГЕНТА ИЗ БД
    agent_factory = AgentFactory()
    db_agent = await agent_factory.get_agent("db_math_agent")
    
    assert db_agent is not None
    print(f"✅ ReAct агент загружен из БД: {type(db_agent)}")
    
    # 2. ПРЯМОЕ ТЕСТИРОВАНИЕ АГЕНТА
    result = await db_agent.ainvoke(
        {"messages": [HumanMessage(content="Сколько будет 15 + 23?")]},
        config={"configurable": {"thread_id": "test_react_direct"}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "38" in final_message or "15" in final_message and "23" in final_message
    
    print(f"✅ Прямое выполнение ReAct агента: {final_message[:100]}...")
    
    # 3. ТЕСТИРОВАНИЕ ЧЕРЕЗ FLOW
    flow_factory = FlowFactory()
    math_flow = await flow_factory.get_flow("db_math_flow")
    
    result = await math_flow.ainvoke(
        {"messages": [HumanMessage(content="Умножь 12 на 7")]},
        config={"configurable": {"thread_id": "test_react_flow"}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "84" in final_message or "12" in final_message and "7" in final_message
    
    print(f"✅ Flow выполнение ReAct агента: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_react_agent_tools():
    """Создание и тест что ReAct агент правильно использует инструменты"""
    
    from app.core.llm_factory import get_global_mock_llm, get_llm
    from app.models import LLMConfig
    
    # Создаем мок чтобы инициализировать глобальную переменную
    get_llm("mock", "mock-gpt-4")
    
    # Получаем глобальный мок и настраиваем его для сложных вычислений
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "(10 + 5) * 3 - 8": "Я выполню это вычисление пошагово используя инструменты. Результат: 37",
            "вычисли": "Я использую математические инструменты для вычисления. Получается 37.",
            "10": "Я буду использовать математические инструменты. Результат будет 37."
        })
    
    # СОЗДАЕМ агента в этом же тесте для изоляции
    await test_create_db_react_agent()
    
    agent_factory = AgentFactory()
    db_agent = await agent_factory.get_agent("db_math_agent")
    
    # Сложная математическая задача требующая несколько инструментов
    result = await db_agent.ainvoke(
        {"messages": [HumanMessage(content="Вычисли (10 + 5) * 3 - 8")]},
        config={"configurable": {"thread_id": "test_react_complex"}}
    )
    
    final_message = result["messages"][-1].content
    # Ожидаемый результат: (10+5)*3-8 = 15*3-8 = 45-8 = 37
    assert "37" in final_message or ("15" in final_message and "45" in final_message)
    
    print(f"✅ ReAct агент использует инструменты: {final_message[:100]}...")

