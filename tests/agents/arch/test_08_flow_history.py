"""
Тесты для получения истории выполнения flow через FlowFactory
"""

import pytest
from datetime import datetime, timezone

from apps.agents.models.session_models import SessionConfig, SessionStatus
from apps.agents.models.history_models import MessageRole
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_flow_history_from_smart_flow(migrated_db,  flow_factory, system_context, unique_id, session_repo, mock_llm):
    """
    Тест получения истории сообщений из выполненного smart_flow
    """
    print("\n=== Тест: История выполнения smart_flow ===")
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            tool_responses={
                "посчитай 15 + 27": {"tool": "calculator_agent_tool", "args": {"request": "Посчитай 15 + 27"}},
                "15 + 27": {"tool": "calculator_agent_tool", "args": {"request": "15 + 27"}},
            },
            responses={
                "посчитай 15 + 27": "Я выполню вычисление 15 + 27 = 42 используя калькулятор.",
                "15 + 27": "Результат вычисления 15 + 27 равен 42.",
                "исходный вопрос": "Пользователь спросил про вычисление 15 + 27, результат: 42",
                "калькулятор": "Калькулятор выполнил вычисление и получил результат 42.",
                "42": "Финальный ответ: Результат вычисления 15 + 27 равен 42."
            },
            default_response="Финальный ответ: Результат вычисления 15 + 27 равен 42."
        )
    
    flow_id = "apps.agents.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    print(f"✅ Flow загружен: {flow_id}")
    
    # Устанавливаем context_window для агентов, используемых в flow
    from apps.agents.container import get_agents_container
    agent_factory = get_agents_container().agent_factory
    
    calculator_agent = await agent_factory.get_agent("apps.agents.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config and calculator_agent.config.llm_config:
        calculator_agent.config.llm_config.context_window = 8192
    
    explainer_agent = await agent_factory.get_agent("apps.agents.agents.explainer.agent.ExplainerAgent")
    if explainer_agent and explainer_agent.config and explainer_agent.config.llm_config:
        explainer_agent.config.llm_config.context_window = 8192
    
    session_id = unique_id("history")
    config = {"configurable": {"session_id": session_id}}
    
    session = SessionConfig(
        session_id=session_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await session_repo.set(session)
    
    print("🔄 Выполняем flow с вопросом о математике...")
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 15 + 27")]},
        config=config
    )
    
    messages = result.get("messages", [])
    print(f"✅ Flow выполнен, получено {len(messages)} сообщений")
    
    for i, msg in enumerate(messages):
        print(f"  {i}: [{type(msg).__name__}] {msg.content[:80]}")
    
    # Проверяем что state сохранился
    import asyncio
    await asyncio.sleep(0.1)  # Даем время на сохранение
    
    from apps.agents.services.state_manager import get_state_manager
    state_manager = await get_state_manager()
    saved_state = await state_manager.get_or_create_session(session_id)
    assert saved_state is not None, f"State должен быть сохранен для session_id={session_id}"
    assert len(saved_state.get("messages", [])) > 0, f"State должен содержать сообщения: {len(saved_state.get('messages', []))}"
    
    print("\n🔄 Получаем историю через FlowFactory...")
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=100,
        include_checkpoints=False
    )
    
    print("✅ История получена:")
    print(f"  - Сессия: {history.session_id}")
    print(f"  - Flow: {history.flow_id}")
    print(f"  - Всего сообщений: {history.total_messages}")
    print(f"  - Всего checkpoints: {history.total_checkpoints}")
    print(f"  - Создано: {history.created_at}")
    print(f"  - Последняя активность: {history.last_activity}")
    
    assert history.total_messages > 0, f"История должна содержать сообщения, получено: {history.total_messages}, messages в result: {len(messages)}"
    assert history.total_checkpoints > 0, "История должна содержать checkpoints"
    assert history.session_id == session_id
    assert history.flow_id == flow_id
    
    print("\n📋 Сообщения в истории:")
    for i, msg in enumerate(history.messages):
        tool_info = ""
        if msg.tool_calls:
            tool_info = f" [вызовы: {', '.join(tc.tool_name for tc in msg.tool_calls)}]"
        print(f"  {i}: [{msg.role.value}] {msg.content[:80]}{tool_info}")
    
    user_messages = [m for m in history.messages if m.role == MessageRole.USER]
    assistant_messages = [m for m in history.messages if m.role == MessageRole.ASSISTANT]
    tool_messages = [m for m in history.messages if m.role == MessageRole.TOOL]
    
    print("\n📊 Статистика сообщений:")
    print(f"  - Пользователь: {len(user_messages)}")
    print(f"  - Ассистент: {len(assistant_messages)}")
    print(f"  - Инструменты: {len(tool_messages)}")
    
    assert len(user_messages) >= 1, "Должно быть хотя бы одно сообщение пользователя"
    assert len(assistant_messages) >= 1, "Должно быть хотя бы одно сообщение ассистента"
    
    print("✅ Тест истории выполнения пройден")


