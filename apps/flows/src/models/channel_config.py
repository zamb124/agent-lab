"""
ChannelConfig - конфигурация каналов для отправки сообщений.

Используется в:
- ChannelNode (нода графа)
- TriggerConfig.output_actions (автоматическая отправка после агента)
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from core.models import StrictBaseModel
from .enums import ChannelType, TriggerType


class OutputAction(StrictBaseModel):
    """
    Действие отправки сообщения в канал.
    
    Используется в trigger.output_actions для автоматической отправки
    после выполнения агента.
    
    Пример (ответ в тот же чат, chat_id из триггера):
    {
        "channel": "telegram",
        "action": "send_message",
        "mapping": {
            "recipient": "@state:triggers.tg_1.context.chat_id",
            "text": "@state:response"
        },
        "config": {
            "parse_mode": "HTML"
        },
        "condition": "@state:should_reply == true"
    }
    """
    
    channel: ChannelType = Field(..., description="Тип канала (telegram, email, etc)")
    action: str = Field(..., description="Действие: send_message, send_photo, send_document")
    
    mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг параметров: param_name -> @state:field.path"
    )
    
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Статические параметры (parse_mode, etc)"
    )
    
    condition: Optional[str] = Field(
        default=None,
        description="Условие выполнения: @state:field == value"
    )


class ChannelNodeConfig(StrictBaseModel):
    """
    Конфигурация ChannelNode в графе агента.
    
    Пример ноды:
    {
        "type": "channel",
        "channel": "telegram",
        "action": "send_message",
        "channel_config": {
            "bot_token": "@var:my_bot_token",
            "parse_mode": "HTML"
        },
        "input_mapping": {
            "recipient": "@state:triggers.my_trigger.context.chat_id",
            "text": "@state:response"
        }
    }
    """
    
    channel: ChannelType = Field(..., description="Тип канала")
    action: str = Field(default="send_message", description="Действие")
    
    channel_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Параметры канала (bot_token для Telegram, smtp для Email)"
    )


def default_output_actions_for_trigger(
    trigger_id: str,
    trigger_type: TriggerType,
) -> List[OutputAction]:
    if trigger_type == TriggerType.TELEGRAM:
        return [
            OutputAction(
                channel=ChannelType.TELEGRAM,
                action="send_message",
                mapping={
                    "recipient": f"@state:triggers.{trigger_id}.context.chat_id",
                    "text": "@state:response",
                },
                config={"parse_mode": "HTML"},
                condition=None,
            )
        ]
    return []


__all__ = [
    "OutputAction",
    "ChannelNodeConfig",
    "ChannelType",
    "default_output_actions_for_trigger",
]
