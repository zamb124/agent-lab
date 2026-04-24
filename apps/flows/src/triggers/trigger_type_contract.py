"""
Контракт поведения триггеров по TriggerType: пост-выход flow, UI, эффективные output_actions.
"""

from typing import List

from apps.flows.src.models import TriggerConfig
from apps.flows.src.models.channel_config import OutputAction, default_output_actions_for_trigger
from apps.flows.src.models.enums import TriggerType


def trigger_supports_post_flow_output(trigger_type: TriggerType) -> bool:
    if trigger_type == TriggerType.CRON:
        return False
    return True


def default_post_flow_output_enabled(trigger_type: TriggerType) -> bool:
    return trigger_supports_post_flow_output(trigger_type)


def trigger_show_output_tab_in_ui(trigger_type: TriggerType) -> bool:
    return trigger_supports_post_flow_output(trigger_type)


def effective_output_actions_for_trigger(trigger: TriggerConfig) -> List[OutputAction]:
    if not trigger_supports_post_flow_output(trigger.type):
        return []
    if not trigger.post_flow_output_enabled:
        return []
    if trigger.output_actions:
        return list(trigger.output_actions)
    return default_output_actions_for_trigger(trigger.trigger_id, trigger.type)


__all__ = [
    "default_post_flow_output_enabled",
    "effective_output_actions_for_trigger",
    "trigger_show_output_tab_in_ui",
    "trigger_supports_post_flow_output",
]
