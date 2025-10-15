"""
Тест 6: Tools в БД с разными режимами.

Проверяет:
1. Миграцию агента из кода в БД с добавлением inline tool
2. Добавление tool из БД к агенту в коде через ссылку
"""
import pytest
from app.models import AgentConfig, AgentType, CodeMode, FlowConfig, ToolReference, LLMConfig
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_migrate_and_add_inline_tool(migrated_db, storage, flow_factory, mock_llm, unique_id, test_helpers):
    """
    Тест 1: Создаем агента в БД и добавляем inline tool "покажи сахару"
    """
    
    # 1. Создаем inline tool "покажи сахару"
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
        description="Показывает сахар пользователю"
    )
    
    # 2. Создаем DB-only агента с sugar tool
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="db_sugar_agent",
        name="DB Sugar Agent",
        prompt="Ты помощник который показывает сахар. Используй show_sugar tool когда пользователь просит показать сахар.",
        tools=[sugar_tool]
    )
    print("✅ DB агент с inline tool создан")
    
    # 3. Настраиваем mock LLM
    mock_llm.configure(
        responses={
            "покажи": "ВОТ САХАРА!! 🍯🧂✨",
            "сахар": "ВОТ САХАРА!! 🍯🧂✨",
        }
    )
    
    # 4. Создаем flow для тестирования
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="db_sugar_flow",
        name="DB Sugar Flow",
        entry_point_agent="db_sugar_agent"
    )

    # 5. Выполняем flow
    sugar_flow = await flow_factory.get_flow("db_sugar_flow")

    result = await sugar_flow.ainvoke(
        {"messages": [HumanMessage(content="покажи сахару")]},
        config={"configurable": {"thread_id": unique_id("sugar")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    
    print(f"🔍 Финальное сообщение: '{final_message}'")
    print(f"🔍 Все сообщения: {len(result['messages'])}")
    for i, msg in enumerate(result['messages']):
        print(f"  [{i}] {type(msg).__name__}: {msg.content[:100] if msg.content else 'empty'}")
    
    # Проверяем что tool сработал (есть эмодзи сахара)
    assert "🍯" in final_message or "🧂" in final_message or "✨" in final_message
    assert "сахар" in final_message.lower()
    
    print(f"✅ DB агент с inline tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_code_agent_with_db_tool(migrated_db, storage, flow_factory, mock_llm, unique_id, test_helpers):
    """
    Тест 2: Агент в коде использует tool из БД через ссылку
    """
    mock_llm.configure(
        tool_responses={
            "заклинание": {"tool": "main", "args": {"spell": "хокус покус"}},
        },
        responses={
            "заклинание": "✨ МАГИЯ! ХОКУС ПОКУС ✨ АБРАКАДАБРА!",
        },
        default_response="Использую магию!"
    )
    
    magic_tool = test_helpers.create_inline_tool(
        tool_id="db_magic_tool",
        function_name="main",
        function_body='''
def main(spell: str) -> str:
    """Выполняет магическое заклинание
    
    Args:
        spell: Текст заклинания
    """
    return f"✨ МАГИЯ! {spell.upper()} ✨ АБРАКАДАБРА!"
''',
        description="Магический инструмент из БД"
    )
    
    await storage.set(f"tool:{magic_tool.tool_id}", magic_tool.model_dump_json())
    print("✅ Magic tool сохранен в БД")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="magic_test_agent",
        name="Magic Test Agent",
        prompt="Ты волшебник. Используй main для выполнения заклинаний.",
        tools=[magic_tool]
    )
    print("✅ Magic agent создан в БД со ссылкой на DB tool")
    
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="magic_test_flow",
        name="Magic Test Flow",
        entry_point_agent="magic_test_agent"
    )
    
    magic_flow = await flow_factory.get_flow("magic_test_flow")
    
    result = await magic_flow.ainvoke(
        {"messages": [HumanMessage(content="произнеси заклинание 'хокус покус'")]},
        config={"configurable": {"thread_id": unique_id("magic")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    assert any(word in final_message.lower() for word in ["магия", "магию", "волшебник", "хокус покус"])
    
    print(f"✅ Агент с DB tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_code_reference_tool(migrated_db, storage, flow_factory, mock_llm, unique_id, test_helpers):
    """
    Тест 3: Tool из кода (CODE_REFERENCE режим)
    """
    mock_llm.configure(
        tool_responses={
            "вычисли": {"tool": "calculate", "args": {"expression": "15 + 27"}},
        },
        responses={
            "вычисли": "Результат: 42",
        },
        default_response="42"
    )
    
    calc_tool = ToolReference(
        tool_id="app.tools.calc.calc_tools.calculate",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="app.tools.calc.calc_tools.calculate",
        description="Калькулятор из кода"
    )
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="calc_test_agent",
        name="Calculator Test Agent",
        prompt="Ты калькулятор. Используй calculate для вычислений.",
        tools=[calc_tool]
    )
    print("✅ Calculator agent создан с CODE_REFERENCE tool")
    
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="calc_test_flow",
        name="Calculator Test Flow",
        entry_point_agent="calc_test_agent"
    )
    
    calc_flow = await flow_factory.get_flow("calc_test_flow")
    
    result = await calc_flow.ainvoke(
        {"messages": [HumanMessage(content="вычисли 15 + 27")]},
        config={"configurable": {"thread_id": unique_id("calc")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "42" in final_message or ("15" in final_message and "27" in final_message)
    
    print(f"✅ Агент с CODE_REFERENCE tool отвечает: {final_message}")


@pytest.mark.asyncio
async def test_db_agent_with_code_tool(migrated_db, storage, flow_factory, mock_llm, unique_id, test_helpers):
    """
    Тест 4: Агент в БД использует tool из кода (мигрированный в БД)
    """
    mock_llm.configure(
        tool_responses={
            "вычисли": {"tool": "calculate", "args": {"expression": "25 * 3 + 7"}},
        },
        responses={
            "вычисли": "Результат: 82",
        },
        default_response="82"
    )
    
    code_tool = ToolReference(
        tool_id="app.tools.calc_tools.calculate",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="app.tools.calc_tools.calculate",
        description="Калькулятор из кода"
    )
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id="db_agent_with_code_tool",
        name="DB Agent with Code Tool",
        prompt="Ты математик. Используй calculate для вычислений. Будь точным.",
        tools=[code_tool]
    )
    print("✅ DB агент создан со ссылкой на code tool")
    
    await test_helpers.create_simple_flow(
        storage=storage,
        flow_id="db_agent_code_tool_flow",
        name="DB Agent Code Tool Flow",
        entry_point_agent="db_agent_with_code_tool"
    )
    
    math_flow = await flow_factory.get_flow("db_agent_code_tool_flow")
    
    result = await math_flow.ainvoke(
        {"messages": [HumanMessage(content="вычисли 25 * 3 + 7")]},
        config={"configurable": {"thread_id": unique_id("db_code")}}
    )
    
    assert "messages" in result
    final_message = result["messages"][-1].content
    assert "82" in final_message or ("25" in final_message and "3" in final_message and "7" in final_message)
    
    print(f"✅ DB агент с code tool отвечает: {final_message}")
