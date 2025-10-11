"""
Telegram Channel Management Flow - для управления публикациями в Telegram канале.
"""

from app.models import FlowConfig

# Telegram Channel Flow конфигурация
telegram_channel_flow_config = FlowConfig(
    flow_id="telegram_channel_manager",
    name="Telegram Channel Manager",
    description="Управление публикациями в Telegram канале @my_osom_tg_kanal",
    entry_point_agent="app.agents.telegram_channel.agent.TelegramChannelAgent",
    platforms={
        "telegram": {
            "token": "@var:agents_lab_tg_channel_test_bot_token",
            "username": "agents_lab_tg_channel_test_bot",
            "allowed_users": ["shvedvik"]
        },
        "web": {}
    },
    variables={
        "channel_id": "@my_osom_tg_kanal",
        "bot_token": "8412993684:AAGtwAUMO3OT8xCXHvGei2eUIqFK01gYfs8"
    },
    is_public=False,
)

