"""
Простой флоу для работы с погодой.
"""

from app.models import FlowConfig

# Простая конфигурация флоу
amocrm_flow_config = FlowConfig(
    name="AmoCRM Flow",
    description="Простой флоу для работы с AmoCRM",
    entry_point_agent="app.flows.test_flow.TestFlowAgent",
    platforms={"api": {}, "amocrm": {}},
)
