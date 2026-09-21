"""Триггеры flow: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import ValidationError

from apps.flows.realtime.operations import (
    FlowsFlowIdPayload,
    require_company_member,
    require_edit_flow,
    require_view_flow,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models import FlowConfig, TriggerConfig
from apps.flows.src.models.channel_config import default_output_actions_for_trigger
from apps.flows.src.models.enums import TriggerType
from apps.flows.src.models.trigger_config import (
    PlatformEventTriggerConfig,
    TriggerCreatePayload,
    TriggerDeletedResponse,
    TriggerFlowIdPayload,
    TriggerResponse,
    TriggerTestRequest,
    TriggerTestResponse,
    TriggerUpdatePayload,
    TriggerVerifyPayload,
    TriggerVerifyResponse,
)
from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
from apps.flows.src.triggers.handlers.platform_event import (
    validate_platform_event_trigger_config,
)
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows.src.triggers.registry import (
    TriggerReregisterDisabledError,
    TriggerReregisterUnsupportedError,
)
from apps.flows.src.triggers.trigger_type_contract import (
    default_post_flow_output_enabled,
    effective_output_actions_for_trigger,
)
from apps.flows.src.triggers.verify_draft import verify_trigger_draft as run_verify
from core.errors.boundary import PlatformNotFoundError
from core.events import PlatformEventCatalogResponse, load_platform_event_catalog
from core.logging import get_logger
from core.models.identity_models import User
from core.pagination import ListResponse
from core.types import JsonObject
from core.variables.resolver import VariableResolutionError
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_invalid,
    raise_not_found,
)

logger = get_logger(__name__)

_SENSITIVE_TRIGGER_CONFIG_KEYS = frozenset(
    {"bot_token", "secret_token", "imap_password", "password"},
)
_REDACTED_CONFIG_SECRET = "(redacted)"


def _public_trigger_config(config: JsonObject) -> JsonObject:
    out: JsonObject = {}
    for key, value in config.items():
        if key.startswith("_"):
            continue
        if key in _SENSITIVE_TRIGGER_CONFIG_KEYS and value not in (None, ""):
            out[key] = _REDACTED_CONFIG_SECRET
        else:
            out[key] = value
    return out


def _trigger_response(trigger: TriggerConfig) -> TriggerResponse:
    return TriggerResponse(
        trigger_id=trigger.trigger_id,
        name=trigger.name,
        type=trigger.type,
        enabled=trigger.enabled,
        config=_public_trigger_config(trigger.config),
        output_mapping=trigger.output_mapping,
        input_mapping=trigger.input_mapping,
        output_actions=effective_output_actions_for_trigger(trigger),
        post_flow_output_enabled=trigger.post_flow_output_enabled,
        branch_id=trigger.branch_id,
        webhook_url=trigger.webhook_url,
        status=trigger.status,
        last_error=trigger.last_error,
    )


async def _flow_for_view(container: FlowContainer, flow_id: str) -> FlowConfig:
    _ = await require_view_flow(container, flow_id)
    flow_config = await container.flow_repository.get(flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow not found: {flow_id}"))
    return flow_config


async def _flow_for_edit(container: FlowContainer, flow_id: str) -> FlowConfig:
    _ = await require_edit_flow(container, flow_id)
    flow_config = await container.flow_repository.get(flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow not found: {flow_id}"))
    return flow_config


async def _validate_platform_event_config(config: JsonObject) -> None:
    try:
        validated = PlatformEventTriggerConfig.model_validate(config)
        await validate_platform_event_trigger_config(validated)
    except ValidationError as exc:
        raise_invalid(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_triggers_list(
    payload: FlowsFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[TriggerResponse]:
    _ = user
    flow_config = await _flow_for_view(container, payload.flow_id)
    return ListResponse(
        items=[_trigger_response(trigger) for trigger in flow_config.triggers.values()]
    )


async def op_flows_triggers_item(
    payload: TriggerFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerResponse:
    _ = user
    flow_config = await _flow_for_view(container, payload.flow_id)
    trigger = flow_config.triggers.get(payload.trigger_id)
    if trigger is None:
        raise_not_found(LookupError(f"Trigger not found: {payload.trigger_id}"))
    return _trigger_response(trigger)


async def op_flows_triggers_verify(
    payload: TriggerVerifyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerVerifyResponse:
    _ = user
    scope = await require_edit_flow(container, payload.flow_id)
    flow_config = await container.flow_repository.get(payload.flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow not found: {payload.flow_id}"))

    cfg: JsonObject = dict(payload.config)
    if payload.type == TriggerType.TELEGRAM:
        raw_token = cfg.get("bot_token")
        if isinstance(raw_token, str) and raw_token == _REDACTED_CONFIG_SECRET:
            tid = payload.trigger_id
            if isinstance(tid, str) and tid.strip() != "":
                stored = flow_config.triggers.get(tid)
                if stored is not None:
                    stored_token = stored.config.get("bot_token")
                    if stored_token is not None and str(stored_token).strip() != "":
                        cfg["bot_token"] = stored_token
            raw_token = cfg.get("bot_token")
        if isinstance(raw_token, str) and raw_token == _REDACTED_CONFIG_SECRET:
            return TriggerVerifyResponse(
                ok=False,
                metadata={},
                error_code="bot_token_required",
                error_message=(
                    "В запросе подставлена заглушка (redacted) из ответа API: укажите токен "
                    "вручную (@var:имя_переменной) или откройте проверку из сохранённого триггера с trigger_id."
                ),
            )
        if isinstance(raw_token, str) and raw_token.startswith("@var:"):
            try:
                cfg["bot_token"] = await resolve_at_var_for_flow(
                    container.flow_factory,
                    payload.flow_id,
                    raw_token,
                    branch_id=payload.branch_id,
                )
            except VariableResolutionError as exc:
                return TriggerVerifyResponse(
                    ok=False,
                    metadata={},
                    error_code="variable_not_found",
                    error_message=str(exc),
                )

    ok, metadata, err_code, err_msg = await run_verify(
        payload.type,
        cfg,
        payload.flow_id,
        payload.trigger_id,
        mail_service=container.mail_service,
        company_id=scope.company_id,
    )
    return TriggerVerifyResponse(
        ok=ok,
        metadata=metadata,
        error_code=err_code,
        error_message=err_msg,
    )


async def op_flows_triggers_create(
    payload: TriggerCreatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerResponse:
    _ = user
    flow_config = await _flow_for_edit(container, payload.flow_id)
    if payload.trigger_id in flow_config.triggers:
        raise_conflict(ValueError(f"Trigger already exists: {payload.trigger_id}"))

    if payload.type == TriggerType.PLATFORM_EVENT:
        await _validate_platform_event_config(payload.config)

    post_enabled = payload.post_flow_output_enabled
    if post_enabled is None:
        post_enabled = default_post_flow_output_enabled(payload.type)
    if post_enabled and len(payload.output_actions) == 0:
        out_actions = default_output_actions_for_trigger(payload.trigger_id, payload.type)
    else:
        out_actions = list(payload.output_actions)

    trigger = TriggerConfig(
        trigger_id=payload.trigger_id,
        name=payload.name,
        type=payload.type,
        enabled=payload.enabled,
        config=payload.config,
        output_mapping=payload.output_mapping,
        input_mapping=payload.input_mapping,
        output_actions=out_actions,
        post_flow_output_enabled=post_enabled,
        branch_id=payload.branch_id,
    )
    old_config = flow_config.model_copy(deep=True)
    flow_config.triggers[payload.trigger_id] = trigger
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=payload.flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    _ = await container.flow_repository.set(flow_config)
    updated_trigger = flow_config.triggers.get(payload.trigger_id)
    if updated_trigger is None:
        raise RuntimeError(f"Trigger '{payload.trigger_id}' missing after sync")
    logger.info("flows.trigger.created.flow_id.trigger", flow_id=payload.flow_id, trigger=payload.trigger_id)
    return _trigger_response(updated_trigger)


async def op_flows_triggers_update(
    payload: TriggerUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerResponse:
    _ = user
    old_config = await _flow_for_edit(container, payload.flow_id)
    trigger = old_config.triggers.get(payload.trigger_id)
    if trigger is None:
        raise_not_found(LookupError(f"Trigger not found: {payload.trigger_id}"))

    flow_config = old_config.model_copy(deep=True)
    trigger = flow_config.triggers[payload.trigger_id]
    if payload.name is not None:
        trigger.name = payload.name
    if payload.enabled is not None:
        trigger.enabled = payload.enabled
    if payload.config is not None:
        trigger.config = payload.config
    if payload.output_mapping is not None:
        trigger.output_mapping = payload.output_mapping
    if payload.input_mapping is not None:
        trigger.input_mapping = payload.input_mapping
    if payload.output_actions is not None:
        trigger.output_actions = payload.output_actions
    if payload.post_flow_output_enabled is not None:
        trigger.post_flow_output_enabled = payload.post_flow_output_enabled
    if payload.branch_id is not None:
        trigger.branch_id = payload.branch_id

    current = flow_config.triggers[payload.trigger_id]
    flow_config.triggers[payload.trigger_id] = TriggerConfig.model_validate(
        current.model_dump()
    )
    if flow_config.triggers[payload.trigger_id].type == TriggerType.PLATFORM_EVENT:
        await _validate_platform_event_config(
            flow_config.triggers[payload.trigger_id].config
        )

    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=payload.flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    _ = await container.flow_repository.set(flow_config)
    updated_trigger = flow_config.triggers.get(payload.trigger_id)
    if updated_trigger is None:
        raise RuntimeError(f"Trigger '{payload.trigger_id}' missing after sync")
    logger.info("flows.trigger.updated.flow_id.trigger", flow_id=payload.flow_id, trigger=payload.trigger_id)
    return _trigger_response(updated_trigger)


async def op_flows_triggers_reregister(
    payload: TriggerFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerResponse:
    _ = user
    old_config = await _flow_for_edit(container, payload.flow_id)
    if payload.trigger_id not in old_config.triggers:
        raise_not_found(LookupError(f"Trigger not found: {payload.trigger_id}"))

    flow_config = old_config.model_copy(deep=True)
    trigger = flow_config.triggers[payload.trigger_id]
    try:
        updated = await container.trigger_registry.reregister_trigger(
            payload.flow_id, trigger
        )
    except TriggerReregisterDisabledError:
        raise_invalid(ValueError("enable the trigger before reregistering hooks"))
    except TriggerReregisterUnsupportedError as exc:
        tstr = exc.trigger_type.value
        raise_conflict(
            ValueError(
                f"external hook reregistration for type {tstr} is not implemented. only Telegram (setWebhook) is supported"
            )
        )

    flow_config.triggers[payload.trigger_id] = updated
    _ = await container.flow_repository.set(flow_config)
    out = flow_config.triggers[payload.trigger_id]
    logger.info("flows.trigger.reregistered.flow_id.trigger", flow_id=payload.flow_id, trigger=payload.trigger_id)
    return _trigger_response(out)


async def op_flows_triggers_remove(
    payload: TriggerFlowIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerDeletedResponse:
    _ = user
    old_config = await _flow_for_edit(container, payload.flow_id)
    if payload.trigger_id not in old_config.triggers:
        raise_not_found(LookupError(f"Trigger not found: {payload.trigger_id}"))

    flow_config = old_config.model_copy(deep=True)
    del flow_config.triggers[payload.trigger_id]
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=payload.flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    _ = await container.flow_repository.set(flow_config)
    logger.info("flows.trigger.deleted.flow_id.trigger", flow_id=payload.flow_id, trigger=payload.trigger_id)
    return TriggerDeletedResponse(status="deleted", trigger_id=payload.trigger_id)


async def op_flows_triggers_test(
    payload: TriggerTestRequest,
    *,
    user: User,
    container: FlowContainer,
) -> TriggerTestResponse:
    _ = user
    flow_config = await _flow_for_edit(container, payload.flow_id)
    trigger = flow_config.triggers.get(payload.trigger_id)
    if trigger is None:
        raise_not_found(LookupError(f"Trigger not found: {payload.trigger_id}"))

    mapper = InputMapper()
    mapping = {**dict(trigger.input_mapping), **dict(trigger.output_mapping)}
    mapped_data = mapper.map(payload.trigger_id, payload.payload, mapping)
    return TriggerTestResponse(
        status="ok",
        trigger_id=payload.trigger_id,
        trigger_type=trigger.type.value,
        input_payload=payload.payload,
        mapped_data=mapped_data,
    )


async def op_flows_platform_events_catalog(
    payload: EmptyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> PlatformEventCatalogResponse:
    _ = user
    _ = payload
    _ = await require_company_member(container)
    entries = await load_platform_event_catalog()
    return PlatformEventCatalogResponse(items=entries)
