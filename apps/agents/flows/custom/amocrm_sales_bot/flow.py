"""
Конфигурация флоу для бота ассистента закупщика.
"""

from apps.agents.models import FlowConfig

# Конфигурация флоу
sales_bot_flow_config = FlowConfig(
    name="Fashn Buyer Flow",
    description="Флоу для сбора информации о брендовых вещах через Telegram бота",
    entry_point_agent="apps.agents.flows.custom.amocrm_sales_bot.agent.AmocrmSalesBot",
    platforms={"amocrm": {}, "web": {}, "telegram": {}},
)
