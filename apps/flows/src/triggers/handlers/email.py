"""
EmailTriggerHandler — platform mail (MailboxBinding) → TriggerExecutor.

Индекс Redis: flows:email_triggers:{mailbox_binding_id} → SET company_id|flow_id|trigger_id.
Срабатывание — из mail_sync_tick через dispatch_email_triggers_for_messages.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import override

from apps.flows.src.models import (
    EmailTriggerConfig,
    TriggerConfig,
    TriggerStatus,
    TriggerType,
)
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.triggers.email_filter import (
    email_message_matches_filter,
    email_trigger_index_key,
    email_trigger_index_member,
    inbound_mail_to_trigger_payload,
    parse_email_trigger_index_member,
)
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from core.clients.redis_client import RedisClient
from core.context import clear_context, get_context, set_context
from core.db.storage import Storage
from core.logging import get_logger
from core.mail.exceptions import MailConnectionNotFoundError
from core.mail.models import InboundMailMessage, MailboxBinding, MailConnectionStatus
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.types import JsonObject

logger = get_logger(__name__)

_EMAIL_TRIGGER_RUN_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def email_trigger_run_id(
    *,
    mailbox_binding_id: str,
    flow_id: str,
    trigger_id: str,
    mail_uid: str,
) -> str:
    """Детерминированный id run'а для дедупа повторного dispatch того же UID."""
    return str(
        uuid.uuid5(
            _EMAIL_TRIGGER_RUN_NAMESPACE,
            f"{mailbox_binding_id}:{flow_id}:{trigger_id}:{mail_uid}",
        )
    )


class EmailTriggerHandler(BaseTriggerHandler):
    """Handler для email-триггеров на platform MailboxBinding."""

    trigger_type: TriggerType = TriggerType.EMAIL

    def __init__(self, base_url: str, *, redis_client: RedisClient, mail_service: MailService) -> None:
        super().__init__(base_url)
        self.redis_client: RedisClient = redis_client
        self.mail_service: MailService = mail_service
        self._executor: TriggerExecutor = TriggerExecutor()

    @override
    async def register(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        self._log_register(flow_id, trigger.trigger_id)

        try:
            config = EmailTriggerConfig.model_validate(trigger.config)
        except Exception as exc:
            raise TriggerRegistrationError(
                trigger_type="email",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"invalid EmailTriggerConfig: {exc}",
            ) from exc

        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise TriggerRegistrationError(
                trigger_type="email",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="request context with user and active_company is required",
            )
        company_id = ctx.active_company.company_id
        user_id = ctx.user.user_id

        binding = await self._resolve_user_binding(
            mailbox_binding_id=config.mailbox_binding_id,
            company_id=company_id,
            user_id=user_id,
            flow_id=flow_id,
            trigger_id=trigger.trigger_id,
        )
        try:
            connection = await self.mail_service.require_connection_for_binding(binding)
        except MailConnectionNotFoundError as exc:
            raise TriggerRegistrationError(
                trigger_type="email",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=str(exc),
            ) from exc
        if connection.status != MailConnectionStatus.ACTIVE:
            raise TriggerRegistrationError(
                trigger_type="email",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"mail connection status is {connection.status.value}",
            )

        member = email_trigger_index_member(
            company_id=company_id,
            flow_id=flow_id,
            trigger_id=trigger.trigger_id,
        )
        _ = await self.redis_client.sadd(
            email_trigger_index_key(binding.mailbox_binding_id),
            member,
        )

        trigger.status = TriggerStatus.ACTIVE
        trigger.last_error = None
        logger.info(
            "flows.email.trigger.registered.flow_id.trigger",
            flow_id=flow_id,
            trigger=trigger.trigger_id,
            mailbox_binding_id=binding.mailbox_binding_id,
        )
        return trigger

    @override
    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        self._log_unregister(flow_id, trigger.trigger_id)
        raw_binding_id = trigger.config.get("mailbox_binding_id")
        if not isinstance(raw_binding_id, str) or not raw_binding_id.strip():
            logger.warning("flows.email.trigger.unregister.skipped.mailbox_binding_id", flow_id=flow_id, trigger=trigger.trigger_id)
            return

        ctx = get_context()
        company_id = (
            ctx.active_company.company_id
            if ctx is not None and ctx.active_company is not None
            else None
        )
        if company_id is None:
            logger.warning("flows.email.trigger.unregister.without.company", flow_id=flow_id, trigger=trigger.trigger_id)
            return

        member = email_trigger_index_member(
            company_id=company_id,
            flow_id=flow_id,
            trigger_id=trigger.trigger_id,
        )
        _ = await self.redis_client.srem(
            email_trigger_index_key(raw_binding_id.strip()),
            member,
        )

    @override
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
    ) -> JsonObject:
        flow_config = await FlowConfig.get_latest(flow_id)
        if flow_config is None:
            raise TriggerValidationError(f"Flow not found: {flow_id}")
        trigger = flow_config.triggers.get(trigger_id)
        if trigger is None:
            raise TriggerValidationError(f"Trigger not found: {trigger_id}")
        if trigger.type != TriggerType.EMAIL:
            raise TriggerValidationError(f"Trigger {trigger_id} is not email")
        if not trigger.enabled:
            raise TriggerValidationError(f"Trigger {trigger_id} is disabled")

        return await self._executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
        )

    async def _resolve_user_binding(
        self,
        *,
        mailbox_binding_id: str,
        company_id: str,
        user_id: str,
        flow_id: str,
        trigger_id: str,
    ) -> MailboxBinding:
        bindings = await self.mail_service.list_my_bindings(company_id)
        for binding in bindings:
            if binding.mailbox_binding_id == mailbox_binding_id:
                if binding.user_id != user_id:
                    raise TriggerRegistrationError(
                        trigger_type="email",
                        flow_id=flow_id,
                        trigger_id=trigger_id,
                        message="mailbox_binding_id does not belong to current user",
                    )
                return binding
        raise TriggerRegistrationError(
            trigger_type="email",
            flow_id=flow_id,
            trigger_id=trigger_id,
            message=f"mailbox_binding_id not found for user: {mailbox_binding_id}",
        )


