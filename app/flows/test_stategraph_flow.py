"""
Flow для тестирования всех типов нод в StateGraph агенте.
"""

from app.models import FlowConfig

test_stategraph_flow_config = FlowConfig(
    flow_id="app.flows.test_stategraph_flow.test_stategraph_flow_config",
    name="Test StateGraph Flow",
    description="Демонстрация всех типов нод: AGENT_NODE, TOOL_NODE, FUNCTION_NODE, MESSAGE_NODE, FLOW_NODE, ROUTER_NODE",
    entry_point_agent="app.agents.test_stategraph_agent.test_stategraph_agent_config",
    timeout=120,
    max_retries=3,
    is_public=True,
    variables={
        "bot_name": "Test Bot",
        "max_attempts": 3,
        "greeting_message": "Привет! Я демонстрационный бот."
    },
    store={
        "warehouse_id": None,
        "courier_id": None,
        "user_name": None
    }
)

