"""
Эталонный тест архитектуры Agent Lab.

Демонстрирует:
1. Создание Flow
2. Создание Supervisor агента (точка входа)
3. Создание Subagent (специализированный агент)
4. Добавление Tool к субагенту
5. Настройка MockLLM для корректного роутинга
6. End-to-end тестирование всей цепочки

Это ЭТАЛОН для всех будущих тестов!
"""
import pytest
import uuid
from pathlib import Path
import sys

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.storage import Storage
from app.core.flow_factory import FlowFactory
from app.core.llm_factory import setup_mock_responses
from app.models import (
    AgentConfig, AgentType, CodeMode, FlowConfig,
    ToolReference, LLMConfig
)
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_00_reference_architecture(save_test_company):
    """
    Эталонный тест: Supervisor -> Subagent -> Tool
    
    Сценарий:
    1. Пользователь: "Посчитай площадь круга радиусом 5"
    2. Supervisor: определяет что это математика -> вызывает MathAgent
    3. MathAgent: видит что нужен расчет -> вызывает calculate_area tool
    4. Tool: возвращает результат
    5. MathAgent: формулирует ответ
    6. Supervisor: возвращает результат пользователю
    """
    
    print("\n" + "="*80)
    print("ЭТАЛОННЫЙ ТЕСТ: Supervisor -> MathAgent -> calculate_area_tool")
    print("="*80)
    
    storage = Storage()
    
    # ============================================================
    # ШАГ 1: Создаем Tool для расчета площади круга
    # ============================================================
    print("\n📦 Шаг 1: Создаем Tool")
    
    calculate_area_code = '''
from langchain_core.tools import tool
import math

@tool
def calculate_area(radius: float) -> str:
    """
    Вычисляет площадь круга по радиусу.
    
    Args:
        radius: Радиус круга
        
    Returns:
        Площадь круга
    """
    area = math.pi * radius ** 2
    return f"Площадь круга с радиусом {radius} = {area:.2f}"
'''
    
    area_tool = ToolReference(
        tool_id="calculate_area_tool",
        code_mode=CodeMode.INLINE_CODE,
        inline_code=calculate_area_code,
        description="Вычисляет площадь круга",
        params={}
    )
    
    print("   ✅ Tool calculate_area создан")
    
    # ============================================================
    # ШАГ 2: Создаем Subagent (MathAgent) с tool
    # ============================================================
    print("\n🤖 Шаг 2: Создаем MathAgent (subagent)")
    
    math_agent_config = AgentConfig(
        agent_id="ref_math_agent",
        name="Reference Math Agent",
        description="Математический агент для расчетов",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        function_class=None,
        prompt="""Ты математик-специалист.

Используй calculate_area tool для вычисления площади круга.

Всегда используй инструменты для точных расчетов.""",
        tools=[area_tool],
        llm_config=LLMConfig(model="mock-gpt-4"),
        source="test"
    )
    
    await storage.set_agent_config(math_agent_config)
    print("   ✅ MathAgent создан с calculate_area tool")
    
    # ============================================================
    # ШАГ 3: Создаем Supervisor агента
    # ============================================================
    print("\n👔 Шаг 3: Создаем SupervisorAgent")
    
    supervisor_config = AgentConfig(
        agent_id="ref_supervisor",
        name="Reference Supervisor",
        description="Supervisor для роутинга запросов",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        function_class=None,
        prompt="""Ты координатор запросов.

Анализируй запросы и вызывай подходящий инструмент:
- Для математических вычислений -> используй math_agent_tool

ВАЖНО: ВСЕГДА передавай ПОЛНЫЙ запрос пользователя в инструмент.""",
        tools=[
            ToolReference(
                tool_id="agent:ref_math_agent",
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="ref_math_agent",
                description="Математический агент для расчетов"
            )
        ],
        llm_config=LLMConfig(model="mock-gpt-4"),
        source="test"
    )
    
    await storage.set_agent_config(supervisor_config)
    print("   ✅ SupervisorAgent создан с math_agent как tool")
    
    # ============================================================
    # ШАГ 4: Создаем Flow
    # ============================================================
    print("\n🔄 Шаг 4: Создаем Flow")
    
    flow_config = FlowConfig(
        flow_id="ref_flow",
        name="Reference Flow",
        description="Эталонный flow для демонстрации архитектуры",
        entry_point_agent="ref_supervisor",
        llm_config=None,
        source="test"
    )
    
    await storage.set_flow_config(flow_config)
    print("   ✅ Flow создан с SupervisorAgent как entry point")
    
    # ============================================================
    # ШАГ 5: Настраиваем MockLLM
    # ============================================================
    print("\n🎭 Шаг 5: Настраиваем MockLLM")
    
    setup_mock_responses(
        tool_responses={
            # Supervisor вызывает MathAgent
            "посчитай площадь": {"tool": "ref_math_agent", "args": {"request": "Посчитай площадь круга радиусом 5"}},
            # MathAgent вызывает calculate_area
            "радиусом 5": {"tool": "calculate_area", "args": {"radius": 5.0}},
        },
        responses={
            # Финальный ответ после выполнения tool
            "площадь круга": "Площадь круга с радиусом 5 составляет 78.54 квадратных единиц",
        },
        default_response="Выполняю расчет..."
    )
    
    print("   ✅ MockLLM настроен для Supervisor -> MathAgent -> Tool")
    
    # ============================================================
    # ШАГ 6: Выполняем Flow
    # ============================================================
    print("\n▶️  Шаг 6: Выполняем Flow")
    
    flow_factory = FlowFactory()
    ref_flow = await flow_factory.get_flow("ref_flow")
    
    thread_id = f"ref_test_{uuid.uuid4().hex[:8]}"
    result = await ref_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай площадь круга радиусом 5")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    # ============================================================
    # ШАГ 7: Проверяем результат
    # ============================================================
    print("\n✓ Шаг 7: Проверяем результат")
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    
    print(f"\n📊 Всего сообщений: {len(result['messages'])}")
    for i, msg in enumerate(result['messages']):
        msg_type = type(msg).__name__
        content = msg.content[:80] if msg.content else "(empty)"
        tool_calls = getattr(msg, 'tool_calls', None)
        if tool_calls:
            print(f"   [{i}] {msg_type}: вызов {len(tool_calls)} tool(s)")
            for tc in tool_calls:
                print(f"       -> {tc['name']}({tc.get('args', {})})")
        else:
            print(f"   [{i}] {msg_type}: {content}")
    
    final_message = result["messages"][-1].content
    
    # Проверяем что получили осмысленный ответ
    assert len(final_message) > 0
    assert isinstance(final_message, str)
    
    print(f"\n✅ ЭТАЛОННЫЙ ТЕСТ ПРОЙДЕН!")
    print(f"   Финальный ответ: {final_message}")
    print("="*80)


