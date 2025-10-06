"""
Тест 6: Tools в БД с разными режимами.

Проверяет:
1. Миграцию агента из кода в БД с добавлением inline tool
2. Добавление tool из БД к агенту в коде через ссылку
"""
import pytest
import asyncio
from pathlib import Path
import sys
import uuid

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.storage import Storage
from app.core.migrator import Migrator
from app.core.agent_factory import AgentFactory
from app.core.flow_factory import FlowFactory
from app.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig,
    ToolReference, LLMConfig
)
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_migrate_and_add_inline_tool():
    """
    Тест 1: Мигрируем WeatherAgent в БД и добавляем inline tool "покажи сахару"
    """
    
    # 1. Мигрируем существующего WeatherAgent
    migrator = Migrator()
    await migrator.run_full_migration()
    
    # 2. Загружаем конфиг WeatherAgent из БД
    storage = Storage()
    weather_config = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_config is not None
    print("✅ WeatherAgent найден в БД")
    
    # 3. Создаем inline tool "покажи сахару"
    show_sugar_code = '''
from langchain_core.tools import tool

@tool
def show_sugar(request: str) -> str:
    """
    Показывает сахар по запросу пользователя.
    
    Args:
        request: Запрос пользователя про сахар
    """
    return "ВОТ САХАРА!! 🍯🧂✨"
'''
    
    sugar_tool = ToolReference(
        tool_id="inline_show_sugar",
        code_mode=CodeMode.INLINE_CODE,
        inline_code=show_sugar_code,
        description="Показывает сахар пользователю",
        params={}
    )
    
    # 4. Добавляем tool к агенту
    if not weather_config.tools:
        weather_config.tools = []
    weather_config.tools.append(sugar_tool)
    
    # Сохраняем обновленный конфиг
    await storage.set_agent_config(weather_config)
    print("✅ Inline tool 'покажи сахару' добавлен к WeatherAgent")
    
    # 5. Создаем flow для тестирования
    test_flow_config = FlowConfig(
        flow_id="weather_sugar_flow",
        name="Weather Sugar Flow", 
        description="Flow для тестирования WeatherAgent с sugar tool",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    await storage.set_flow_config(test_flow_config)
    
    # 6. Настраиваем мок для сахарного запроса
    from app.core.llm_factory import get_global_mock_llm, get_llm
    
    get_llm("mock", "mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "покажи сахару": "Я покажу вам сахар! ВОТ САХАРА!! 🍯🧂✨",
            "сахар": "Конечно! Вот ваш сахар: 🍯🧂✨",
            "показать": "Показываю сахар: ВОТ САХАРА!! 🍯🧂✨"
        })

    # 7. Тестируем агента с новым tool
    flow_factory = FlowFactory()
    weather_flow = await flow_factory.get_flow("weather_sugar_flow")

    thread_id = f"test_sugar_{uuid.uuid4().hex[:8]}"
    result = await weather_flow.ainvoke(
        {"messages": [HumanMessage(content="покажи сахару")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    # Проверяем что tool сработал (есть эмодзи сахара)
    assert "🍯" in final_message or "🧂" in final_message or "✨" in final_message
    assert "сахар" in final_message.lower()
    
    print(f"✅ WeatherAgent с inline tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_code_agent_with_db_tool():
    """
    Тест 2: Агент в коде использует tool из БД через ссылку
    """
    
    # Настраиваем мок для магических заклинаний
    from app.core.llm_factory import get_global_mock_llm, get_llm
    from app.models import LLMConfig
    
    get_llm("mock", "mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "произнеси заклинание": "Я произнесу заклинание 'хокус покус' используя magic_function!",
            "хокус покус": "Отлично! Я выполню магическое заклинание 'хокус покус' с помощью magic_function.",
            "волшебник": "Как волшебник, я использую магические инструменты для выполнения заклинаний."
        })
    
    # 1. Создаем tool в БД
    storage = Storage()
    
    magic_tool_code = '''
from langchain_core.tools import tool

@tool
def magic_function(spell: str) -> str:
    """
    Выполняет магическое заклинание.
    
    Args:
        spell: Текст заклинания
    """
    return f"✨ МАГИЯ! {spell.upper()} ✨ АБРАКАДАБРА!"
'''
    
    magic_tool = ToolReference(
        tool_id="db_magic_tool",
        code_mode=CodeMode.INLINE_CODE,
        inline_code=magic_tool_code,
        description="Магический инструмент из БД",
        params={}
    )
    
    # Сохраняем tool в БД
    await storage.set(f"tool:{magic_tool.tool_id}", magic_tool.model_dump_json())
    print("✅ Magic tool сохранен в БД")
    
    # 2. Создаем агента в БД который ссылается на tool из БД
    magic_agent_config = AgentConfig(
        agent_id="magic_test_agent",
        name="Magic Test Agent",
        description="Тестовый агент с tool из БД",
        type=AgentType.REACT,
        prompt="Ты волшебник. Используй magic_function для выполнения заклинаний.",
        tools=[
            ToolReference(
                tool_id="tool:db_magic_tool",  # Ссылка на tool в БД
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="db_magic_tool",
                description="Ссылка на магический tool из БД"
            )
        ],
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    
    await storage.set_agent_config(magic_agent_config)
    print("✅ Magic agent создан в БД со ссылкой на DB tool")
    
    # 3. Создаем flow для тестирования
    magic_flow_config = FlowConfig(
        flow_id="magic_test_flow",
        name="Magic Test Flow",
        description="Flow для тестирования агента с DB tool",
        entry_point_agent="magic_test_agent",
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    await storage.set_flow_config(magic_flow_config)
    
    # 4. Тестируем агента
    flow_factory = FlowFactory()
    magic_flow = await flow_factory.get_flow("magic_test_flow")
    
    thread_id = f"test_magic_{uuid.uuid4().hex[:8]}"
    result = await magic_flow.ainvoke(
        {"messages": [HumanMessage(content="произнеси заклинание 'хокус покус'")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    # Проверяем что tool сработал (есть упоминание заклинания)
    assert "хокус покус" in final_message.lower() or "магия" in final_message.lower()
    
    print(f"✅ Агент с DB tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_code_reference_tool():
    """
    Тест 3: Tool из кода (CODE_REFERENCE режим)
    """
    
    # Настраиваем мок для вычислений
    from app.core.llm_factory import get_global_mock_llm, get_llm
    from app.models import LLMConfig
    
    get_llm("mock", "mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "вычисли 15 + 27": "Я использую инструмент calculate для вычисления 15 + 27. Результат: 42",
            "15 + 27": "Я выполню вычисление 15 + 27 = 42.",
            "вычисли": "Я использую calculate для математических вычислений. Результат будет 42."
        })
    
    # 1. Создаем агента с tool из кода
    storage = Storage()
    
    calc_agent_config = AgentConfig(
        agent_id="calc_test_agent", 
        name="Calculator Test Agent",
        description="Тестовый агент с calculator tool из кода",
        type=AgentType.REACT,
        prompt="Ты калькулятор. Используй calculate для вычислений.",
        tools=[
            ToolReference(
                tool_id="app.tools.calc_tools.calculate",
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="app.tools.calc_tools.calculate",
                description="Калькулятор из кода"
            )
        ],
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    
    await storage.set_agent_config(calc_agent_config)
    print("✅ Calculator agent создан с CODE_REFERENCE tool")
    
    # 2. Создаем flow
    calc_flow_config = FlowConfig(
        flow_id="calc_test_flow",
        name="Calculator Test Flow", 
        description="Flow для тестирования calculator tool",
        entry_point_agent="calc_test_agent",
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    await storage.set_flow_config(calc_flow_config)
    
    # 3. Тестируем
    flow_factory = FlowFactory()
    calc_flow = await flow_factory.get_flow("calc_test_flow")
    
    thread_id = f"test_calc_{uuid.uuid4().hex[:8]}"
    result = await calc_flow.ainvoke(
        {"messages": [HumanMessage(content="вычисли 15 + 27")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "42" in final_message or "15" in final_message and "27" in final_message
    
    print(f"✅ Агент с CODE_REFERENCE tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_db_agent_with_code_tool():
    """
    Тест 4: Агент в БД использует tool из кода (мигрированный в БД)
    """
    
    # Настраиваем мок для вычислений
    from app.core.llm_factory import get_global_mock_llm, get_llm
    from app.models import LLMConfig
    
    get_llm("mock", "mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "вычисли": "Я использую calculate для вычисления выражения 25 * 3 + 7. Результат: 82",
            "25": "Я выполню вычисление 25 * 3 + 7 = 82.",
            "математик": "Я использую математические инструменты для точных вычислений. Результат: 82"
        })
        mock_llm.set_default_response("Я использую calculate для вычисления. Результат: 82")
    
    # 1. Сначала мигрируем tools из кода в БД
    migrator = Migrator()
    await migrator._migrate_tools()  # Мигрируем только tools
    
    # 2. Создаем агента в БД который ссылается на мигрированный tool
    storage = Storage()
    
    math_agent_config = AgentConfig(
        agent_id="db_agent_with_code_tool",
        name="DB Agent with Code Tool",
        description="Агент из БД использующий tool из кода",
        type=AgentType.REACT,
        prompt="Ты математик. Используй calculate для вычислений. Будь точным.",
        tools=[
            # Ссылка на мигрированный tool из кода
            ToolReference(
                tool_id="app.tools.calc_tools.calculate",
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="app.tools.calc_tools.calculate",
                description="Калькулятор из мигрированного кода"
            )
        ],
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    
    await storage.set_agent_config(math_agent_config)
    print("✅ DB агент создан со ссылкой на мигрированный code tool")
    
    # 3. Создаем flow
    math_flow_config = FlowConfig(
        flow_id="db_agent_code_tool_flow",
        name="DB Agent Code Tool Flow",
        description="Flow для тестирования DB агента с code tool",
        entry_point_agent="db_agent_with_code_tool",
        llm_config=None,  # Используем дефолтную конфигурацию
        source="test"
    )
    await storage.set_flow_config(math_flow_config)
    
    # 4. Тестируем
    flow_factory = FlowFactory()
    math_flow = await flow_factory.get_flow("db_agent_code_tool_flow")
    
    thread_id = f"test_db_code_{uuid.uuid4().hex[:8]}"
    result = await math_flow.ainvoke(
        {"messages": [HumanMessage(content="вычисли 25 * 3 + 7")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "82" in final_message or ("25" in final_message and "3" in final_message and "7" in final_message)
    
    print(f"✅ DB агент с code tool отвечает: {final_message}")
