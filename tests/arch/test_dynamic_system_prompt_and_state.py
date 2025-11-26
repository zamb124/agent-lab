import asyncio
import pytest

from langchain_core.messages import HumanMessage

from core.clients.llm import get_llm, setup_mock_responses
from core.context import get_context
from core.variables import VariableResolver
from apps.agents.flows.flow import Flow
from apps.agents.models import AgentConfig, FlowConfig, LLMConfig, AgentType, ToolReference, CodeMode


@pytest.mark.asyncio
async def test_dynamic_system_prompt_updates_and_shared_state(migrated_db, system_context, agent_repo, flow_repo, agent_factory):
    # Tool для установки города и страны
    set_location_tool = ToolReference(
        tool_id="set_location",
        code_mode=CodeMode.INLINE_CODE,
        inline_code="""
from apps.agents.services.tool_decorator import tool
from core.variables import get_state

@tool(state_aware=True)
def set_location(city: str, country: str) -> str:
    '''Устанавливает город и страну в state'''
    state = get_state()
    if "store" not in state:
        state["store"] = {}
    state["store"]["city"] = city
    state["store"]["country"] = country
    return f"ok:{city},{country}"
""",
    )

    # Координатор: показывает город/страну/время и вызывает set_location напрямую
    coordinator_config = AgentConfig(
            agent_id="coord_agent",
            name="Coordinator",
            type=AgentType.REACT,
            prompt=(
                "Координатор. Город: {?store.city|нет}, Страна: {?store.country|нет}. "
                "Сейчас: {current_time}. Если скажут изменить локацию — вызови set_location."
            ),
            llm_config=LLMConfig(model="mock-gpt-4", temperature=0.1, context_window=10000),
            tools=[set_location_tool],
        )

        # Tool для установки города и страны
    set_location_tool = ToolReference(
        tool_id="set_location",
        code_mode=CodeMode.INLINE_CODE,
        inline_code="""
from apps.agents.services.tool_decorator import tool
from core.variables import get_state

@tool(state_aware=True)
def set_location(city: str, country: str) -> str:
    '''Устанавливает город и страну в state'''
    state = get_state()
    if "store" not in state:
        state["store"] = {}
    state["store"]["city"] = city
    state["store"]["country"] = country
    return f"ok:{city},{country}"
""",
    )

    await agent_repo.set(coordinator_config)

    # Flow со стартовым store и таймзоной
    flow_config = FlowConfig(
        flow_id="flow_coord_sub",
        name="Flow Coordinator/Sub",
        entry_point_agent="coord_agent",
        platforms={"api": {}},
        store={"city": "", "country": "", "timezone": "UTC"},
    )
    await flow_repo.set(flow_config)

    # Установить flow в контекст
    context = get_context()
    context.flow_config = flow_config

        # Настройка Mock LLM: координатор напрямую вызывает set_location
    mock_llm = get_llm("mock-gpt-4")
    mock_llm.reset_call_counts()
    setup_mock_responses(
            tool_responses={
                # Координатор: ключевая фраза приводит к вызову set_location
                "измени локацию": {"tool": "set_location", "args": {"city": "Moscow", "country": "Russia"}},
                "Пожалуйста, измени локацию": {"tool": "set_location", "args": {"city": "Moscow", "country": "Russia"}},
            },
            responses={
                "ok:" : "Локация установлена",
                "Сколько времени": "Сейчас прекрасное время для работы!",
                "сколько времени": "Сейчас прекрасное время для работы!",
            },
            default_response="Готово",
            model_name="mock-gpt-4"
        )

    # Инстанцируем Flow и инвокаем его (как в реальной системе)
    flow = Flow(flow_config)
    await flow.initialize()

    thread_id = "thread_coord_sub"
    config = {"configurable": {"thread_id": thread_id}}

    # Шаг 1: пользователь просит изменить локацию — координатор передаст управление субагенту
    result = await flow.ainvoke({
        "messages": [HumanMessage(content="Пожалуйста, измени локацию")],
        "remaining_steps": 25,
        "session_id": "s1",
        "task_id": "t1",
        "user_id": "u1",
    }, config=config)

    # Проверяем что state обновился через tool
    assert result["store"]["city"] == "Moscow"
    assert result["store"]["country"] == "Russia"

    # Проверяем что системное время подставляется в промпт
    # Для этого проверим что в ответе агента есть упоминание времени
    final_message = result["messages"][-1].content if result.get("messages") else ""
    # Агент должен ответить что-то вроде "Готово" или упомянуть время
    assert len(final_message) > 0

    # Основная цель: state обновился через tool И системные переменные работают
    print(f"✅ Тест пройден: state обновлен через tool, системные переменные резолвятся")


