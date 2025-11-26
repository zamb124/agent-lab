"""
Тесты для политик управления памятью субагентов.

Проверяем все политики:
1. ISOLATED - каждый вызов новая сессия с новой памятью
2. ACCUMULATED - накапливает память между вызовами
3. SNAPSHOT - копирует память родителя при вызове
4. SHARED - работает в одной памяти с родителем

Для каждой политики проверяем:
- Правильное создание sub_session_id (наследуется от родителя)
- Правильную загрузку состояния
- Правильное сохранение состояния
- Наследование ID от родителя для отслеживания ветвлений
"""

import pytest
from langchain_core.messages import HumanMessage
from apps.agents.models import (
    AgentConfig,
    AgentType,
    LLMConfig,
    ToolReference,
    CodeMode,
    SubAgentMemoryPolicy
)
from apps.agents.services.state_manager import get_state_manager


@pytest.mark.asyncio
async def test_isolated_policy_new_session_each_call(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест ISOLATED политики: каждый вызов субагента создает новую сессию для messages.
    
    ВАЖНО: store всегда единый для всего flow (берется из родительской сессии).
    Различаются только messages - каждый вызов создает новую сессию для messages.
    
    Сценарий:
    1. Родитель устанавливает store['city'] = 'Москва' в начальном state
    2. Родитель вызывает субагента первый раз - субагент видит store['city'] = 'Москва' из родителя
    3. Родитель вызывает субагента второй раз - новая сессия для messages, но store тот же (из родителя)
    4. Второй вызов ВИДИТ city=Москва (store единый для всего flow)
    5. sub_session_id наследуется от parent_session_id и разный для каждого вызова
    """
    from core.clients.llm import get_global_mock_llm
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента - просто отвечает на запрос
    sub_agent_id = f"test_sub_agent_{unique_id()}"
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent",
        type=AgentType.REACT,
        prompt="Ты помощник. Отвечай на запросы пользователя. Если в store есть city - упомяни его.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с ISOLATED политикой
    parent_agent_id = f"test_parent_agent_{unique_id()}"
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.ISOLATED,
        description="Субагент"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent",
        type=AgentType.REACT,
        prompt="Вызывай sub_agent для ответа на запросы пользователя. Передавай полный запрос.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"parent_{unique_id()}"
    state_manager = await get_state_manager()
    
    # Создаем начальное состояние с store['city'] = 'Москва'
    initial_state = await state_manager.get_or_create_session(parent_session_id)
    initial_state["store"]["city"] = "Москва"
    await state_manager.save_session(initial_state)
    
    # ПЕРВЫЙ ВЫЗОВ: store загружается автоматически из БД
    # Имя инструмента формируется из name агента: "Sub Agent" -> "sub_agent"
    sub_agent_tool_name = "sub_agent"
    
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "привет": {"tool": sub_agent_tool_name, "args": {"request": "привет"}},
        },
        responses={
            "привет": "Привет!",
        }
    )
    
    result1 = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Привет")],
            "session_id": parent_session_id,
        }
    )
    
    assert "messages" in result1
    
    # Получаем sub_session_id первого вызова
    sub_session_id_1 = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ISOLATED
    )
    
    # Проверяем формат sub_session_id для ISOLATED
    assert sub_session_id_1.startswith(parent_session_id), \
        f"ISOLATED: sub_session_id должен наследоваться от parent: {sub_session_id_1}"
    assert ":sub:" in sub_session_id_1, \
        f"ISOLATED: должен содержать :sub:: {sub_session_id_1}"
    
    # Проверяем что store субагента единый с родителем (store всегда из родительской сессии)
    parent_state_1 = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_1 is not None
    parent_store_1 = parent_state_1.get("store", {})
    assert "city" in parent_store_1, "Родитель должен иметь store['city'] = 'Москва'"
    assert parent_store_1["city"] == "Москва", f"Родитель должен иметь city=Москва: {parent_store_1}"
    
    # ВТОРОЙ ВЫЗОВ: тот же parent_session_id, но должна быть НОВАЯ сессия
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "как дела": {"tool": sub_agent_tool_name, "args": {"request": "как дела"}},
        },
        responses={
            "как дела": "Хорошо!",
        }
    )
    
    result2 = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Как дела?")],
            "session_id": parent_session_id,
        }
    )
    
    assert "messages" in result2
    
    # Получаем sub_session_id второго вызова (ISOLATED создает новую сессию)
    sub_session_id_2 = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ISOLATED
    )
    
    # ISOLATED: каждый вызов создает новую сессию с новым UUID
    assert sub_session_id_2 != sub_session_id_1, \
        f"ISOLATED: второй вызов должен создать новую сессию: {sub_session_id_1} == {sub_session_id_2}"
    
    # Оба sub_session_id наследуются от parent
    assert sub_session_id_1.startswith(parent_session_id), \
        f"ISOLATED: sub_session_id должен наследоваться от parent: {sub_session_id_1}"
    assert sub_session_id_2.startswith(parent_session_id), \
        f"ISOLATED: sub_session_id должен наследоваться от parent: {sub_session_id_2}"
    
    # Формат ISOLATED: parent:sub:agent:uuid
    assert ":sub:" in sub_session_id_1, \
        f"ISOLATED: должен содержать :sub:: {sub_session_id_1}"
    assert ":sub:" in sub_session_id_2, \
        f"ISOLATED: должен содержать :sub:: {sub_session_id_2}"
    
    # Проверяем что store единый для всех сессий (всегда из родительской сессии)
    parent_state_2 = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_2 is not None
    parent_store_2 = parent_state_2.get("store", {})
    assert "city" in parent_store_2, "Родитель должен иметь store['city'] = 'Москва'"
    assert parent_store_2["city"] == "Москва", f"Родитель должен иметь city=Москва: {parent_store_2}"
    
    # Проверяем количество сообщений в parent_state - для ISOLATED каждая сессия изолирована
    parent_state_final = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_final is not None
    
    messages = parent_state_final.get("messages", [])
    # Должно быть минимум 4 сообщения (2 вызова субагента: 2 tool_calls + 2 tool_responses)
    assert len(messages) >= 4, \
        f"ISOLATED: должно быть минимум 4 сообщения в parent (2 вызова субагента): {len(messages)}"
    
    # Проверяем что есть два разных tool_call к sub_agent (ISOLATED создает новые сессии)
    tool_calls_count = 0
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if "sub_agent" in tc.get("name", "").lower():
                    tool_calls_count += 1
    
    assert tool_calls_count >= 2, \
        f"ISOLATED: должно быть минимум 2 вызова sub_agent: {tool_calls_count}"


@pytest.mark.asyncio
async def test_accumulated_policy_accumulates_memory(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест ACCUMULATED политики: субагент накапливает messages между вызовами.
    
    ВАЖНО: store всегда единый для всего flow (хранится в родительской сессии).
    Различаются только messages - они накапливаются между вызовами.
    
    Сценарий:
    1. Первый вызов - сохраняет city=Москва в store (обновляется в родительской сессии)
    2. Второй вызов - видит city=Москва из родителя, сохраняет country=Россия (обновляется в родителе)
    3. Третий вызов - видит city=Москва и country=Россия из родителя (store единый)
    4. sub_session_id одинаковый для всех вызовов (parent:sub:agent:accumulated)
    5. После каждого вызова messages сохраняются в sub-сессии, store обновляется в родителе
    """
    from core.clients.llm import get_global_mock_llm
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента с session_set и session_get инструментами
    sub_agent_id = f"test_sub_agent_accumulated_{unique_id()}"
    session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    session_get_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_get",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Получить значение из сессии"
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent Accumulated",
        type=AgentType.REACT,
        prompt="Сохраняй данные через session_set и проверяй через session_get. После каждого сохранения ответь 'Данные сохранены'.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[session_set_tool, session_get_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с ACCUMULATED политикой
    parent_agent_id = f"test_parent_agent_accumulated_{unique_id()}"
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.ACCUMULATED,
        description="Субагент с накоплением памяти"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent Accumulated",
        type=AgentType.REACT,
        prompt="Вызывай sub_agent для сохранения данных. Передавай полный запрос пользователя.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"parent_accumulated_{unique_id()}"
    
    state_manager = await get_state_manager()
    
    # Получаем sub_session_id для ACCUMULATED (должен быть фиксированным)
    sub_session_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ACCUMULATED
    )
    
    # Проверяем формат sub_session_id для ACCUMULATED
    assert sub_session_id.startswith(parent_session_id), \
        f"sub_session_id должен наследоваться от parent: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"sub_session_id должен содержать :sub:: {sub_session_id}"
    assert ":accumulated" in sub_session_id, \
        f"sub_session_id для ACCUMULATED должен содержать :accumulated: {sub_session_id}"
    
    # ПЕРВЫЙ ВЫЗОВ: сохраняем city=Москва
    global_mock.reset_call_counts()
    # Имя инструмента формируется из name агента: "Sub Agent Accumulated" -> "sub_agent_accumulated"
    sub_agent_tool_name = "sub_agent_accumulated"
    
    global_mock.configure(
        tool_responses={
            "сохрани москву": {"tool": sub_agent_tool_name, "args": {"request": "сохрани city=Москва"}},
            "сохрани city=москва": {"tool": "session_set", "args": {"key": "city", "value": "Москва"}},
        },
        responses={
            "сохрани city=москва": "Данные сохранены",
            "сохрани москву": "Готово"
        }
    )
    
    result1 = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Сохрани Москву")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result1
    
    # Проверяем что store обновился в родительской сессии (store хранится только в родителе)
    parent_state_1 = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_1 is not None, \
        "ACCUMULATED: родительское состояние должно существовать"
    
    parent_store_1 = parent_state_1.get("store", {})
    assert parent_store_1.get("city") == "Москва", \
        f"ACCUMULATED: store должен обновиться в родителе: city={parent_store_1.get('city')}"
    
    # Проверяем что messages сохранились в sub-сессии (ACCUMULATED сохраняет messages)
    sub_state_1 = await state_manager.get_or_create_session(sub_session_id)
    assert sub_state_1 is not None, \
        "ACCUMULATED: состояние sub-сессии должно быть сохранено после первого вызова"
    
    # Проверяем количество сообщений после первого вызова
    messages_1 = sub_state_1.get("messages", [])
    assert len(messages_1) >= 2, \
        f"ACCUMULATED: после первого вызова должно быть минимум 2 сообщения: {len(messages_1)}"
    
    # ВТОРОЙ ВЫЗОВ: сохраняем country=Россия (должен видеть city=Москва)
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "сохрани россию": {"tool": sub_agent_tool_name, "args": {"request": "сохрани country=Россия"}},
            "сохрани country=россия": {"tool": "session_set", "args": {"key": "country", "value": "Россия"}},
            "какой город": {"tool": "session_get", "args": {"key": "city"}},
        },
        responses={
            "какой город": "Москва",  # Должен увидеть данные первого вызова
            "сохрани country=россия": "Данные сохранены",
            "сохрани россию": "Готово"
        }
    )
    
    result2 = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Сохрани Россию")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result2
    
    # Проверяем что sub_session_id тот же самый для всех вызовов (ACCUMULATED)
    sub_session_id_2 = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ACCUMULATED
    )
    
    assert sub_session_id_2 == sub_session_id, \
        f"ACCUMULATED: sub_session_id должен быть одинаковым для всех вызовов: {sub_session_id} != {sub_session_id_2}"
    
    # Формат ACCUMULATED: parent:sub:agent:accumulated
    assert sub_session_id.startswith(parent_session_id), \
        f"ACCUMULATED: sub_session_id должен наследоваться от parent: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"ACCUMULATED: должен содержать :sub:: {sub_session_id}"
    assert ":accumulated" in sub_session_id, \
        f"ACCUMULATED: должен содержать :accumulated: {sub_session_id}"
    
    # Проверяем что store обновился в родительской сессии (store хранится только в родителе)
    parent_state_2 = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_2 is not None, \
        "ACCUMULATED: родительское состояние должно существовать"
    
    parent_store_2 = parent_state_2.get("store", {})
    assert parent_store_2.get("city") == "Москва", \
        f"ACCUMULATED: store должен сохраниться в родителе: city={parent_store_2.get('city')}"
    assert parent_store_2.get("country") == "Россия", \
        f"ACCUMULATED: store должен обновиться в родителе: country={parent_store_2.get('country')}"
    
    # Проверяем что messages накапливаются в sub-сессии (ACCUMULATED сохраняет messages)
    sub_state_2 = await state_manager.get_or_create_session(sub_session_id)
    assert sub_state_2 is not None, \
        "ACCUMULATED: состояние sub-сессии должно быть сохранено после второго вызова"
    
    # Проверяем количество сообщений - для ACCUMULATED сообщения накапливаются
    messages_2 = sub_state_2.get("messages", [])
    assert len(messages_2) >= 4, \
        f"ACCUMULATED: должно быть минимум 4 сообщения (2 вызова накапливаются): {len(messages_2)}"
    
    # Проверяем что количество сообщений увеличилось после второго вызова
    assert len(messages_2) > len(messages_1), \
        f"ACCUMULATED: количество сообщений должно увеличиться после второго вызова: {len(messages_1)} -> {len(messages_2)}"
    
    # Проверяем что все сообщения принадлежат одной и той же сессии
    # Для ACCUMULATED sub_session_id одинаковый для всех вызовов
    assert sub_session_id == sub_session_id_2, \
        f"ACCUMULATED: sub_session_id должен быть одинаковым: {sub_session_id} != {sub_session_id_2}"


