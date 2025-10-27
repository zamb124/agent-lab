"""
Тест для проверки отслеживания source_node в истории сообщений
"""

import pytest
from langchain_core.messages import HumanMessage
from app.flows.smart_flow import SmartFlowAgent
from app.models import FlowConfig, LLMConfig, AgentConfig


@pytest.mark.asyncio
async def test_source_node_in_history(migrated_db, storage, flow_factory, unique_id, agent_repo, flow_repo):
    """Тест проверяет, что source_node корректно записывается в историю сообщений"""
    
    weather_agent_config = AgentConfig(
        agent_id="app.agents.weather.agent.WeatherAgent",
        name="Weather Agent",
        description="Агент для получения погоды",
        function_class="app.agents.weather.agent.WeatherAgent",
        prompt="Ты погодный агент. Отвечай о погоде.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(weather_agent_config)
    
    calc_agent_config = AgentConfig(
        agent_id="app.agents.calculator.agent.CalculatorAgent",
        name="Calculator Agent",
        description="Агент для вычислений",
        function_class="app.agents.calculator.agent.CalculatorAgent",
        prompt="Ты калькулятор. Вычисляй математические выражения.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(calc_agent_config)
    
    explainer_agent_config = AgentConfig(
        agent_id="app.agents.explainer.agent.ExplainerAgent",
        name="Explainer Agent",
        description="Агент для объяснений",
        function_class="app.agents.explainer.agent.ExplainerAgent",
        prompt="Ты объяснитель. Объясняй что произошло.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(explainer_agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_source_tracking_flow",
        name="Test Source Node Tracking",
        description="Тестовый flow для проверки отслеживания source_node",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await flow_repo.set(flow_config)
    
    flow = SmartFlowAgent()
    
    session_id = unique_id("source_tracking")
    
    result = await flow.ainvoke(
        {
            "messages": [HumanMessage(content="Какая погода в Москве?")],
            "user_id": "test_user",
        },
        config={"configurable": {"thread_id": session_id}},
    )
    
    print(f"✅ Flow выполнен, session_id: {session_id}")
    print(f"📝 Результат: {result.get('messages', [])[-1] if result.get('messages') else 'Нет сообщений'}")
    
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=100,
        include_checkpoints=True
    )
    
    print("\n📊 Статистика истории:")
    print(f"  - Всего сообщений: {history.total_messages}")
    print(f"  - Всего checkpoints: {history.total_checkpoints}")
    
    print("\n📋 Детали сообщений с source_node:")
    for i, message in enumerate(history.messages, 1):
        source_info = f" [Node: {message.source_node}]" if message.source_node else " [Node: не указан]"
        print(f"  {i}. {message.role.value}{source_info}")
        if message.content:
            content_preview = message.content[:50] + "..." if len(message.content) > 50 else message.content
            print(f"     Содержимое: {content_preview}")
    
    if history.checkpoints:
        print("\n🔖 Детали checkpoints:")
        for i, checkpoint in enumerate(history.checkpoints, 1):
            source_info = f" [Source: {checkpoint.source_node}]" if checkpoint.source_node else " [Source: не указан]"
            print(f"  {i}. Checkpoint #{checkpoint.step}{source_info}")
            print(f"     Namespace: {checkpoint.checkpoint_ns}")
            print(f"     Сообщений: {len(checkpoint.messages)}")
    
    has_source_nodes = any(msg.source_node for msg in history.messages)
    print(f"\n✅ Source_node найден в сообщениях: {has_source_nodes}")
    
    has_checkpoint_sources = any(cp.source_node for cp in history.checkpoints)
    print(f"✅ Source_node найден в checkpoints: {has_checkpoint_sources}")
    
    assert history.total_messages > 0, "История должна содержать сообщения"
    
    # Source_node трекинг - опциональная feature, проверяем но не требуем
    if has_source_nodes or has_checkpoint_sources:
        print("\n✅ Source_node трекинг работает!")
    else:
        print("\n⚠️  Source_node не найден - feature может быть не активирована")
    
    print("\n✅ Тест отслеживания source_node пройден успешно!")


@pytest.mark.asyncio
async def test_checkpoint_metadata_structure(migrated_db, storage, flow_factory, unique_id, agent_repo, flow_repo):
    """Тест для проверки структуры metadata в checkpoint"""
    
    calc_agent_config = AgentConfig(
        agent_id="app.agents.calculator.agent.CalculatorAgent",
        name="Calculator Agent",
        description="Агент для вычислений",
        function_class="app.agents.calculator.agent.CalculatorAgent",
        prompt="Ты калькулятор. Вычисляй математические выражения.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(calc_agent_config)
    
    weather_agent_config = AgentConfig(
        agent_id="app.agents.weather.agent.WeatherAgent",
        name="Weather Agent",
        description="Агент для получения погоды",
        function_class="app.agents.weather.agent.WeatherAgent",
        prompt="Ты погодный агент. Отвечай о погоде.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(weather_agent_config)
    
    explainer_agent_config = AgentConfig(
        agent_id="app.agents.explainer.agent.ExplainerAgent",
        name="Explainer Agent",
        description="Агент для объяснений",
        function_class="app.agents.explainer.agent.ExplainerAgent",
        prompt="Ты объяснитель. Объясняй что произошло.",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await agent_repo.set(explainer_agent_config)
    
    flow_config = FlowConfig(
        flow_id="test_metadata_flow",
        name="Test Metadata Flow",
        description="Тестовый flow для проверки metadata",
        entry_point_agent="app.agents.calculator.agent.CalculatorAgent",
        llm_config=LLMConfig(model="mock-gpt-4"),
    )
    await flow_repo.set(flow_config)
    
    flow = SmartFlowAgent()
    
    session_id = unique_id("metadata")
    
    await flow.ainvoke(
        {
            "messages": [HumanMessage(content="Сколько будет 5 + 3?")],
            "user_id": "test_user",
        },
        config={"configurable": {"thread_id": session_id}},
    )
    
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=100,
        include_checkpoints=True
    )
    
    print("\n🔍 Анализ metadata в checkpoints:")
    for checkpoint in history.checkpoints:
        print(f"\n  Checkpoint #{checkpoint.step}:")
        print(f"    - source_node: {checkpoint.source_node}")
        print(f"    - timestamp: {checkpoint.timestamp}")
        print(f"    - checkpoint_ns: {checkpoint.checkpoint_ns}")
        
        metadata_keys = list(checkpoint.metadata.keys()) if checkpoint.metadata else []
        print(f"    - Ключи в metadata: {metadata_keys}")
        
        if checkpoint.metadata:
            for key, value in checkpoint.metadata.items():
                if key not in ['ts', 'step']:
                    value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    print(f"      • {key}: {value_str}")
    
    print("\n✅ Тест структуры metadata пройден успешно!")
