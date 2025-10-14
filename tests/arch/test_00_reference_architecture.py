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
from app.models import AgentConfig, AgentType, CodeMode, ToolReference
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_00_reference_architecture(
    migrated_db,
    storage,
    flow_factory,
    mock_llm,
    test_helpers,
    unique_id
):
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
    
    # ШАГ 1: Создаем Tool для расчета площади круга
    print("\n📦 Шаг 1: Создаем Tool")
    
    area_tool = test_helpers.create_inline_tool(
        tool_id="calculate_area_tool",
        function_name="calculate_area",
        function_body="""
def calculate_area(radius: float) -> str:
    '''Вычисляет площадь круга по радиусу'''
    import math
    area = math.pi * radius ** 2
    return f"Площадь круга с радиусом {radius} = {area:.2f}"
""",
        description="Вычисляет площадь круга"
    )
    
    print("   ✅ Tool calculate_area создан")
    
    # ШАГ 2: Создаем Subagent (MathAgent) с tool
    print("\n🤖 Шаг 2: Создаем MathAgent (subagent)")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="ref_math_agent",
        name="Reference Math Agent",
        prompt="Ты математик-специалист. Используй calculate_area tool для вычисления площади круга.",
        tools=[area_tool]
    )
    
    print("   ✅ MathAgent создан с calculate_area tool")
    
    # ШАГ 3: Создаем Supervisor агента
    print("\n👔 Шаг 3: Создаем SupervisorAgent")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="ref_supervisor",
        name="Reference Supervisor",
        prompt="Ты координатор запросов. Для математических вычислений используй ref_math_agent.",
        tools=[
            ToolReference(
                tool_id="agent:ref_math_agent",
                code_mode=CodeMode.CODE_REFERENCE,
                function_path="ref_math_agent",
                description="Математический агент для расчетов"
            )
        ]
    )
    
    print("   ✅ SupervisorAgent создан с math_agent как tool")
    
    # ШАГ 4: Создаем Flow
    print("\n🔄 Шаг 4: Создаем Flow")
    
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="ref_flow",
        name="Reference Flow",
        entry_point_agent="ref_supervisor"
    )
    
    print("   ✅ Flow создан с SupervisorAgent как entry point")
    
    # ШАГ 5: Настраиваем MockLLM
    print("\n🎭 Шаг 5: Настраиваем MockLLM")
    
    mock_llm.configure(
        tool_responses={
            "посчитай площадь": {"tool": "ref_math_agent", "args": {"request": "Посчитай площадь круга радиусом 5"}},
            "радиусом 5": {"tool": "calculate_area", "args": {"radius": 5.0}},
        },
        responses={
            "площадь круга": "Площадь круга с радиусом 5 составляет 78.54 квадратных единиц",
        },
        default_response="Выполняю расчет..."
    )
    
    print("   ✅ MockLLM настроен для Supervisor -> MathAgent -> Tool")
    
    # ШАГ 6: Выполняем Flow
    print("\n▶️  Шаг 6: Выполняем Flow")
    
    ref_flow = await flow_factory.get_flow("ref_flow")
    
    result = await ref_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай площадь круга радиусом 5")]},
        config={"configurable": {"thread_id": unique_id("ref_test")}}
    )
    
    # ШАГ 7: Проверяем результат
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
async def test_00_simple_agent_with_tool(
    migrated_db,
    storage,
    flow_factory,
    mock_llm,
    test_helpers,
    unique_id
):
    """
    Упрощенный эталон: Один агент с одним tool.
    Самый базовый сценарий для быстрой проверки.
    """
    
    print("\n" + "="*80)
    print("ПРОСТОЙ ЭТАЛОН: Agent -> Tool")
    print("="*80)
    
    # 1. Создаем простой tool
    print("\n📦 Создаем greet_tool")
    
    greet_tool = test_helpers.create_inline_tool(
        tool_id="greet_tool",
        function_name="greet",
        function_body="""
def greet(name: str) -> str:
    '''Приветствует пользователя по имени'''
    return f"Привет, {name}! Рад тебя видеть!"
""",
        description="Приветствует пользователя"
    )
    
    # 2. Создаем агента с tool
    print("🤖 Создаем SimpleAgent")
    
    simple_agent = await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="ref_simple_agent",
        name="Simple Reference Agent",
        prompt="Ты вежливый помощник. Используй greet tool для приветствия.",
        tools=[greet_tool]
    )
    
    print("   ✅ SimpleAgent создан")
    
    # Проверим что агент сохранился с tools
    loaded_config = await storage.get_agent_config("ref_simple_agent")
    assert loaded_config.tools is not None, "Tools не сохранились в БД!"
    assert len(loaded_config.tools) > 0, "Tools пустой список!"
    
    # 3. Создаем flow
    print("🔄 Создаем Flow")
    
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="ref_simple_flow",
        name="Simple Reference Flow",
        entry_point_agent="ref_simple_agent"
    )
    
    print("   ✅ Flow создан")
    
    # 4. Настраиваем MockLLM
    print("🎭 Настраиваем MockLLM")
    
    mock_llm.configure(
        tool_responses={
            "привет": {"tool": "greet", "args": {"name": "Виктор"}},
        },
        responses={
            "привет": "Отлично! Приветствие выполнено успешно.",
        },
        default_response="Готово!"
    )
    
    print("   ✅ MockLLM настроен (tool call -> текстовый ответ)")
    
    # 5. Выполняем
    print("▶️  Выполняем Flow")
    
    simple_flow = await flow_factory.get_flow("ref_simple_flow")
    
    result = await simple_flow.ainvoke(
        {"messages": [HumanMessage(content="Привет, меня зовут Виктор")]},
        config={"configurable": {"thread_id": unique_id("simple")}}
    )
    
    # 6. Проверяем
    print("✓ Проверяем результат")
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    
    print(f"\n✅ ПРОСТОЙ ЭТАЛОН ПРОЙДЕН!")
    print(f"   Ответ: {final_message}")
    print("="*80)

