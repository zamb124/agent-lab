"""
WebhookTriggerHandler — inbound HTTP webhook → TriggerExecutor.

Регистрация только выставляет webhook_url и status=active.
Исполнение — POST /triggers/webhook/{flow_id}/{trigger_id}.
"""

from typing import override

from apps.flows.src.models import (
    TriggerConfig,
    TriggerStatus,
    TriggerType,
    WebhookTriggerConfig,
)
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
)
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


class WebhookTriggerHandler(BaseTriggerHandler):
    """Handler для generic HTTP webhook триггеров."""

    trigger_type: TriggerType = TriggerType.WEBHOOK

    def __init__(self, base_url: str) -> None:
        super().__init__(base_url)
        self._executor: TriggerExecutor = TriggerExecutor()

    @override
    async def register(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        self._log_register(flow_id, trigger.trigger_id)
        try:
            _ = WebhookTriggerConfig.model_validate(trigger.config)
        except Exception as exc:
            raise TriggerRegistrationError(
                trigger_type="webhook",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"invalid WebhookTriggerConfig: {exc}",
            ) from exc

        trigger.webhook_url = self.generate_webhook_url(flow_id, trigger.trigger_id)
        trigger.status = TriggerStatus.ACTIVE
        trigger.last_error = None
        logger.info(
            "flows.webhook.trigger.registered.flow_id.trigger",
            flow_id=flow_id,
            trigger=trigger.trigger_id,
            url=trigger.webhook_url,
        )
        return trigger

    @override
    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        self._log_unregister(flow_id, trigger.trigger_id)
        trigger.webhook_url = None
        trigger.status = TriggerStatus.INACTIVE
        trigger.last_error = None

    @override
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
    ) -> JsonObject:
        flow_config = await FlowConfig.get_latest(flow_id)
        if flow_config is None:
            raise TriggerRegistrationError(
                trigger_type="webhook",
                flow_id=flow_id,
                trigger_id=trigger_id,
                message=f"Flow not found: {flow_id}",
            )
        trigger = flow_config.triggers.get(trigger_id)
        if trigger is None:
            raise TriggerRegistrationError(
                trigger_type="webhook",
                flow_id=flow_id,
                trigger_id=trigger_id,
                message=f"Trigger not found: {trigger_id}",
            )
        if trigger.type != TriggerType.WEBHOOK:
            raise TriggerRegistrationError(
                trigger_type="webhook",
                flow_id=flow_id,
                trigger_id=trigger_id,
                message=f"Trigger type is {trigger.type.value}, expected webhook",
            )
        return await self._executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
            user_id="webhook_inbound",
        )


__all__ = ["WebhookTriggerHandler"]
