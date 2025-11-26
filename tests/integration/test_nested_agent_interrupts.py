"""
Тест рекурсивного восстановления при вложенных interrupts на 3 уровнях.

Проверяет что:
1. EntryAgent вызывает SubAgentA
2. SubAgentA вызывает SubSubAgentB
3. SubSubAgentB вызывает ask_user
4. Пользователь отвечает - управление возвращается в SubSubAgentB
5. SubSubAgentB завершается - управление возвращается в SubAgentA
6. SubAgentA вызывает interrupt
7. Пользователь отвечает - управление возвращается в SubAgentA
8. SubAgentA завершается - управление возвращается в EntryAgent
9. EntryAgent вызывает interrupt
10. Пользователь отвечает - управление возвращается в EntryAgent
"""
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from apps.agents.agents.base import AgentInterrupt
from apps.agents.services.state_manager import get_state_manager
from apps.agents.models import AgentConfig, AgentType, LLMConfig


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_nested_agent_interrupts_three_levels(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """Тест: EntryAgent -> SubAgentA -> SubSubAgentB -> ask_user -> ответ -> SubAgentA -> ask_user -> ответ -> EntryAgent -> ask_user -> ответ"""
    
    subsub_agent_id = f"test_subsub_agent_{unique_id('agent')}"
    sub_agent_id = f"test_sub_agent_{unique_id('agent')}"
    entry_agent_id = f"test_entry_agent_{unique_id('agent')}"
    
    from apps.agents.models import ToolReference, CodeMode
    
    ask_user_tool = ToolReference(
        tool_id="ask_user",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="apps.agents.tools.misc.standard.ask_user",
        description="Запрашивает информацию у пользователя"
    )
    
    await agent_repo.set(AgentConfig(
        agent_id=subsub_agent_id,
        name="SubSubAgentB",
        type=AgentType.REACT,
        prompt="Узнай город. Если нет - вызови ask_user('Какой город?')",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[ask_user_tool]
    ))
    
    await agent_repo.set(AgentConfig(
        agent_id=sub_agent_id,
        name="SubAgentA",
        type=AgentType.REACT,
        prompt="Вызови subsub_agent_tool для города. После получения спроси ask_user('Какая погода нужна?')",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[ask_user_tool]
    ))
    
    await agent_repo.set(AgentConfig(
        agent_id=entry_agent_id,
        name="EntryAgent",
        type=AgentType.REACT,
        prompt="Вызови sub_agent_tool. После получения спроси ask_user('Показать результат?')",
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
        tools=[ask_user_tool]
    ))
    
    entry_agent = await agent_factory.get_agent(entry_agent_id)
    sub_agent = await agent_factory.get_agent(sub_agent_id)
    subsub_agent = await agent_factory.get_agent(subsub_agent_id)
    
    sub_agent_tool_ref = ToolReference(
        tool_id=f"agent:{sub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path=sub_agent_id,
        description="SubAgentA для получения города и погоды"
    )
    
    subsub_agent_tool_ref = ToolReference(
        tool_id=f"agent:{subsub_agent_id}",
        code_mode=CodeMode.CODE_REFERENCE,
        function_path=subsub_agent_id,
        description="SubSubAgentB для получения города"
    )
    
    entry_agent.config.tools = [sub_agent_tool_ref, ask_user_tool]
    sub_agent.config.tools = [subsub_agent_tool_ref, ask_user_tool]
    
    await agent_repo.set(entry_agent.config)
    await agent_repo.set(sub_agent.config)
    
    entry_agent = await agent_factory.get_agent(entry_agent_id)
    sub_agent = await agent_factory.get_agent(sub_agent_id)
    
    session_id = f"test_nested_{unique_id('session')}"
    state_manager = await get_state_manager()
    
    mock_llm.reset_call_counts()
    original_agenerate = mock_llm._agenerate
    
    call_counter = {"entry": 0, "sub": 0, "subsub": 0}
    
    async def mock_agenerate(messages, **kwargs):
        last_message = messages[-1].content if messages else ""
        messages_str = str(messages).lower()
        
        if "sub_agent_tool" in messages_str and call_counter["entry"] == 0:
            call_counter["entry"] += 1
            tool_calls = [{"name": "sub_agent_tool", "args": {"request": "узнай город"}, "id": "call_entry"}]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=tool_calls))])
        
        if "subsub_agent_tool" in messages_str and call_counter["sub"] == 0:
            call_counter["sub"] += 1
            tool_calls = [{"name": "subsub_agent_tool", "args": {"request": "узнай город"}, "id": "call_sub"}]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=tool_calls))])
        
        if "узнай город" in last_message.lower() and "ask_user" not in messages_str and call_counter["subsub"] == 0:
            call_counter["subsub"] += 1
            tool_calls = [{"name": "ask_user", "args": {"question": "Какой город?"}, "id": "call_subsub_ask"}]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=tool_calls))])
        
        if "Москва" in last_message and call_counter["subsub"] == 1:
            call_counter["subsub"] += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Город: Москва"))])
        
        if "Город: Москва" in last_message and call_counter["sub"] == 1:
            call_counter["sub"] += 1
            tool_calls = [{"name": "ask_user", "args": {"question": "Какая погода нужна?"}, "id": "call_sub_ask"}]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=tool_calls))])
        
        if "Температура" in last_message and call_counter["sub"] == 2:
            call_counter["sub"] += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Погода: Температура для Москвы"))])
        
        if "Погода: Температура" in last_message and call_counter["entry"] == 1:
            call_counter["entry"] += 1
            tool_calls = [{"name": "ask_user", "args": {"question": "Показать результат?"}, "id": "call_entry_ask"}]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=tool_calls))])
        
        if "Да" in last_message and call_counter["entry"] == 2:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Результат: Температура в Москве +5°C"))])
        
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Выполнено"))])
    
    mock_llm._agenerate = mock_agenerate
    
    try:
        # Шаг 1: EntryAgent -> SubAgentA -> SubSubAgentB -> ask_user
        print(f"\n{'='*60}\n📝 Шаг 1: Вызываем EntryAgent (ожидаем interrupt в SubSubAgentB)\n{'='*60}\n")
        
        initial_state = {
            "messages": [HumanMessage(content="узнай погоду")],
            "store": {},
            "session_id": session_id,
            "task_id": "",
            "user_id": "test_user",
            "remaining_steps": 25,
        }
        
        try:
            await entry_agent.ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})
        except AgentInterrupt as interrupt:
            assert interrupt.value == "Какой город?", f"Неправильный вопрос: {interrupt.value}"
            
            saved_state = await state_manager.get_or_create_session(session_id)
            entry_interrupt = saved_state["interrupt_context"]
            assert entry_interrupt["type"] == "tool_call"
            
            sub_state = await state_manager.get_or_create_session(entry_interrupt["sub_session_id"])
            sub_interrupt = sub_state["interrupt_context"]
            assert sub_interrupt["type"] == "tool_call"
            
            subsub_state = await state_manager.get_or_create_session(sub_interrupt["sub_session_id"])
            subsub_interrupt = subsub_state["interrupt_context"]
            assert subsub_interrupt["interrupt_message"] == "Какой город?"
            
            print("✅ Все 3 уровня сохранили interrupt_context")
            
            # Шаг 2: Ответ "Москва" -> возврат в SubSubAgentB -> SubAgentA -> ask_user
            print(f"\n{'='*60}\n📝 Шаг 2: Пользователь отвечает 'Москва'\n{'='*60}\n")
            
            saved_state["messages"].append(HumanMessage(content="Москва"))
            
            try:
                await entry_agent.ainvoke(saved_state, config={"configurable": {"thread_id": session_id}})
            except AgentInterrupt as interrupt:
                assert interrupt.value == "Какая погода нужна?", f"Неправильный вопрос: {interrupt.value}"
                
                saved_state = await state_manager.get_or_create_session(session_id)
                entry_interrupt = saved_state["interrupt_context"]
                assert entry_interrupt["type"] == "tool_call"
                
                sub_state = await state_manager.get_or_create_session(entry_interrupt["sub_session_id"])
                sub_interrupt = sub_state["interrupt_context"]
                assert sub_interrupt["interrupt_message"] == "Какая погода нужна?"
                
                print("✅ Управление вернулось в SubAgentA")
                
                # Шаг 3: Ответ "Температура" -> возврат в SubAgentA -> EntryAgent -> ask_user
                print(f"\n{'='*60}\n📝 Шаг 3: Пользователь отвечает 'Температура'\n{'='*60}\n")
                
                saved_state["messages"].append(HumanMessage(content="Температура"))
                
                try:
                    await entry_agent.ainvoke(saved_state, config={"configurable": {"thread_id": session_id}})
                except AgentInterrupt as interrupt:
                    assert interrupt.value == "Показать результат?", f"Неправильный вопрос: {interrupt.value}"
                    
                    saved_state = await state_manager.get_or_create_session(session_id)
                    entry_interrupt = saved_state["interrupt_context"]
                    assert entry_interrupt["interrupt_message"] == "Показать результат?"
                    
                    print("✅ Управление вернулось в EntryAgent")
                    
                    # Шаг 4: Ответ "Да" -> EntryAgent завершается
                    print(f"\n{'='*60}\n📝 Шаг 4: Пользователь отвечает 'Да'\n{'='*60}\n")
                    
                    saved_state["messages"].append(HumanMessage(content="Да"))
                    
                    result = await entry_agent.ainvoke(saved_state, config={"configurable": {"thread_id": session_id}})
                    
                    assert "messages" in result
                    assert "__interrupt__" not in result
                    
                    print(f"\n{'='*60}\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ\n{'='*60}\n")
    
    finally:
        mock_llm._agenerate = original_agenerate