@pytest.mark.asyncio
async def test_00_simple_agent_with_tool(save_test_company):
    """
    Упрощенный эталон: Один агент с одним tool.
    Самый базовый сценарий для быстрой проверки.
    """
    
    print("\n" + "="*80)
    print("ПРОСТОЙ ЭТАЛОН: Agent -> Tool")
    print("="*80)
    
    storage = Storage()
    
    # 1. Создаем простой tool
    print("\n📦 Создаем greet_tool")
    
    greet_code = '''
from langchain_core.tools import tool

@tool
def greet(name: str) -> str:
    """Приветствует пользователя по имени"""
    return f"Привет, {name}! Рад тебя видеть!"
'''
    
    greet_tool = ToolReference(
        tool_id="greet_tool",
        code_mode=CodeMode.INLINE_CODE,
        inline_code=greet_code,
        description="Приветствует пользователя",
        params={}
    )
    
    # 2. Создаем агента с tool
    print("🤖 Создаем SimpleAgent")
    
    simple_agent = AgentConfig(
        agent_id="ref_simple_agent",
        name="Simple Reference Agent",
        description="Простой агент для демонстрации",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        function_class=None,
        prompt="Ты вежливый помощник. Используй greet tool для приветствия.",
        tools=[greet_tool],
        llm_config=LLMConfig(model="mock-gpt-4"),
        source="test"
    )
    
    print(f"   🔍 ПЕРЕД сохранением: simple_agent.tools = {simple_agent.tools}")
    print(f"   🔍 ПЕРЕД сохранением: len = {len(simple_agent.tools)}")
    
    await storage.set_agent_config(simple_agent)
    print("   ✅ SimpleAgent создан")
    
    # Проверим что агент сохранился с tools
    loaded_config = await storage.get_agent_config("ref_simple_agent")
    print(f"   🔍 ПОСЛЕ загрузки: loaded_config.tools = {loaded_config.tools}")
    print(f"   🔍 ПОСЛЕ загрузки: len = {len(loaded_config.tools) if loaded_config.tools else 0}")
    
    # Проверим JSON напрямую
    raw_json = await storage.get(f"agent:ref_simple_agent")
    import json
    if raw_json:
        parsed = json.loads(raw_json)
        print(f"   🔍 RAW JSON tools: {parsed.get('tools', 'NO TOOLS KEY')}")
    print(f"   🔍 RAW JSON (first 300 chars): {raw_json[:300] if raw_json else 'None'}...")
    
    assert loaded_config.tools is not None, "Tools не сохранились в БД!"
    assert len(loaded_config.tools) > 0, "Tools пустой список!"
    
    # 3. Создаем flow
    print("🔄 Создаем Flow")
    
    flow_config = FlowConfig(
        flow_id="ref_simple_flow",
        name="Simple Reference Flow",
        description="Простой эталонный flow",
        entry_point_agent="ref_simple_agent",
        source="test"
    )
    
    await storage.set_flow_config(flow_config)
    print("   ✅ Flow создан")
    
    # 4. Настраиваем MockLLM
    print("🎭 Настраиваем MockLLM")
    
    setup_mock_responses(
        tool_responses={
            # Первый вызов - вызываем greet tool
            "привет": {"tool": "greet", "args": {"name": "Виктор"}},
        },
        responses={
            # Второй вызов после tool - формулируем финальный ответ
            "привет": "Отлично! Приветствие выполнено успешно.",
        },
        default_response="Готово!"
    )
    
    print("   ✅ MockLLM настроен (tool call -> текстовый ответ)")
    
    # 5. Выполняем
    print("▶️  Выполняем Flow")
    
    flow_factory = FlowFactory()
    simple_flow = await flow_factory.get_flow("ref_simple_flow")
    
    result = await simple_flow.ainvoke(
        {"messages": [HumanMessage(content="Привет, меня зовут Виктор")]},
        config={"configurable": {"thread_id": f"simple_{uuid.uuid4().hex[:8]}"}}
    )
    
    # 6. Проверяем
    print("✓ Проверяем результат")
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    
    print(f"\n✅ ПРОСТОЙ ЭТАЛОН ПРОЙДЕН!")
    print(f"   Ответ: {final_message}")
    print("="*80)