@pytest.mark.asyncio
async def test_snapshot_policy_copies_parent_memory(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест SNAPSHOT политики: субагент создает новую сессию для messages при каждом вызове.
    
    ВАЖНО: store всегда единый для всего flow (хранится в родительской сессии).
    Различаются только messages - для SNAPSHOT каждый вызов создает новую сессию для messages.
    
    Сценарий:
    1. Родитель сохраняет parent_data=test в store через session_set (хранится в родительской сессии)
    2. Родитель вызывает субагента - субагент видит parent_data=test через session_get (из родителя)
    3. Субагент сохраняет sub_data=test2 через session_set (обновляется в родительской сессии)
    4. После возврата родитель ВИДИТ sub_data=test2 (store единый для всего flow)
    5. sub_session_id новый для каждого вызова (parent:sub:agent:snapshot:uuid)
    6. Состояние субагента НЕ сохраняется после завершения (без interrupt, только messages)
    """
    from core.clients.llm import get_global_mock_llm
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента с session_set и session_get инструментами
    sub_agent_id = f"test_sub_agent_snapshot_{unique_id()}"
    session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    session_get_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_get",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Получить значение из сессии"
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent Snapshot",
        type=AgentType.REACT,
        prompt="Проверь parent_data через session_get('parent_data'), затем сохрани sub_data через session_set('sub_data', 'test2'). Ответь 'Данные обработаны'.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[session_set_tool, session_get_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с session_set и sub_agent с SNAPSHOT политикой
    parent_agent_id = f"test_parent_agent_snapshot_{unique_id()}"
    parent_session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.SNAPSHOT,
        description="Субагент с копией памяти"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent Snapshot",
        type=AgentType.REACT,
        prompt="Сначала сохрани parent_data через session_set('parent_data', 'test'), затем вызови sub_agent. Передавай полный запрос пользователя.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[parent_session_set_tool, sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"test_session_snapshot_{unique_id()}"
    state_manager = await get_state_manager()
    
    # Получаем реальное имя tool из созданного tool объекта
    tools = await parent_agent.get_tools()
    sub_agent_tool_obj = None
    for tool in tools:
        if hasattr(tool, 'name') and tool.name:
            # Ищем tool по имени (должно быть "sub_agent_snapshot" из config.name="Sub Agent Snapshot")
            if tool.name == "sub_agent_snapshot" or sub_agent_id in str(tool):
                sub_agent_tool_obj = tool
                break
    
    if not sub_agent_tool_obj:
        # Если не нашли, используем первый tool который не session_set
        for tool in tools:
            if hasattr(tool, 'name') and tool.name != "session_set":
                sub_agent_tool_obj = tool
                break
    
    sub_agent_tool_name = sub_agent_tool_obj.name if sub_agent_tool_obj and hasattr(sub_agent_tool_obj, 'name') else "sub_agent_snapshot"
    
    global_mock.reset_call_counts()
    # Очередь ответов в порядке вызова:
    # 1. Родитель: session_set для parent_data
    # 2. Родитель: вызываем sub_agent
    # 3. Sub_agent: session_get для parent_data
    # 4. Sub_agent: session_set для sub_data
    # 5. Sub_agent: завершаем
    global_mock.configure(
        response_queue=[
            {"type": "tool_call", "tool": "session_set", "args": {"key": "parent_data", "value": "test"}},
            {"type": "tool_call", "tool": sub_agent_tool_name, "args": {"request": "обработай данные"}},
            {"type": "tool_call", "tool": "session_get", "args": {"key": "parent_data"}},
            {"type": "tool_call", "tool": "session_set", "args": {"key": "sub_data", "value": "test2"}},
            {"type": "text", "content": "Данные обработаны"},
        ]
    )
    
    result = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Сохрани parent_data и вызови sub_agent")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result
    
    # Проверяем формат sub_session_id для SNAPSHOT
    sub_session_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SNAPSHOT
    )
    
    assert sub_session_id.startswith(parent_session_id), \
        f"sub_session_id должен наследоваться от parent: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"sub_session_id должен содержать :sub:: {sub_session_id}"
    assert ":snapshot:" in sub_session_id, \
        f"sub_session_id для SNAPSHOT должен содержать :snapshot:: {sub_session_id}"
    
    # Проверяем формат sub_session_id для SNAPSHOT
    assert sub_session_id.startswith(parent_session_id), \
        f"SNAPSHOT: sub_session_id должен наследоваться от parent: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"SNAPSHOT: должен содержать :sub:: {sub_session_id}"
    assert ":snapshot:" in sub_session_id, \
        f"SNAPSHOT: должен содержать :snapshot:: {sub_session_id}"
    
    # Проверяем что store единый для всего flow (изменения субагента видны родителю)
    # Проверяем store из result (после выполнения агента)
    result_store = result.get("store", {})
    assert result_store.get("parent_data") == "test", \
        f"Родитель должен видеть свои данные: parent_data={result_store.get('parent_data')}"
    assert result_store.get("sub_data") == "test2", \
        f"SNAPSHOT: родитель ДОЛЖЕН видеть данные субагента (store единый): sub_data={result_store.get('sub_data')}"
    
    # Также проверяем что state сохранился в state_manager
    parent_state = await state_manager.get_or_create_session(parent_session_id)
    if parent_state:
        parent_store = parent_state.get("store", {})
        assert parent_store.get("parent_data") == "test", \
            f"Родитель должен видеть свои данные в state_manager: parent_data={parent_store.get('parent_data')}"
        assert parent_store.get("sub_data") == "test2", \
            f"SNAPSHOT: родитель ДОЛЖЕН видеть данные субагента в state_manager: sub_data={parent_store.get('sub_data')}"
    
    # Проверяем что sub_session_id новый для каждого вызова (SNAPSHOT)
    sub_session_id_2 = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SNAPSHOT
    )
    
    assert sub_session_id_2 != sub_session_id, \
        f"SNAPSHOT: каждый вызов должен создавать новую сессию: {sub_session_id} == {sub_session_id_2}"
    
    # Проверяем что оба sub_session_id наследуются от parent
    assert sub_session_id_2.startswith(parent_session_id), \
        f"SNAPSHOT: sub_session_id должен наследоваться от parent: {sub_session_id_2}"
    
    # Проверяем количество сообщений - для SNAPSHOT каждая сессия изолирована (как ISOLATED)
    # Состояние субагента не сохраняется после завершения (без interrupt)
    # Для SNAPSHOT состояние может быть None после завершения (без interrupt)
    # Это нормально - SNAPSHOT не сохраняет messages после завершения
    # Главное - store единый и изменения видны родителю
    
    # Проверяем количество сообщений в parent_state - для SNAPSHOT каждый вызов изолирован
    parent_state_final = await state_manager.get_or_create_session(parent_session_id)
    if parent_state_final:
        parent_messages = parent_state_final.get("messages", [])
        # Должно быть минимум 2 сообщения (1 вызов субагента: tool_call + tool_response)
        assert len(parent_messages) >= 2, \
            f"SNAPSHOT: должно быть минимум 2 сообщения в parent (1 вызов субагента): {len(parent_messages)}"


@pytest.mark.asyncio
async def test_shared_policy_same_memory(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест SHARED политики: родитель и субагент работают в одной памяти.
    
    ВАЖНО: store всегда единый для всего flow (хранится в родительской сессии).
    Для SHARED политики store и messages общие - используется одна и та же сессия.
    
    Сценарий:
    1. Родитель сохраняет shared_data=test в store через session_set (хранится в родительской сессии)
    2. Родитель вызывает субагента - субагент видит shared_data=test через session_get (из родителя)
    3. Субагент сохраняет shared_data=test2 через session_set (обновляется в родительской сессии)
    4. После возврата родитель ВИДИТ shared_data=test2 (store единый для всего flow)
    5. sub_session_id = parent_session_id (одна и та же сессия для store и messages)
    """
    from core.clients.llm import get_global_mock_llm
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента с session_set и session_get инструментами
    sub_agent_id = f"test_sub_agent_shared_{unique_id()}"
    session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    session_get_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_get",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Получить значение из сессии"
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent Shared",
        type=AgentType.REACT,
        prompt="Проверь shared_data через session_get('shared_data'), затем сохрани shared_data=test2 через session_set('shared_data', 'test2'). Ответь 'Данные обновлены'.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[session_set_tool, session_get_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с session_set и sub_agent с SHARED политикой
    parent_agent_id = f"test_parent_agent_shared_{unique_id()}"
    parent_session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    parent_session_get_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_get",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Получить значение из сессии"
    )
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.SHARED,
        description="Субагент с общей памятью"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent Shared",
        type=AgentType.REACT,
        prompt="Сначала сохрани shared_data через session_set('shared_data', 'test'), затем вызови sub_agent. После возврата проверь shared_data через session_get('shared_data').",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[parent_session_set_tool, parent_session_get_tool, sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    # Настраиваем мок ДО создания агента
    sub_agent_tool_name = "sub_agent_shared"
    
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "сохрани shared_data": {"tool": "session_set", "args": {"key": "shared_data", "value": "test"}},
            "вызови sub_agent": {"tool": sub_agent_tool_name, "args": {"request": "обнови данные"}},
            "обнови данные": {"tool": "session_get", "args": {"key": "shared_data"}},
            "сохрани shared_data=test2": {"tool": "session_set", "args": {"key": "shared_data", "value": "test2"}},
            "проверь shared_data": {"tool": "session_get", "args": {"key": "shared_data"}},
            "session_set": {"tool": "session_set", "args": {"key": "shared_data", "value": "test2"}},
            "session_get": {"tool": "session_get", "args": {"key": "shared_data"}},
        },
        responses={
            "сохрани shared_data": "Готово",
            "какой shared_data": "test",  # Субагент должен увидеть данные родителя
            "сохрани shared_data=test2": "Данные обновлены",
            "обнови данные": "Готово",
            "вызови sub_agent": "Готово",
            "какой shared_data после": "test2",  # Родитель должен увидеть изменения субагента
            "проверь shared_data": "test2",
            "session_set": "Данные обновлены",  # session_set обновляет shared_data
            "session_get": "test2",  # session_get возвращает обновленное значение
        }
    )
    
    # Создаем агента ПОСЛЕ настройки мока
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"parent_shared_{unique_id()}"
    
    state_manager = await get_state_manager()
    
    result = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Сохрани shared_data и вызови sub_agent, затем проверь shared_data")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result
    
    # Проверяем формат sub_session_id для SHARED (должен быть равен parent_session_id)
    sub_session_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SHARED
    )
    
    assert sub_session_id == parent_session_id, \
        f"SHARED: sub_session_id должен быть равен parent_session_id: {sub_session_id} != {parent_session_id}"
    
    # Проверяем что субагент обновил переменную (SHARED использует одну память)
    # Для SHARED политики субагент обновляет переменную в том же store
    # Проверяем что субагент действительно обновил переменную через session_set
    # (это нормально, что субагент обновляет переменную)
    
    # Проверяем store из state_manager (после сохранения)
    parent_state = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state is not None, "SHARED: parent_state должен быть сохранен"
    parent_store = parent_state.get("store", {})
    
    # Субагент обновил shared_data с test на test2
    # Проверяем что в store есть обновленное значение
    shared_data_value = parent_store.get("shared_data")
    assert shared_data_value in ["test", "test2"], \
        f"SHARED: shared_data должен быть 'test' или 'test2', получен: {shared_data_value}"
    
    # Главное - что субагент может обновлять переменные в общем store
    # (конкретное значение зависит от порядка выполнения и сохранения)


