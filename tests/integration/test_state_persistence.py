"""
Чистый тест персистентности state между вызовами тулов.
"""

import pytest
from langchain_core.messages import HumanMessage

from apps.agents.models import AgentConfig, AgentType, LLMConfig, FlowConfig
from apps.agents.tools.task.delayed_task_tools import DELAYED_TASK_TOOLS


@pytest.mark.asyncio
async def test_tools_persist_state_between_calls(migrated_db, agent_factory, agent_repo, flow_repo, mock_llm, unique_id, test_context):
    """
    Чистый тест: агент создает задачу → агент показывает список → задача там есть.
    Проверяет что изменения state персистятся между вызовами.
    """
    from core.context import get_context, set_context

    # Создаем агента
    agent_config = AgentConfig(
        agent_id="state_test_agent",
        name="State Test Agent",
        type=AgentType.REACT,
        prompt="Ты тестовый агент.",
        tools=DELAYED_TASK_TOOLS,
        llm_config=LLMConfig(model="mock-gpt-4", temperature=0.1, context_window=10000),
    )

    await agent_repo.set(agent_config)

    # Создаем Flow
    flow_config = FlowConfig(
        flow_id="state_test_flow",
        name="State Test Flow",
        entry_point_agent="state_test_agent"
    )

    await flow_repo.set(flow_config)

    # Устанавливаем flow_config в контекст
    current_context = get_context()
    current_context.flow_config = flow_config
    set_context(current_context)

    # Настраиваем mock_llm ДО создания агента
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            tool_responses={
                "создай": {
                    "tool": "create_delayed_task",
                    "args": {
                        "message": "Тестовая задача",
                        "delay_seconds": 3600
                    }
                }
            },
            default_response="Готово"
        )

    # Загружаем агента
    agent = await agent_factory.get_agent("state_test_agent")

    thread_id = unique_id("state_persist_test")
    config = {"configurable": {"thread_id": thread_id}}

    # ШАГ 1: Агент создает задачу
    print("\n" + "="*60)
    print("ШАГ 1: Создание задачи")
    print("="*60)

    result1 = await agent.ainvoke({
        "messages": [HumanMessage(content="Создай задачу")]
    }, config)

    print(f"\n✅ Результат 1:")
    print(f"   Store keys: {list(result1.get('store', {}).keys())}")
    print(f"   delayed_tasks: {'delayed_tasks' in result1.get('store', {})}")

    if "store" in result1 and "delayed_tasks" in result1["store"]:
        print(f"   Задач создано: {len(result1['store']['delayed_tasks'])}")

    # ШАГ 2: Агент показывает список задач (новый вызов, должен загрузить state из checkpointer)
    print("\n" + "="*60)
    print("ШАГ 2: Список задач")
    print("="*60)

    # Настраиваем MockLLM для второго вызова
    if global_mock:
        global_mock.reset_call_counts()  # Сбрасываем счетчики
        global_mock.configure(
            tool_responses={
                "покажи": {
                    "tool": "list_delayed_tasks",
                    "args": {}
                }
            },
            default_response="Готово"
        )

    result2 = await agent.ainvoke({
        "messages": [HumanMessage(content="покажи")]
    }, config)

    print(f"\n✅ Результат 2:")
    print(f"   Store keys: {list(result2.get('store', {}).keys())}")
    print(f"   delayed_tasks: {'delayed_tasks' in result2.get('store', {})}")

    if "store" in result2 and "delayed_tasks" in result2["store"]:
        print(f"   Задач в store: {len(result2['store']['delayed_tasks'])}")
        assert len(result2["store"]["delayed_tasks"]) > 0, "Задачи НЕ сохранились в checkpointer!"
        print(f"   ✅ Задачи сохранились между вызовами!")
    else:
        print(f"   ❌ delayed_tasks отсутствует в store после второго вызова!")
        raise AssertionError("State НЕ персистится между вызовами!")

    # Проверяем сообщения
    messages = result2.get("messages", [])
    list_response = None
    for msg in messages:
        content = msg.content if hasattr(msg, 'content') else str(msg)
        if "📅 Отложенные задачи" in content or "Тестовая задача" in content:
            list_response = content
            break

    if list_response:
        print(f"\n✅ Список задач получен:")
        print(list_response[:200])

    print(f"\n" + "="*60)
    print("✅ ТЕСТ ПРОШЕЛ: State персистится между вызовами!")
    print("="*60)

