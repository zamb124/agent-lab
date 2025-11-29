"""
Простой тест для проверки что родитель и субагент используют один и тот же объект StoreProxy.
"""
import pytest
from langchain_core.messages import HumanMessage

from apps.agents.services.state_manager import get_state_manager, StoreProxy
from apps.agents.models.core_models import AgentConfig, AgentType, LLMConfig, ToolReference, CodeMode, SubAgentMemoryPolicy


@pytest.mark.asyncio
async def test_store_proxy_same_object(migrated_db, agent_factory, agent_repo, mock_llm, unique_id):
    """Проверяем что родитель и субагент используют один и тот же объект StoreProxy"""
    from core.clients.llm import get_global_mock_llm
    
    global_mock = get_global_mock_llm("mock-gpt-4")
    global_mock.reset_all()
    
    # Создаем субагента с session_set
    sub_agent_id = f"test_sub_{unique_id()}"
    session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE
    )
    
    sub_agent_config = AgentConfig(
        agent_id=sub_agent_id,
        name="Sub Agent",
        type=AgentType.REACT,
        prompt="Сохрани sub_data через session_set('sub_data', 'test2'). Ответь 'Готово'.",
        llm_config=LLMConfig(model="mock-gpt-4"),
        tools=[session_set_tool]
    )
    await agent_repo.set(sub_agent_config)
    
    # Создаем родителя с sub_agent
    parent_agent_id = f"test_parent_{unique_id()}"
    parent_session_set_tool = ToolReference(
        tool_id="apps.agents.tools.session.session_tools.session_set",
        code_mode=CodeMode.CODE_REFERENCE
    )
    sub_agent_tool = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        memory_policy=SubAgentMemoryPolicy.SNAPSHOT,
        description="Субагент"
    )
    
    parent_agent_config = AgentConfig(
        agent_id=parent_agent_id,
        name="Parent Agent",
        type=AgentType.REACT,
        prompt="Сначала сохрани parent_data через session_set('parent_data', 'test'), затем вызови sub_agent. Передавай полный запрос пользователя.",
        llm_config=LLMConfig(model="mock-gpt-4"),
        tools=[parent_session_set_tool, sub_agent_tool]
    )
    await agent_repo.set(parent_agent_config)
    
    parent_agent = await agent_factory.get_agent(parent_agent_id)
    parent_session_id = f"test_session_{unique_id()}"
    state_manager = await get_state_manager()
    
    # Получаем реальное имя tool из созданного tool объекта
    tools = await parent_agent.get_tools()
    sub_agent_tool_obj = None
    for tool in tools:
        if hasattr(tool, 'name') and tool.name:
            # Ищем tool по имени (должно быть "sub_agent" из config.name="Sub Agent")
            if tool.name == "sub_agent" or sub_agent_id in str(tool):
                sub_agent_tool_obj = tool
                break
    
    if not sub_agent_tool_obj:
        # Если не нашли, используем первый tool который не session_set
        for tool in tools:
            if hasattr(tool, 'name') and tool.name != "session_set":
                sub_agent_tool_obj = tool
                break
    
    sub_agent_tool_name = sub_agent_tool_obj.name if sub_agent_tool_obj and hasattr(sub_agent_tool_obj, 'name') else sub_agent_tool.tool_id.split(":")[1]
    global_mock.reset_call_counts()
    
    # Новая логика: очередь ответов в порядке вызова
    # 1. Родитель вызывает session_set для parent_data
    # 2. После session_set родитель вызывает sub_agent
    # 3. Sub_agent вызывает session_set для sub_data
    # 4. После session_set sub_agent завершается
    global_mock.configure(
        response_queue=[
            # 1. Родитель: вызываем session_set
            {"type": "tool_call", "tool": "session_set", "args": {"key": "parent_data", "value": "test"}},
            # 2. После session_set: вызываем sub_agent
            {"type": "tool_call", "tool": sub_agent_tool_name, "args": {"request": "Сохрани sub_data"}},
            # 3. Sub_agent: вызываем session_set
            {"type": "tool_call", "tool": "session_set", "args": {"key": "sub_data", "value": "test2"}},
            # 4. После session_set sub_agent: завершаем
            {"type": "text", "content": "Готово"},
        ]
    )
    
    # Вызываем родителя
    result = await parent_agent.ainvoke({
        "messages": [HumanMessage(content="Сохрани parent_data и вызови sub_agent")],
        "session_id": parent_session_id
    })
    
    # Проверяем что store содержит оба значения
    result_store = result.get("store", {})
    print(f"\n🔍 result_store: {result_store}")
    print(f"🔍 result_store type: {type(result_store)}")
    print(f"🔍 result_store.get('parent_data'): {result_store.get('parent_data')}")
    print(f"🔍 result_store.get('sub_data'): {result_store.get('sub_data')}")
    print(f"🔍 result.get('store_id'): {result.get('store_id')}")
    
    # Проверяем что в БД есть sub_data
    store_data = await state_manager.load_store(parent_session_id)
    print(f"🔍 store_data из БД: {store_data}")
    print(f"🔍 store_data.get('sub_data'): {store_data.get('sub_data')}")
    
    # Проверяем sub_session_id
    sub_session_id = await state_manager.get_sub_session_id(
        parent_session_id=parent_session_id,
        sub_agent_id=sub_agent_id,
        policy=SubAgentMemoryPolicy.SNAPSHOT
    )
    print(f"🔍 sub_session_id: {sub_session_id}")
    
    # Проверяем state субагента
    sub_state = await state_manager.get_or_create_session(sub_session_id)
    if sub_state:
        print(f"🔍 sub_state.get('store'): {sub_state.get('store')}")
        print(f"🔍 sub_state.get('store_id'): {sub_state.get('store_id')}")
        print(f"🔍 sub_state['store'].get('sub_data'): {sub_state['store'].get('sub_data') if isinstance(sub_state.get('store'), dict) else 'не dict'}")
    
    # Проверяем что parent_data есть
    assert result_store.get("parent_data") == "test", f"parent_data должен быть 'test', получен: {result_store.get('parent_data')}"
    
    # Проверяем что sub_data есть
    assert result_store.get("sub_data") == "test2", f"sub_data должен быть 'test2', получен: {result_store.get('sub_data')}"
    
    # Проверяем что это StoreProxy
    assert isinstance(result_store, StoreProxy), f"store должен быть StoreProxy, получен: {type(result_store)}"
    
    # Проверяем что store_id правильный
    assert result.get("store_id") == parent_session_id, f"store_id должен быть {parent_session_id}, получен: {result.get('store_id')}"

