"""
Конфигурация флоу для бота ассистента закупщика.
"""

from apps.agents.models import FlowConfig

# Конфигурация флоу
fashn_buyer_flow_config = FlowConfig(
    name="Fashn Buyer Flow",
    description="Флоу для сбора информации о брендовых вещах через Telegram бота",
    entry_point_agent="apps.agents.flows.custom.fashn_buyer.agent.FashnBuyerAgent",
    platforms={"telegram": {"username": "fashn_agents_lab_test_bot"}},
)