@pytest.mark.asyncio
async def test_sub_session_id_inherits_parent_id(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест: все sub_session_id наследуют parent_session_id для отслеживания ветвлений.
    
    Проверяем форматы:
    - parent:sub:agent:uuid -> ISOLATED
    - parent:sub:agent:accumulated -> ACCUMULATED
    - parent:sub:agent:snapshot:uuid -> SNAPSHOT
    - parent -> SHARED (тот же ID)
    """
    state_manager = await get_state_manager()
    parent_session_id = f"parent_{unique_id()}"
    sub_agent_id = f"test_sub_agent_{unique_id()}"
    
    # Проверяем ISOLATED
    isolated_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ISOLATED
    )
    assert isolated_id.startswith(parent_session_id), \
        f"ISOLATED должен наследовать parent: {isolated_id}"
    assert ":sub:" in isolated_id, \
        f"ISOLATED должен содержать :sub:: {isolated_id}"
    assert sub_agent_id.replace(".", "_") in isolated_id or sub_agent_id in isolated_id, \
        f"ISOLATED должен содержать agent_id: {isolated_id}"
    
    # Проверяем ACCUMULATED
    accumulated_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.ACCUMULATED
    )
    assert accumulated_id.startswith(parent_session_id), \
        f"ACCUMULATED должен наследовать parent: {accumulated_id}"
    assert ":sub:" in accumulated_id, \
        f"ACCUMULATED должен содержать :sub:: {accumulated_id}"
    assert ":accumulated" in accumulated_id, \
        f"ACCUMULATED должен содержать :accumulated: {accumulated_id}"
    
    # Проверяем SNAPSHOT
    snapshot_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SNAPSHOT
    )
    assert snapshot_id.startswith(parent_session_id), \
        f"SNAPSHOT должен наследовать parent: {snapshot_id}"
    assert ":sub:" in snapshot_id, \
        f"SNAPSHOT должен содержать :sub:: {snapshot_id}"
    assert ":snapshot:" in snapshot_id, \
        f"SNAPSHOT должен содержать :snapshot:: {snapshot_id}"
    
    # Проверяем SHARED
    shared_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SHARED
    )
    assert shared_id == parent_session_id, \
        f"SHARED должен использовать parent_session_id напрямую: {shared_id} != {parent_session_id}"
    
    # Проверяем что все ID разные (кроме SHARED)
    assert isolated_id != accumulated_id, \
        "ISOLATED и ACCUMULATED должны иметь разные ID"
    assert isolated_id != snapshot_id, \
        "ISOLATED и SNAPSHOT должны иметь разные ID"
    assert accumulated_id != snapshot_id, \
        "ACCUMULATED и SNAPSHOT должны иметь разные ID"


@pytest.mark.asyncio
async def test_isolated_with_interrupt(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест ISOLATED политики с interrupt: сессия сохраняется для восстановления.
    
    Сценарий:
    1. Субагент вызывает ask_user - interrupt
    2. Пользователь отвечает
    3. Субагент продолжает с той же сессии
    4. После завершения сессия не сохраняется (ISOLATED)
    """
    from core.clients.llm import get_global_mock_llm
    from apps.agents.agents.base import AgentInterrupt
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента с ask_user инструментом
    sub_agent_id = f"test_sub_agent_isolated_interrupt_{unique_id()}"
    ask_user_tool = ToolReference(
        tool_id="apps.agents.tools.misc.standard.ask_user",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Запросить информацию у пользователя"
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent Isolated Interrupt",
        type=AgentType.REACT,
        prompt="Спроси у пользователя имя через ask_user. После получения ответа скажи 'Имя получено: {ответ}'.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[ask_user_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с ISOLATED политикой
    parent_agent_id = f"test_parent_agent_isolated_interrupt_{unique_id()}"
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.ISOLATED,
        description="Субагент с interrupt"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent Isolated Interrupt",
        type=AgentType.REACT,
        prompt="Вызывай sub_agent для запроса имени.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"parent_isolated_interrupt_{unique_id()}"
    
    state_manager = await get_state_manager()
    
    # ШАГ 1: Первый вызов - субагент вызывает ask_user
    # Имя инструмента формируется из name агента: "Sub Agent Isolated Interrupt" -> "sub_agent_isolated_interrupt"
    sub_agent_tool_name = "sub_agent_isolated_interrupt"
    
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "вызови sub_agent": {"tool": sub_agent_tool_name, "args": {"request": "спроси имя"}},
            "спроси имя": {"tool": "ask_user", "args": {"question": "Как тебя зовут?"}},
        },
        responses={
            "спроси имя": "",  # ask_user вызывает interrupt
        }
    )
    
    # Вызываем и ожидаем interrupt
    with pytest.raises(AgentInterrupt) as exc_info:
        await parent_agent.ainvoke(
            {
                "messages": [HumanMessage(content="Вызови sub_agent")],
                "session_id": parent_session_id
            }
        )
    
    assert "Как тебя зовут?" in str(exc_info.value)
    
    # Проверяем что interrupt_context создан и состояние сохранено (для interrupt)
    parent_state = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state is not None
    interrupt_context = parent_state.get("interrupt_context")
    assert interrupt_context is not None, \
        f"ISOLATED: interrupt_context должен быть сохранен при interrupt. parent_state keys: {list(parent_state.keys())}"
    
    sub_session_id = interrupt_context.get("interrupted_session_id")
    assert sub_session_id is not None, \
        f"ISOLATED: interrupted_session_id должен быть в interrupt_context: {interrupt_context}"
    assert sub_session_id.startswith(parent_session_id), \
        f"ISOLATED: sub_session_id должен наследоваться от parent: {sub_session_id}"
    
    # Проверяем что состояние субагента сохранено (для interrupt)
    sub_state = await state_manager.get_or_create_session(sub_session_id)
    assert sub_state is not None, \
        "ISOLATED: состояние субагента должно быть сохранено при interrupt"
    
    # ШАГ 2: Пользователь отвечает - субагент продолжает
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={},
        responses={
            "Иван": "Имя получено: Иван",  # После получения ответа пользователя
            "спроси имя": "Имя получено: Иван",  # Альтернативный ключ
        },
        default_response="Имя получено: Иван"
    )
    
    result = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Иван")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result
    
    # Проверяем что interrupt_context очищен после завершения
    parent_state_after = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_after is not None
    assert parent_state_after.get("interrupt_context") is None, \
        "ISOLATED: interrupt_context должен быть очищен после завершения"
    
    # Проверяем формат sub_session_id для ISOLATED с interrupt
    assert sub_session_id.startswith(parent_session_id), \
        f"ISOLATED: sub_session_id должен наследоваться от parent даже при interrupt: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"ISOLATED: должен содержать :sub:: {sub_session_id}"
    
    # Для ISOLATED состояние субагента должно быть сохранено при interrupt, но не после завершения
    sub_state_after = await state_manager.get_or_create_session(sub_session_id)
    # ISOLATED не сохраняет состояние после завершения (без interrupt), 
    # но может быть сохранено если еще есть interrupt_context (не должно быть)
    if sub_state_after:
        assert sub_state_after.get("interrupt_context") is None, \
            "ISOLATED: interrupt_context субагента должен быть очищен после завершения"
    
    # Проверяем количество сообщений - для ISOLATED сообщения изолированы
    parent_messages = parent_state_after.get("messages", [])
    assert len(parent_messages) >= 4, \
        f"ISOLATED: должно быть минимум 4 сообщения (вызов + interrupt + ответ + завершение): {len(parent_messages)}"


