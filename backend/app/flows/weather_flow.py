"""
Простой флоу для работы с погодой.
"""
from app.core.models import FlowConfig

# Простая конфигурация флоу
weather_flow_config = FlowConfig(
    flow_id="weather_flow",
    name="Weather Flow",
    description="Простой флоу для получения информации о погоде",
    entry_point_agent="app.agents.weather.agent.WeatherAgent",
    platforms={
        "api": {},
        "telegram": {
            'username': 'agent_lab_whether_bot'
        }
    }
)
