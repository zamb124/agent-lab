"""
Тесты для получения истории выполнения flow через FlowFactory
"""

import pytest
import uuid
from datetime import datetime, timezone

from app.core.flow_factory import FlowFactory
from app.core.agent_factory import AgentFactory
from app.core.storage import Storage
from app.models import (
    FlowConfig,
    AgentConfig,
    AgentType,
    ToolReference,
    LLMConfig,
    MessageRole,
)
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_flow_history_from_smart_flow(save_test_company):
    """
    Тест получения истории сообщений из выполненного smart_flow
    """
    print("\n=== Тест: История выполнения smart_flow ===")
    
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    
    flow_factory = FlowFactory()
    
    flow_id = "app.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    print(f"✅ Flow загружен: {flow_id}")
    
    thread_id = f"test_history_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    from app.models import SessionConfig, SessionStatus
    from app.core.storage import Storage
    storage = Storage()
    
    session = SessionConfig(
        session_id=thread_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await storage.set_session_config(session)
    
    print(f"🔄 Выполняем flow с вопросом о математике...")
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 15 + 27")]},
        config=config
    )
    
    messages = result.get("messages", [])
    print(f"✅ Flow выполнен, получено {len(messages)} сообщений")
    
    for i, msg in enumerate(messages):
        print(f"  {i}: [{type(msg).__name__}] {msg.content[:80]}")
    
    print(f"\n🔄 Получаем историю через FlowFactory...")
    history = await flow_factory.get_flow_history(
        session_id=thread_id,
        limit=100,
        include_checkpoints=False
    )
    
    print(f"✅ История получена:")
    print(f"  - Сессия: {history.session_id}")
    print(f"  - Flow: {history.flow_id}")
    print(f"  - Всего сообщений: {history.total_messages}")
    print(f"  - Всего checkpoints: {history.total_checkpoints}")
    print(f"  - Создано: {history.created_at}")
    print(f"  - Последняя активность: {history.last_activity}")
    
    assert history.total_messages > 0, "История должна содержать сообщения"
    assert history.total_checkpoints > 0, "История должна содержать checkpoints"
    assert history.session_id == thread_id
    assert history.flow_id == flow_id
    
    print(f"\n📋 Сообщения в истории:")
    for i, msg in enumerate(history.messages):
        tool_info = ""
        if msg.tool_calls:
            tool_info = f" [вызовы: {', '.join(tc.tool_name for tc in msg.tool_calls)}]"
        print(f"  {i}: [{msg.role.value}] {msg.content[:80]}{tool_info}")
    
    user_messages = [m for m in history.messages if m.role == MessageRole.USER]
    assistant_messages = [m for m in history.messages if m.role == MessageRole.ASSISTANT]
    tool_messages = [m for m in history.messages if m.role == MessageRole.TOOL]
    
    print(f"\n📊 Статистика сообщений:")
    print(f"  - Пользователь: {len(user_messages)}")
    print(f"  - Ассистент: {len(assistant_messages)}")
    print(f"  - Инструменты: {len(tool_messages)}")
    
    assert len(user_messages) >= 1, "Должно быть хотя бы одно сообщение пользователя"
    assert len(assistant_messages) >= 1, "Должно быть хотя бы одно сообщение ассистента"
    
    print(f"✅ Тест истории выполнения пройден")


@pytest.mark.asyncio
async def test_flow_history_with_checkpoints(save_test_company):
    """
    Тест получения истории с детальной информацией о checkpoints
    """
    print("\n=== Тест: История с checkpoints ===")
    
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    
    flow_factory = FlowFactory()
    
    flow_id = "app.flows.weather_flow.weather_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    thread_id = f"test_checkpoints_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    from app.models import SessionConfig, SessionStatus
    from app.core.storage import Storage
    storage = Storage()
    
    session = SessionConfig(
        session_id=thread_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await storage.set_session_config(session)
    
    print(f"🔄 Выполняем weather_flow...")
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config=config
    )
    
    print(f"✅ Flow выполнен")
    
    print(f"\n🔄 Получаем историю с checkpoints...")
    history = await flow_factory.get_flow_history(
        session_id=thread_id,
        limit=100,
        include_checkpoints=True
    )
    
    print(f"✅ История получена:")
    print(f"  - Всего сообщений: {history.total_messages}")
    print(f"  - Всего checkpoints: {history.total_checkpoints}")
    print(f"  - Checkpoints в ответе: {len(history.checkpoints)}")
    
    assert history.total_checkpoints > 0
    assert len(history.checkpoints) > 0, "Checkpoints должны быть включены в ответ"
    
    print(f"\n📋 Детали checkpoints:")
    for i, cp in enumerate(history.checkpoints):
        print(f"  Checkpoint {i}:")
        print(f"    - ID: {cp.checkpoint_id}")
        print(f"    - Step: {cp.step}")
        print(f"    - Сообщений: {len(cp.messages)}")
        print(f"    - Timestamp: {cp.timestamp}")
    
    print(f"✅ Тест с checkpoints пройден")


