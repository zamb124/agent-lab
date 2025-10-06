"""
Простой флоу для работы с погодой.
"""

from app.models import FlowConfig

# Простая конфигурация флоу
weather_flow_config = FlowConfig(
    name="Weather Flow",
    description="Простой флоу для получения информации о погоде",
    entry_point_agent="app.agents.weather.agent.WeatherAgent",
    platforms={"api": {}, "telegram": {"username": "agent_lab_whether_bot"}},
)
