"""
PlatformEventTriggerHandler — событие шины `platform:events` → TriggerExecutor.

Индекс Redis: flows:event_triggers:{event_type} → SET company_id|flow_id|trigger_id.
Срабатывание — из consumer group `flows` (`PlatformEventConsumerService`)
через `dispatch_platform_event_triggers`; HTTP-входа у типа нет.

Идемпотентность at-least-once доставки: `task_id`/`context_id` детерминированно
выводятся из `event_id + trigger_id`, повторная доставка не создаёт второй run.
"""

from __future__ import annotations

import uuid
from typing import override

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import (
    EventFilter,
    PlatformEventTriggerConfig,
    TriggerConfig,
    TriggerStatus,
    TriggerType,
)
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from core.context import Context, User, clear_context, get_context, set_context
from core.events import (
    PlatformEvent,
    catalog_entry_for_event_type,
    load_platform_event_catalog_entry,
    validate_event_filters_against_fields,
)
from core.logging import get_logger
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)

_TRIGGER_RUN_NAMESPACE = uuid.UUID("b2f5f0f6-9f0e-4c1c-9a54-6c1f6d5b8a01")


async def validate_platform_event_trigger_config(
    config: PlatformEventTriggerConfig,
) -> None:
    """Fail-closed: filters только по filter_fields каталога события."""
    entry = await load_platform_event_catalog_entry(config.event_type)
    if entry is None:
        entry = catalog_entry_for_event_type(config.event_type)
    if entry is None:
        raise ValueError(
            f"platform event {config.event_type!r} is not in catalog; "
            + "register_platform_event + store_registered_platform_events required"
        )
    validate_event_filters_against_fields(
        [(item.path, item.op, item.value) for item in config.filters],
        entry.filter_fields,
    )


def platform_event_trigger_index_key(event_type: str) -> str:
    return f"flows:event_triggers:{event_type}"


def platform_event_trigger_index_member(
    *, company_id: str, flow_id: str, trigger_id: str
) -> str:
    return f"{company_id}|{flow_id}|{trigger_id}"


def parse_platform_event_trigger_index_member(member: str) -> tuple[str, str, str] | None:
    parts = member.split("|", 2)
    if len(parts) != 3:
        return None
    company_id, flow_id, trigger_id = parts
    if not company_id or not flow_id or not trigger_id:
        return None
    return company_id, flow_id, trigger_id


def _resolve_payload_path(payload: JsonValue, path: str) -> JsonValue:
    """Значение по dot-path; отсутствующий сегмент — None."""
    current: JsonValue = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def _filter_matches(filter_condition: EventFilter, payload: JsonValue) -> bool:
    actual = _resolve_payload_path(payload, filter_condition.path)
    expected = filter_condition.value
    match filter_condition.op:
        case "eq":
            return actual == expected
        case "ne":
            return actual != expected
        case "contains":
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            if isinstance(actual, list):
                return expected in actual
            return False


def platform_event_matches_filters(
    config: PlatformEventTriggerConfig, payload: JsonValue
) -> bool:
    """Все условия (AND) должны выполниться на payload события."""
    return all(_filter_matches(condition, payload) for condition in config.filters)


def platform_event_trigger_run_id(event_id: str, trigger_id: str) -> str:
    """Детерминированный id run'а для дедупликации at-least-once доставки."""
    return str(uuid.uuid5(_TRIGGER_RUN_NAMESPACE, f"{event_id}:{trigger_id}"))


class PlatformEventTriggerHandler(BaseTriggerHandler):
    """Handler для триггеров на события шины платформы."""

    trigger_type: TriggerType = TriggerType.PLATFORM_EVENT

    def __init__(self, base_url: str, *, container: FlowRuntimeContainer) -> None:
        super().__init__(base_url, container=container)
        self._executor: TriggerExecutor = TriggerExecutor()

    @override
    async def register(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        self._log_register(flow_id, trigger.trigger_id)

        try:
            config = PlatformEventTriggerConfig.model_validate(trigger.config)
            await validate_platform_event_trigger_config(config)
        except Exception as exc:
            raise TriggerRegistrationError(
                trigger_type="platform_event",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"invalid PlatformEventTriggerConfig: {exc}",
            ) from exc

        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise TriggerRegistrationError(
                trigger_type="platform_event",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="request context with user and active_company is required",
            )
        company_id = ctx.active_company.company_id

        member = platform_event_trigger_index_member(
            company_id=company_id,
            flow_id=flow_id,
            trigger_id=trigger.trigger_id,
        )
        _ = await self.container.redis_client.sadd(
            platform_event_trigger_index_key(config.event_type),
            member,
        )

        trigger.status = TriggerStatus.ACTIVE
        trigger.last_error = None
        logger.info(
            "Platform event trigger registered: flow_id=%s trigger=%s event_type=%s",
            flow_id,
            trigger.trigger_id,
            config.event_type,
        )
        return trigger

    @override
    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        self._log_unregister(flow_id, trigger.trigger_id)
        raw_event_type = trigger.config.get("event_type")
        if not isinstance(raw_event_type, str) or not raw_event_type.strip():
            logger.warning(
                "Platform event trigger unregister skipped (no event_type): flow_id=%s trigger=%s",
                flow_id,
                trigger.trigger_id,
            )
            return

        ctx = get_context()
        company_id = (
            ctx.active_company.company_id
            if ctx is not None and ctx.active_company is not None
            else None
        )
        if company_id is None:
            logger.warning(
                "Platform event trigger unregister without company context: flow_id=%s trigger=%s",
                flow_id,
                trigger.trigger_id,
            )
            return

        member = platform_event_trigger_index_member(
            company_id=company_id,
            flow_id=flow_id,
            trigger_id=trigger.trigger_id,
        )
        _ = await self.container.redis_client.srem(
            platform_event_trigger_index_key(raw_event_type.strip()),
            member,
        )

    @override
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
    ) -> JsonObject:
        """Ручной прогон триггера (тесты); боевой вход — consumer шины."""
        flow_config = await self.container.flow_repository.get(flow_id)
        if flow_config is None:
            raise TriggerValidationError(f"Flow not found: {flow_id}")
        trigger = flow_config.triggers.get(trigger_id)
        if trigger is None:
            raise TriggerValidationError(f"Trigger not found: {trigger_id}")
        if trigger.type != TriggerType.PLATFORM_EVENT:
            raise TriggerValidationError(f"Trigger {trigger_id} is not platform_event")
        if not trigger.enabled:
            raise TriggerValidationError(f"Trigger {trigger_id} is disabled")

        return await self._executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
        )