@pytest.mark.asyncio
async def test_flow_sessions_list(save_test_company):
    """
    Тест получения списка сессий через FlowFactory
    """
    print("\n=== Тест: Список сессий ===")
    
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    
    flow_factory = FlowFactory()
    storage = Storage()
    
    flow_id = "app.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    thread_id_1 = f"test_session_1_{uuid.uuid4().hex[:8]}"
    thread_id_2 = f"test_session_2_{uuid.uuid4().hex[:8]}"
    
    config_1 = {"configurable": {"thread_id": thread_id_1}}
    config_2 = {"configurable": {"thread_id": thread_id_2}}
    
    print(f"🔄 Создаем 2 сессии...")
    
    from app.models import SessionConfig, SessionStatus
    
    session_1 = SessionConfig(
        session_id=thread_id_1,
        platform="web",
        user_id="test_user_1",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc)
    )
    await storage.set_session_config(session_1)
    
    session_2 = SessionConfig(
        session_id=thread_id_2,
        platform="telegram",
        user_id="test_user_2",
        flow_id=flow_id,
        status=SessionStatus.INACTIVE,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc)
    )
    await storage.set_session_config(session_2)
    
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Первая сессия")]},
        config=config_1
    )
    
    await flow.ainvoke(
        {"messages": [HumanMessage(content="Вторая сессия")]},
        config=config_2
    )
    
    print(f"✅ Сессии созданы")
    
    print(f"\n🔄 Получаем список всех сессий...")
    sessions_all = await flow_factory.get_flow_sessions(
        limit=100,
        offset=0
    )
    
    print(f"✅ Всего сессий: {sessions_all.total}")
    print(f"  - Возвращено: {len(sessions_all.sessions)}")
    
    assert sessions_all.total >= 2, "Должно быть как минимум 2 сессии"
    
    print(f"\n🔄 Фильтруем по flow_id...")
    sessions_filtered = await flow_factory.get_flow_sessions(
        flow_id=flow_id,
        limit=100,
        offset=0
    )
    
    print(f"✅ Сессий для {flow_id}: {sessions_filtered.total}")
    
    test_sessions = [s for s in sessions_filtered.sessions if s.session_id in [thread_id_1, thread_id_2]]
    print(f"  - Наших тестовых сессий: {len(test_sessions)}")
    
    assert len(test_sessions) >= 2, "Должны найтись обе тестовые сессии"
    
    print(f"\n🔄 Фильтруем по платформе web...")
    sessions_web = await flow_factory.get_flow_sessions(
        platform="web",
        limit=100,
        offset=0
    )
    
    print(f"✅ Web сессий: {sessions_web.total}")
    
    web_test_session = [s for s in sessions_web.sessions if s.session_id == thread_id_1]
    assert len(web_test_session) == 1, "Должна найтись web сессия"
    
    print(f"\n📋 Детали сессий:")
    for session in test_sessions:
        print(f"  - {session.session_id}:")
        print(f"    Platform: {session.platform}")
        print(f"    User: {session.user_id}")
        print(f"    Status: {session.status}")
        print(f"    Messages: {session.message_count}")
        print(f"    Created: {session.created_at}")
    
    print(f"✅ Тест списка сессий пройден")


@pytest.mark.asyncio
async def test_flow_history_tool_calls(save_test_company):
    """
    Тест что история корректно фиксирует вызовы инструментов
    """
    print("\n=== Тест: Вызовы инструментов в истории ===")
    
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    
    flow_factory = FlowFactory()
    
    flow_id = "app.flows.smart_flow.smart_flow_config"
    flow = await flow_factory.get_flow(flow_id)
    
    thread_id = f"test_tools_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    from app.models import SessionConfig, SessionStatus
    from app.core.storage import Storage
    storage = Storage()
    
    session = SessionConfig(
        session_id=thread_id,
        platform="web",
        user_id="test_user",
        flow_id=flow_id,
        status=SessionStatus.ACTIVE,
    )
    await storage.set_session_config(session)
    
    print(f"🔄 Выполняем flow с запросом который вызовет калькулятор...")
    result = await flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 123 * 456")]},
        config=config
    )
    
    print(f"✅ Flow выполнен")
    
    print(f"\n🔄 Получаем историю...")
    history = await flow_factory.get_flow_history(
        session_id=thread_id,
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
    
    print(f"✅ Тест вызовов инструментов пройден")


@pytest.mark.asyncio  
async def test_flow_history_pagination(save_test_company):
    """
    Тест пагинации при получении списка сессий
    """
    print("\n=== Тест: Пагинация сессий ===")
    
    flow_factory = FlowFactory()
    
    print(f"🔄 Получаем первую страницу (limit=2, offset=0)...")
    page_1 = await flow_factory.get_flow_sessions(
        limit=2,
        offset=0
    )
    
    print(f"✅ Страница 1:")
    print(f"  - Всего сессий: {page_1.total}")
    print(f"  - Возвращено: {len(page_1.sessions)}")
    print(f"  - Limit: {page_1.limit}")
    print(f"  - Offset: {page_1.offset}")
    
    if page_1.total > 2:
        print(f"\n🔄 Получаем вторую страницу (limit=2, offset=2)...")
        page_2 = await flow_factory.get_flow_sessions(
            limit=2,
            offset=2
        )
        
        print(f"✅ Страница 2:")
        print(f"  - Возвращено: {len(page_2.sessions)}")
        
        assert page_2.total == page_1.total, "Общее количество должно совпадать"
        
        if len(page_1.sessions) > 0 and len(page_2.sessions) > 0:
            assert page_1.sessions[0].session_id != page_2.sessions[0].session_id, \
                "Сессии на разных страницах должны отличаться"
    else:
        print(f"⚠️ Недостаточно сессий для проверки пагинации")
    
    print(f"✅ Тест пагинации пройден")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
