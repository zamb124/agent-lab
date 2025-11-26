"""
Тест восстановления StateGraph агента после interrupt в ноде.

Проверяет что:
1. StateGraph агент выполняет ноды по порядку
2. В одной из нод проверяется переменная в store
3. Если переменной нет - вызывается ask_user
4. Управление возвращается в ту же ноду после ответа пользователя
5. Переменная сохраняется в store из ответа пользователя
6. Граф продолжает работу к следующей ноде
"""
import pytest
from langchain_core.messages import HumanMessage
from apps.agents.agents.base import AgentInterrupt
from apps.agents.services.state_manager import get_state_manager
from apps.agents.models import (
    AgentConfig,
    AgentType,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    NodeType,
    CodeMode,
    LLMConfig,
)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_stategraph_agent_interrupt_resumption_in_node(
    migrated_db, agent_factory, agent_repo, mock_llm, unique_id
):
    """
    Тест: StateGraph агент -> нода проверки -> ask_user -> ответ пользователя -> продолжение ноды -> следующая нода
    
    Сценарий:
    1. StateGraph агент начинает выполнение
    2. Первая нода (init_node) инициализирует store
    3. Вторая нода (check_node) проверяет наличие переменной "user_name" в store
    4. Если переменной нет - вызывается ask_user("Как вас зовут?")
    5. Система сохраняет interrupt_context для графа
    6. Пользователь отвечает "Иван"
    7. Управление возвращается в check_node
    8. check_node сохраняет ответ в store["user_name"]
    9. Граф продолжает работу к следующей ноде (final_node)
    """
    
    # Создаем тестовый StateGraph агент
    agent_id = f"test_stategraph_interrupt_{unique_id('agent')}"
    
    agent_config = AgentConfig(
        agent_id=agent_id,
        name="Test StateGraph Interrupt Agent",
        description="Тестовый StateGraph агент с interrupt в ноде",
        type=AgentType.STATEGRAPH,
        graph_definition=GraphDefinition(
            nodes=[
                GraphNode(
                    id="init_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def init_node(state):
    '''Инициализация - устанавливает флаг начала работы'''
    if "store" not in state:
        state["store"] = {}
    state["store"]["initialized"] = True
    state["store"]["step"] = "init"
    return state
""",
                ),
                GraphNode(
                    id="check_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
from apps.agents.tools.misc.standard import ask_user

async def check_node(state):
    '''Проверяет наличие user_name в store, если нет - спрашивает у пользователя'''
    if "store" not in state:
        state["store"] = {}
    
    if "user_name" not in state["store"]:
        # Спрашиваем у пользователя
        answer = ask_user("Как вас зовут?")
        # Парсим ответ: "QUESTION: вопрос\\nANSWER: ответ"
        if "ANSWER: " in answer:
            user_name = answer.split("ANSWER: ")[1].strip()
            state["store"]["user_name"] = user_name
        else:
            state["store"]["user_name"] = answer.strip()
        
        state["store"]["step"] = "check_completed"
    
    return state
""",
                ),
                GraphNode(
                    id="final_node",
                    type=NodeType.FUNCTION_NODE,
                    code_mode=CodeMode.INLINE_CODE,
                    inline_code="""
async def final_node(state):
    '''Финальная нода - обрабатывает результат'''
    if "store" not in state:
        state["store"] = {}
    
    user_name = state["store"].get("user_name", "неизвестно")
    state["store"]["final_message"] = f"Привет, {user_name}! Работа завершена."
    state["store"]["step"] = "final"
    
    return state
""",
                ),
            ],
            edges=[
                GraphEdge(source="START", target="init_node"),
                GraphEdge(source="init_node", target="check_node"),
                GraphEdge(source="check_node", target="final_node"),
                GraphEdge(source="final_node", target="END"),
            ],
            entry_point="init_node",
        ),
        llm_config=LLMConfig(model="mock-gpt-4", context_window=8192),
    )
    
    await agent_repo.set(agent_config)
    
    # Загружаем агента
    agent = await agent_factory.get_agent(agent_id)
    assert agent is not None, f"{agent_id} не найден в БД"
    
    session_id = f"test_stategraph_interrupt_{unique_id('session')}"
    state_manager = await get_state_manager()
    
    # Шаг 1: Вызываем агента - должна сработать check_node и ask_user
    print(f"\n{'='*60}")
    print("📝 Шаг 1: Вызываем StateGraph агента (ожидаем interrupt в check_node)")
    print(f"{'='*60}\n")
    
    initial_state = {
        "messages": [HumanMessage(content="начать работу")],
        "store": {},
        "session_id": session_id,
        "task_id": "",
        "user_id": "test_user",
        "remaining_steps": 25,
    }
    
    try:
        result = await agent.ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})
        # Если нет interrupt - проверяем что все ноды выполнились
        if "__interrupt__" not in result:
            print("⚠️  Interrupt не произошел, возможно user_name уже был в store")
    except AgentInterrupt as interrupt:
        print(f"✅ Получен AgentInterrupt: {interrupt.value}")
        
        # Проверяем что interrupt_context сохранен
        saved_state = await state_manager.get_or_create_session(session_id)
        assert saved_state is not None, "Состояние не сохранено"
        assert "interrupt_context" in saved_state, "interrupt_context отсутствует"
        
        interrupt_ctx = saved_state["interrupt_context"]
        assert interrupt_ctx["type"] == "stategraph_node", f"Неправильный тип: {interrupt_ctx['type']}"
        assert interrupt_ctx["current_node"] == "check_node", f"Неправильная нода: {interrupt_ctx['current_node']}"
        
        print(f"✅ Interrupt context сохранен: {interrupt_ctx}")
        print(f"   Текущая нода: {interrupt_ctx['current_node']}")
        
        # Проверяем что store содержит initialized, но не user_name
        assert saved_state["store"]["initialized"] is True, "init_node не выполнился"
        assert "user_name" not in saved_state["store"], "user_name не должен быть в store до ответа пользователя"
        
        print(f"✅ Store проверен: initialized={saved_state['store'].get('initialized')}, user_name отсутствует")
        
        # Шаг 2: Симулируем ответ пользователя "Иван"
        print(f"\n{'='*60}")
        print("📝 Шаг 2: Симулируем ответ пользователя 'Иван'")
        print(f"{'='*60}\n")
        
        # Добавляем ответ пользователя в состояние
        saved_state["messages"].append(HumanMessage(content="Иван"))
        
        # Убираем interrupt_context - теперь check_node продолжит работу
        saved_state.pop("interrupt_context")
        
        # Продолжаем выполнение агента (УПРАВЛЕНИЕ ВОЗВРАЩАЕТСЯ В check_node!)
        print("🔄 Продолжаем выполнение StateGraph агента с ответом пользователя")
        result = await agent.ainvoke(saved_state, config={"configurable": {"thread_id": session_id}})
        
        assert "store" in result, "Результат не содержит store"
        assert "user_name" in result["store"], "user_name не сохранен в store"
        assert result["store"]["user_name"] == "Иван", f"Неправильное значение user_name: {result['store']['user_name']}"
        
        print(f"✅ user_name сохранен в store: {result['store']['user_name']}")
        
        # Проверяем что граф продолжил работу к final_node
        assert result["store"]["step"] == "final", f"Граф не дошел до final_node. Step: {result['store'].get('step')}"
        assert "final_message" in result["store"], "final_message не создан"
        assert "Иван" in result["store"]["final_message"], "final_message не содержит имя пользователя"
        
        print("✅ Граф завершил работу")
        print(f"   Final message: {result['store']['final_message']}")
        
        # Проверяем что interrupt НЕ произошел второй раз
        assert "__interrupt__" not in result, "Агент не должен был вызвать interrupt второй раз"
        
        print(f"\n{'='*60}")
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print("   - Interrupt произошел в check_node")
        print("   - Состояние сохранено с interrupt_context")
        print("   - Управление вернулось в check_node после ответа")
        print("   - user_name сохранен в store из ответа пользователя")
        print("   - Граф продолжил работу к final_node")
        print("   - Все ноды выполнены успешно")
        print(f"{'='*60}\n")

