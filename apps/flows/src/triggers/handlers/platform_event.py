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
from apps.flows.src.services.execution_identity import resolve_execution_context
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from core.authz.ids import is_openfga_user_subject_id
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.context import User, clear_context, get_context, set_context
from core.context.job_context import build_job_context
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


async def _event_actor_user(
    container: FlowRuntimeContainer,
    actor_user_id: str,
) -> User:
    """Актор из meta: только существующий platform user с FGA-безопасным id."""
    if not is_openfga_user_subject_id(actor_user_id):
        raise ValueError(
            f"platform event actor_user_id must not contain ':': {actor_user_id!r}"
        )
    actor = await container.user_repository.get(actor_user_id)
    if actor is None:
        raise ValueError(
            f"platform event actor_user_id={actor_user_id!r} is not a platform user"
        )
    return actor


async def _flow_owner_user(
    container: FlowRuntimeContainer,
    *,
    company_id: str,
    flow_id: str,
) -> User:
    """Владелец flow из OpenFGA — identity исполнения, когда у события нет актора."""
    subjects = await container.authz_service.list_users(
        AuthzObject.flow(flow_id, company_id=company_id),
        AuthzRelation.OWNER,
    )
    owner_ids = sorted(
        subject.value
        for subject in subjects
        if subject.kind is AuthzSubjectKind.USER and subject.value
    )
    if not owner_ids:
        raise ValueError(
            f"platform event trigger dispatch: flow {flow_id} has no owner"
        )
    owner = await container.user_repository.get(owner_ids[0])
    if owner is None:
        raise ValueError(
            f"platform event trigger dispatch: flow owner {owner_ids[0]} not found"
        )
    return owner


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
            "flows.platform.event.trigger.registered.flow_id",
            flow_id=flow_id,
            trigger=trigger.trigger_id,
            event_type=config.event_type,
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
            logger.warning("flows.platform.event.trigger.unregister.skipped", flow_id=flow_id, trigger=trigger.trigger_id)
            return

        ctx = get_context()
        company_id = (
            ctx.active_company.company_id
            if ctx is not None and ctx.active_company is not None
            else None
        )
        if company_id is None:
            logger.warning("flows.platform.event.trigger.unregister.without", flow_id=flow_id, trigger=trigger.trigger_id)
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
        logger.error("flows.platform.event.trigger.dispatch.company", company_id=event.company_id)
        return 0

    actor_user_id = event.meta.actor_user_id
    event_actor: User | None = None
    if actor_user_id is not None:
        try:
            event_actor = await _event_actor_user(container, actor_user_id)
        except ValueError as exc:
            logger.error("flows.platform.event.trigger.dispatch.invalid", company_id=event.company_id, error=exc)
            return 0

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
    try:
        for member in members:
            parsed = parse_platform_event_trigger_index_member(member)
            if parsed is None:
                logger.warning("flows.platform.event.trigger.index.invalid", member=member)
                continue
            company_id, flow_id, trigger_id = parsed
            if company_id != event.company_id:
                continue

            index_key = platform_event_trigger_index_key(event.type)
            flow_config = await container.flow_repository.get(flow_id)
            if flow_config is None:
                logger.warning("flows.platform.event.trigger.dispatch.flow", flow_id=flow_id)
                _ = await container.redis_client.srem(index_key, member)
                continue
            trigger = flow_config.triggers.get(trigger_id)
            if trigger is None:
                _ = await container.redis_client.srem(index_key, member)
                continue
            if trigger.type != TriggerType.PLATFORM_EVENT or not trigger.enabled:
                continue

            try:
                trigger_config = PlatformEventTriggerConfig.model_validate(trigger.config)
            except Exception as exc:
                logger.warning(
                    "flows.platform.event.trigger.dispatch.invalid",
                    flow_id=flow_id,
                    trigger=trigger_id,
                    error=exc,
                )
                continue
            if trigger_config.event_type != event.type:
                continue
            if not platform_event_matches_filters(trigger_config, event.payload):
                continue

            run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
            session_id = f"{flow_id}:{run_id}"
            existing_state = await container.workflow_runtime.get_state(session_id)
            if existing_state is not None:
                # Deterministic run_id: at-least-once redelivery must not start a second run
                # (A2A terminal event identity would collide).
                fired += 1
                continue
            try:
                initiator = event_actor
                if initiator is None:
                    initiator = await _flow_owner_user(
                        container,
                        company_id=company_id,
                        flow_id=flow_id,
                    )
                event_trace_id = event.meta.trace_id
                initiator_context = build_job_context(
                    company=company,
                    user=initiator,
                    host="",
                    trace_id="" if event_trace_id is None else event_trace_id,
                    session_id=session_id,
                    channel="trigger:platform_event",
                )
                initiator_context.flow_id = flow_id
                execution = await resolve_execution_context(
                    container,
                    flow_config=flow_config,
                    initiator_context=initiator_context,
                )
                _ = set_context(execution.context)
                _ = await TriggerExecutor().execute(
                    flow_id=flow_id,
                    trigger=trigger,
                    payload=event_payload,
                    user_id=execution.context.user.user_id,
                    metadata={
                        "platform_event_id": event.event_id,
                        "platform_event_type": event.type,
                    },
                    task_id=run_id,
                    context_id=run_id,
                )
            except Exception as exc:
                logger.error(
                    "flows.platform.event.trigger.dispatch.failed",
                    flow_id=flow_id,
                    trigger=trigger_id,
                    error=exc,
                    exc_info=True,
                )
                continue
            fired += 1
    finally:
        if previous_context is not None:
            _ = set_context(previous_context)
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