async def dispatch_email_triggers_for_messages(
    *,
    redis_client: RedisClient,
    shared_storage: Storage,
    binding: MailboxBinding,
    messages: list[InboundMailMessage],
    dedup_ttl_seconds: int,
) -> int:
    """
    Запускает email-триггеры для новых писем ящика (из mail_sync_tick).

    Возвращает число успешных запусков TriggerExecutor.
    """
    if binding.user_id is None:
        raise ValueError(
            f"email trigger dispatch requires user_id for mailbox_binding_id={binding.mailbox_binding_id}"
        )
    if len(messages) == 0:
        return 0

    members = await redis_client.smembers(
        email_trigger_index_key(binding.mailbox_binding_id)
    )
    if not members:
        return 0

    company = await Company.get(binding.company_id)
    if company is None:
        logger.error("flows.email.trigger.dispatch.company.found", company_id=binding.company_id)
        return 0

    user = await User.get(binding.user_id)
    trigger_user = user if user is not None else User(
        user_id=binding.user_id,
        name=f"Mail:{binding.email_address}",
        companies={binding.company_id: ["member"]},
        active_company_id=binding.company_id,
    )

    fired = 0
    previous_context = get_context()
    context = Context(
        user=trigger_user,
        active_company=company,
        user_companies=[company],
        channel="trigger:email",
    )
    _ = set_context(context)
    try:
        for member in members:
            parsed = parse_email_trigger_index_member(member)
            if parsed is None:
                logger.warning("flows.email.trigger.index.invalid.member", member=member)
                continue
            company_id, flow_id, trigger_id = parsed
            if company_id != binding.company_id:
                continue

            flow_config = await FlowConfig.get_latest(flow_id)
            if flow_config is None:
                logger.warning("flows.email.trigger.dispatch.flow.found", flow_id=flow_id)
                continue
            trigger = flow_config.triggers.get(trigger_id)
            if trigger is None or trigger.type != TriggerType.EMAIL or not trigger.enabled:
                continue

            try:
                email_config = EmailTriggerConfig.model_validate(trigger.config)
            except Exception as exc:
                logger.warning(
                    "flows.email.trigger.dispatch.invalid.config",
                    flow_id=flow_id,
                    trigger=trigger_id,
                    error=exc,
                )
                continue

            if email_config.mailbox_binding_id != binding.mailbox_binding_id:
                continue

            for message in messages:
                if not email_message_matches_filter(email_config, message):
                    continue
                dedup_key = (
                    f"flows:email_trigger_fired:{binding.company_id}:"
                    f"{binding.mailbox_binding_id}:{flow_id}:{trigger_id}:{message.uid}"
                )
                existing = await shared_storage.get(
                    key=dedup_key,
                    force_global=True,
                )
                if existing is not None:
                    continue

                payload = inbound_mail_to_trigger_payload(
                    binding=binding,
                    message=message,
                )
                run_id = email_trigger_run_id(
                    mailbox_binding_id=binding.mailbox_binding_id,
                    flow_id=flow_id,
                    trigger_id=trigger_id,
                    mail_uid=message.uid,
                )
                executor = TriggerExecutor()
                _ = await executor.execute(
                    flow_id=flow_id,
                    trigger=trigger,
                    payload=payload,
                    user_id=binding.user_id,
                    metadata={
                        "mailbox_binding_id": binding.mailbox_binding_id,
                        "mail_uid": message.uid,
                    },
                    task_id=run_id,
                    context_id=run_id,
                )
                _ = await shared_storage.set(
                    key=dedup_key,
                    value=json.dumps(
                        {"fired_at": datetime.now(timezone.utc).isoformat()}
                    ),
                    ttl=dedup_ttl_seconds,
                    force_global=True,
                )
                fired += 1
    finally:
        if previous_context is not None:
            _ = set_context(previous_context)
        else:
            clear_context()

    return fired


__all__ = [
    "EmailTriggerHandler",
    "dispatch_email_triggers_for_messages",
    "email_trigger_run_id",
]