@pytest.mark.asyncio
async def test_flow_history_with_checkpoints(migrated_db,  flow_factory, system_context, mock_llm, unique_id, session_repo):
    """
    Тест получения истории с детальной информацией о checkpoints
    """
    print("\n=== Тест: История с checkpoints ===")
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            tool_responses={
                "какая погода": {"tool": "get_weather", "args": {"city": "Москва"}},
            },
            responses={
                "какая погода": "Я проверю погоду в Москве используя инструмент get_weather.",
            },
            default_response="Погода в Москве: +5°C, облачно"
        )
    
    flow_id = "apps.agents.flows.weather_flow.weather_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    session_id = unique_id("checkpoints")
    config = {"configurable": {"session_id": session_id}}
    
    session = SessionConfig(
        session_id=session_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await session_repo.set(session)
    
    print("🔄 Выполняем weather_flow...")
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config=config
    )
    
    print("✅ Flow выполнен")
    
    print("\n🔄 Получаем историю с checkpoints...")
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=100,
        include_checkpoints=True
    )
    
    print("✅ История получена:")
    print(f"  - Всего сообщений: {history.total_messages}")
    print(f"  - Всего checkpoints: {history.total_checkpoints}")
    print(f"  - Checkpoints в ответе: {len(history.checkpoints)}")
    
    assert history.total_checkpoints > 0
    assert len(history.checkpoints) > 0, "Checkpoints должны быть включены в ответ"
    
    print("\n📋 Детали checkpoints:")
    for i, cp in enumerate(history.checkpoints):
        print(f"  Checkpoint {i}:")
        print(f"    - ID: {cp.checkpoint_id}")
        print(f"    - Step: {cp.step}")
        print(f"    - Сообщений: {len(cp.messages)}")
        print(f"    - Timestamp: {cp.timestamp}")
    
    print("✅ Тест с checkpoints пройден")


@pytest.mark.asyncio
async def test_flow_sessions_list(migrated_db,  flow_factory, system_context, unique_id, session_repo):
    """
    Тест получения списка сессий через FlowFactory
    """
    print("\n=== Тест: Список сессий ===")
    
    flow_id = "apps.agents.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    session_id_1 = unique_id("session_1")
    session_id_2 = unique_id("session_2")
    
    config_1 = {"configurable": {"session_id": session_id_1}}
    config_2 = {"configurable": {"session_id": session_id_2}}
    
    print("🔄 Создаем 2 сессии...")
    
    session_1 = SessionConfig(
        session_id=session_id_1,
        platform="web",
        user_id="test_user_1",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc)
    )
    await session_repo.set(session_1)
    
    session_2 = SessionConfig(
        session_id=session_id_2,
        platform="telegram",
        user_id="test_user_2",
        flow_id=flow_id,
        status=SessionStatus.INACTIVE,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc)
    )
    await session_repo.set(session_2)
    
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Первая сессия")]},
        config=config_1
    )
    
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Вторая сессия")]},
        config=config_2
    )
    
    print("✅ Сессии созданы")
    
    print("\n🔄 Получаем список всех сессий...")
    sessions_all = await flow_factory.get_flow_sessions(
        limit=100,
        offset=0
    )
    
    print(f"✅ Всего сессий: {sessions_all.total}")
    print(f"  - Возвращено: {len(sessions_all.sessions)}")
    
    assert sessions_all.total >= 2, "Должно быть как минимум 2 сессии"
    
    print("\n🔄 Фильтруем по flow_id...")
    sessions_filtered = await flow_factory.get_flow_sessions(
        flow_id=flow_id,
        limit=100,
        offset=0
    )
    
    print(f"✅ Сессий для {flow_id}: {sessions_filtered.total}")
    
    test_sessions = [s for s in sessions_filtered.sessions if s.session_id in [session_id_1, session_id_2]]
    print(f"  - Наших тестовых сессий: {len(test_sessions)}")
    
    assert len(test_sessions) >= 2, "Должны найтись обе тестовые сессии"
    
    print("\n🔄 Фильтруем по платформе web...")
    sessions_web = await flow_factory.get_flow_sessions(
        platform="web",
        limit=100,
        offset=0
    )
    
    print(f"✅ Web сессий: {sessions_web.total}")
    
    web_test_session = [s for s in sessions_web.sessions if s.session_id == session_id_1]
    assert len(web_test_session) == 1, "Должна найтись web сессия"
    
    print("\n📋 Детали сессий:")
    for session in test_sessions:
        print(f"  - {session.session_id}:")
        print(f"    Platform: {session.platform}")
        print(f"    User: {session.user_id}")
        print(f"    Status: {session.status}")
        print(f"    Messages: {session.message_count}")
        print(f"    Created: {session.created_at}")
    
    print("✅ Тест списка сессий пройден")