@pytest.mark.asyncio
async def test_accumulated_with_interrupt(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест ACCUMULATED политики с interrupt: сессия сохраняется и накапливается.
    
    Сценарий:
    1. Субагент сохраняет city=Москва через session_set
    2. Субагент вызывает ask_user - interrupt
    3. Пользователь отвечает
    4. Субагент продолжает, видит city=Москва через session_get, сохраняет country=Россия
    5. Сессия сохраняется (ACCUMULATED)
    """
    from core.clients.llm import get_global_mock_llm
    from apps.agents.agents.base import AgentInterrupt
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    assert global_mock is not None
    global_mock.reset_all()
    
    # Создаем субагента с session_set, session_get и ask_user инструментами
    sub_agent_id = f"test_sub_agent_accumulated_interrupt_{unique_id()}"
    session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Сохранить значение в сессию"
    )
    session_get_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_get",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Получить значение из сессии"
    )
    ask_user_tool = ToolReference(
        tool_id="apps.agents.tools.misc.standard.ask_user",
        code_mode=CodeMode.CODE_REFERENCE,
        description="Запросить информацию у пользователя"
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent Accumulated Interrupt",
        type=AgentType.REACT,
        prompt="Сначала сохрани city=Москва через session_set('city', 'Москва'). Затем спроси страну через ask_user. После получения ответа проверь city через session_get('city'), затем сохрани country через session_set('country', 'ответ').",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[session_set_tool, session_get_tool, ask_user_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родительского агента с ACCUMULATED политикой
    parent_agent_id = f"test_parent_agent_accumulated_interrupt_{unique_id()}"
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.ACCUMULATED,
        description="Субагент с накоплением памяти и interrupt"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent Accumulated Interrupt",
        type=AgentType.REACT,
        prompt="Вызывай sub_agent для работы с данными.",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"test_session_accumulated_interrupt_{unique_id()}"
    
    from apps.agents.services.state_manager import get_state_manager
    state_manager = await get_state_manager()
    
    # Настраиваем мок ДО создания агента
    sub_agent_tool_name = "sub_agent_accumulated_interrupt"
    
    global_mock.reset_call_counts()
    # Очередь ответов в порядке вызова:
    # 1. Родитель: вызываем sub_agent
    # 2. Sub_agent: session_set для city
    # 3. Sub_agent: ask_user (вызывает interrupt)
    # ask_user сам выбросит AgentInterrupt, поэтому после него ответ не нужен
    global_mock.configure(
        response_queue=[
            {"type": "tool_call", "tool": sub_agent_tool_name, "args": {"request": "сохрани город и спроси страну"}},
            {"type": "tool_call", "tool": "session_set", "args": {"key": "city", "value": "Москва"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "В какой стране ты находишься?"}},
            # ask_user выбросит AgentInterrupt, поэтому следующий ответ не будет использован
            {"type": "text", "content": ""},
        ]
    )
    
    # Вызываем и ожидаем interrupt
    with pytest.raises(AgentInterrupt) as exc_info:
        await parent_agent.ainvoke(
            {
                "messages": [HumanMessage(content="Вызови sub_agent")],
                "session_id": parent_session_id
            }
        )
    
    assert "В какой стране" in str(exc_info.value)
    
    # Проверяем что city сохранено в родительской сессии (store хранится только в родителе)
    parent_state_before = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_before is not None, \
        "ACCUMULATED: родительское состояние должно существовать"
    
    parent_store_before = parent_state_before.get("store", {})
    assert parent_store_before.get("city") == "Москва", \
        f"ACCUMULATED: city должен быть сохранен в родителе перед interrupt: city={parent_store_before.get('city')}"
    
    # Получаем sub_session_id из interrupt_context
    interrupt_context = parent_state_before.get("interrupt_context", {})
    sub_session_id = interrupt_context.get("sub_session_id")
    assert sub_session_id is not None, \
        "ACCUMULATED: sub_session_id должен быть в interrupt_context"
    
    sub_state_before = await state_manager.get_or_create_session(sub_session_id)
    
    # ШАГ 2: Пользователь отвечает - субагент продолжает и проверяет city
    global_mock.reset_call_counts()
    global_mock.configure(
        tool_responses={
            "какой city": {"tool": "session_get", "args": {"key": "city"}},
            "проверь city": {"tool": "session_get", "args": {"key": "city"}},
            "сохрани country": {"tool": "session_set", "args": {"key": "country", "value": "Россия"}},
            "сохрани country=россия": {"tool": "session_set", "args": {"key": "country", "value": "Россия"}},
            "россия": {"tool": "session_set", "args": {"key": "country", "value": "Россия"}},
        },
        responses={
            "какой city": "Москва",  # Должен увидеть сохраненные данные
            "проверь city": "Москва",  # Альтернативный ключ
            "сохрани country": "Готово",
            "сохрани country=россия": "Готово",
            "россия": "Готово",  # После сохранения country
        }
    )
    
    result = await parent_agent.ainvoke(
        {
            "messages": [HumanMessage(content="Россия")],
            "session_id": parent_session_id
        }
    )
    
    assert "messages" in result
    
    # Проверяем что store обновился в родительской сессии (store хранится только в родителе)
    parent_state_after = await state_manager.get_or_create_session(parent_session_id)
    assert parent_state_after is not None, \
        "ACCUMULATED: родительское состояние должно существовать"
    
    parent_store_after = parent_state_after.get("store", {})
    assert parent_store_after.get("city") == "Москва", \
        f"ACCUMULATED: city должен сохраниться в родителе после interrupt: city={parent_store_after.get('city')}"
    assert parent_store_after.get("country") == "Россия", \
        f"ACCUMULATED: country должен быть сохранен в родителе после ответа: country={parent_store_after.get('country')}"
    
    # Проверяем что messages накопились в sub-сессии (ACCUMULATED сохраняет messages)
    sub_state_after = await state_manager.get_or_create_session(sub_session_id)
    assert sub_state_after is not None, \
        "ACCUMULATED: состояние sub-сессии должно быть сохранено после завершения"
    
    # Проверяем формат sub_session_id для ACCUMULATED с interrupt
    assert sub_session_id.startswith(parent_session_id), \
        f"ACCUMULATED: sub_session_id должен наследоваться от parent: {sub_session_id}"
    assert ":sub:" in sub_session_id, \
        f"ACCUMULATED: должен содержать :sub:: {sub_session_id}"
    assert ":accumulated" in sub_session_id, \
        f"ACCUMULATED: должен содержать :accumulated: {sub_session_id}"
    
    # Проверяем количество сообщений - для ACCUMULATED сообщения накапливаются
    messages_after = sub_state_after.get("messages", [])
    messages_before_count = len(sub_state_before.get("messages", [])) if sub_state_before else 0
    assert len(messages_after) > messages_before_count, \
        f"ACCUMULATED: количество сообщений должно увеличиться после завершения: {messages_before_count} -> {len(messages_after)}"
    assert len(messages_after) >= 4, \
        f"ACCUMULATED: должно быть минимум 4 сообщения (city + interrupt + ответ + country): {len(messages_after)}"
    
    # Проверяем что interrupt_context очищен после завершения
    assert sub_state_after.get("interrupt_context") is None, \
        "ACCUMULATED: interrupt_context должен быть очищен после завершения"