async def dispatch_platform_event_triggers(
    *,
    container: FlowRuntimeContainer,
    event: PlatformEvent,
) -> int:
    """
    Запускает подписанные на событие триггеры (из consumer group `flows`).

    Возвращает число успешных запусков TriggerExecutor. Ошибка одного
    триггера логируется и не блокирует остальные.
    """
    members = await container.redis_client.smembers(
        platform_event_trigger_index_key(event.type)
    )
    if not members:
        return 0

    company = await container.company_repository.get(event.company_id)
    if company is None:
        logger.error(
            "platform event trigger dispatch: company not found company_id=%s",
            event.company_id,
        )
        return 0

    actor_user_id = event.meta.actor_user_id
    trigger_user: User | None = None
    if actor_user_id is not None:
        trigger_user = await container.user_repository.get(actor_user_id)
    if trigger_user is None:
        effective_user_id = actor_user_id if actor_user_id is not None else "trigger:platform_event"
        trigger_user = User(
            user_id=effective_user_id,
            name=f"Event:{event.type}",
            companies={event.company_id: ["member"]},
            active_company_id=event.company_id,
        )

    event_payload: JsonObject = {
        "event_id": event.event_id,
        "event_type": event.type,
        "company_id": event.company_id,
        "payload": event.payload,
        "actor_user_id": actor_user_id,
        "occurred_ts": event.meta.ts,
    }

    fired = 0
    previous_context = get_context()
    context = Context(
        user=trigger_user,
        active_company=company,
        user_companies=[company],
        channel="trigger:platform_event",
        trace_id=event.meta.trace_id,
    )
    set_context(context)
    try:
        for member in members:
            parsed = parse_platform_event_trigger_index_member(member)
            if parsed is None:
                logger.warning("platform event trigger index: invalid member %r", member)
                continue
            company_id, flow_id, trigger_id = parsed
            if company_id != event.company_id:
                continue

            flow_config = await container.flow_repository.get(flow_id)
            if flow_config is None:
                logger.warning(
                    "platform event trigger dispatch: flow not found flow_id=%s",
                    flow_id,
                )
                continue
            trigger = flow_config.triggers.get(trigger_id)
            if (
                trigger is None
                or trigger.type != TriggerType.PLATFORM_EVENT
                or not trigger.enabled
            ):
                continue

            try:
                trigger_config = PlatformEventTriggerConfig.model_validate(trigger.config)
            except Exception as exc:
                logger.warning(
                    "platform event trigger dispatch: invalid config flow_id=%s trigger=%s error=%s",
                    flow_id,
                    trigger_id,
                    exc,
                )
                continue
            if trigger_config.event_type != event.type:
                continue
            if not platform_event_matches_filters(trigger_config, event.payload):
                continue

            run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
            executor = TriggerExecutor()
            try:
                _ = await executor.execute(
                    flow_id=flow_id,
                    trigger=trigger,
                    payload=event_payload,
                    user_id=trigger_user.user_id,
                    metadata={
                        "platform_event_id": event.event_id,
                        "platform_event_type": event.type,
                    },
                    task_id=run_id,
                    context_id=run_id,
                )
            except Exception as exc:
                logger.error(
                    "platform event trigger dispatch failed: flow_id=%s trigger=%s error=%s",
                    flow_id,
                    trigger_id,
                    exc,
                    exc_info=True,
                )
                continue
            fired += 1
    finally:
        if previous_context is not None:
            set_context(previous_context)
        else:
            clear_context()

    return fired


__all__ = [
    "PlatformEventTriggerHandler",
    "dispatch_platform_event_triggers",
    "platform_event_matches_filters",
    "platform_event_trigger_index_key",
    "platform_event_trigger_index_member",
    "platform_event_trigger_run_id",
]