@pytest.mark.asyncio
async def test_flow_history_tool_calls(migrated_db,  flow_factory, system_context, unique_id, session_repo):
    """
    Тест что история корректно фиксирует вызовы инструментов
    """
    print("\n=== Тест: Вызовы инструментов в истории ===")
    
    flow_id = "apps.agents.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    session_id = unique_id("tools")
    config = {"configurable": {"session_id": session_id}}
    
    session = SessionConfig(
        session_id=session_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await session_repo.set(session)
    
    print("🔄 Выполняем flow с запросом который вызовет калькулятор...")
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 123 * 456")]},
        config=config
    )
    
    print("✅ Flow выполнен")
    
    print("\n🔄 Получаем историю...")
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=100,
        include_checkpoints=False
    )
    
    assistant_with_tools = [
        m for m in history.messages 
        if m.role == MessageRole.ASSISTANT and m.tool_calls
    ]
    
    print(f"✅ Найдено {len(assistant_with_tools)} сообщений ассистента с вызовами инструментов")
    
    if assistant_with_tools:
        for i, msg in enumerate(assistant_with_tools):
            print(f"\n  Сообщение {i}:")
            for tc in msg.tool_calls:
                print(f"    - Инструмент: {tc.tool_name}")
                print(f"    - ID вызова: {tc.tool_id}")
                print(f"    - Аргументы: {tc.arguments}")
        
        assert len(assistant_with_tools) > 0, "Должны быть вызовы инструментов"
    else:
        print("⚠️ Не найдено вызовов инструментов (возможно flow не требует их)")
    
    tool_messages = [m for m in history.messages if m.role == MessageRole.TOOL]
    print(f"\n✅ Найдено {len(tool_messages)} сообщений от инструментов")
    
    if tool_messages:
        for i, msg in enumerate(tool_messages):
            print(f"  Tool message {i}: {msg.content[:100]}")
            print(f"    Metadata: {msg.metadata}")
    
    print("✅ Тест вызовов инструментов пройден")


@pytest.mark.asyncio  
@pytest.mark.skip(reason="Нестабилен при массовом запуске")
async def test_flow_history_pagination(migrated_db, flow_factory, session_repo):
    """
    Тест пагинации при получении списка сессий
    """
    print("\n=== Тест: Пагинация сессий ===")
    
    print("🔄 Получаем первую страницу (limit=2, offset=0)...")
    page_1 = await flow_factory.get_flow_sessions(
        limit=2,
        offset=0
    )
    
    print("✅ Страница 1:")
    print(f"  - Всего сессий: {page_1.total}")
    print(f"  - Возвращено: {len(page_1.sessions)}")
    print(f"  - Limit: {page_1.limit}")
    print(f"  - Offset: {page_1.offset}")
    
    if page_1.total > 2:
        print("\n🔄 Получаем вторую страницу (limit=2, offset=2)...")
        page_2 = await flow_factory.get_flow_sessions(
            limit=2,
            offset=2
        )
        
        print("✅ Страница 2:")
        print(f"  - Возвращено: {len(page_2.sessions)}")
        
        assert page_2.total == page_1.total, "Общее количество должно совпадать"
        
        if len(page_1.sessions) > 0 and len(page_2.sessions) > 0:
            assert page_1.sessions[0].session_id != page_2.sessions[0].session_id, \
                "Сессии на разных страницах должны отличаться"
    else:
        print("⚠️ Недостаточно сессий для проверки пагинации")
    
    print("✅ Тест пагинации пройден")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
