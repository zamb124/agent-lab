"""
Конфигурация флоу для Figma Designer агента.
"""

from app.models import FlowConfig

# Конфигурация флоу
figma_designer_flow_config = FlowConfig(
    name="Figma Designer Flow",
    description="Флоу для создания интерфейсов в Figma на основе требований пользователя, используя компонентную систему Туту.ру",
    entry_point_agent="app.agents.figma_designer.agent.FigmaDesignAgent",
    platforms={"web": {}, "api": {}},
)


