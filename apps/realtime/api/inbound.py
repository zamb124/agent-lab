"""Inbound Centrifugo RPC и ingest PlatformEvent."""

from __future__ import annotations

from fastapi import APIRouter, Request

from apps.realtime.di import Di
from core.context import reset_context, set_context
from core.events.contract import EventDelivery, PlatformEvent
from core.logging import get_log_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.realtime.command_owners import is_command_event_type, owner_service_for_event_type
from core.realtime.models import (
    CentrifugoRpcInbound,
    CentrifugoRpcResponse,
    CentrifugoRpcResult,
)
from core.types import JsonObject
from core.utils.tokens import get_token_service
from core.websocket import WsCommandError, raise_invalid

router = APIRouter()

_RPC_METHOD = "platform.event"


@router.post("/internal/centrifugo/inbound", response_model=CentrifugoRpcResponse)
async def centrifugo_inbound(
    inbound: CentrifugoRpcInbound,
    request: Request,
    di: Di,
) -> CentrifugoRpcResponse:
    if not inbound.user:
        raise WsCommandError("ws_invalid_payload", "Centrifugo inbound user is required", error_code="ws_invalid_payload")
    if inbound.method != _RPC_METHOD:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Centrifugo RPC method must be {_RPC_METHOD!r}, got {inbound.method!r}",
            error_code="ws_invalid_payload",
        )
    if inbound.data is None:
        raise WsCommandError("ws_invalid_payload", "Centrifugo RPC data is required", error_code="ws_invalid_payload")
    parsed = PlatformEvent.model_validate(inbound.data)
    if not is_command_event_type(parsed.type):
        raise WsCommandError(
            "ws_invalid_payload",
            "Centrifugo inbound accepts only *_requested PlatformEvent",
            error_code="ws_invalid_payload",
        )
    try:
        _ = owner_service_for_event_type(parsed.type)
    except ValueError as exc:
        raise_invalid(exc)
    company_from_meta = _company_id_from_connection_meta(inbound.meta)
    if company_from_meta is not None and parsed.company_id != company_from_meta:
        raise WsCommandError(
            "ws_invalid_payload",
            f"event.company_id {parsed.company_id!r} does not match connection meta {company_from_meta!r}",
            error_code="ws_invalid_payload",
        )
    delivery = parsed.delivery
    if delivery is None:
        delivery = EventDelivery(user_ids=[inbound.user])
    event = parsed.model_copy(
        update={
            "delivery": delivery,
            "meta": parsed.meta.model_copy(
                update={"actor_user_id": inbound.user, "source": "ws"}
            ),
        }
    )
    actor_context = await _actor_context(
        request,
        user_id=inbound.user,
        company_id=event.company_id,
        namespace=event.meta.namespace,
    )
    context_token = set_context(actor_context)
    try:
        stored = await di.bus_service.ingest(event)
    finally:
        reset_context(context_token)
    return CentrifugoRpcResponse(
        result=CentrifugoRpcResult(
            data={"accepted": True, "event_id": stored.event_id},
        )
    )


@router.post("/internal/events", response_model=PlatformEvent)
async def ingest_platform_event(event: PlatformEvent, di: Di) -> PlatformEvent:
    return await di.bus_service.ingest(event)


async def _actor_context(
    request: Request,
    *,
    user_id: str,
    company_id: str,
    namespace: str,
) -> Context:
    user = await User.get(user_id)
    if user is None:
        raise WsCommandError("unauthorized", f"inbound user {user_id} not found", error_code="unauthorized")
    company = await Company.get(company_id)
    if company is None:
        raise WsCommandError("ws_invalid_payload", f"company {company_id} not found", error_code="ws_invalid_payload")
    auth_token = get_token_service().create_token(user_id, company_id=company_id)
    trace_raw = get_log_context().get("trace_id")
    trace_id = trace_raw if isinstance(trace_raw, str) and trace_raw else None
    host = request.headers.get("host")
    if host is None or host == "":
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    active_namespace = namespace.strip()
    if active_namespace == "":
        raise WsCommandError("ws_invalid_payload", "event.meta.namespace is required", error_code="ws_invalid_payload")
    return Context(
        user=user,
        active_company=company,
        user_companies=[company],
        auth_token=auth_token,
        channel="ws",
        host=host,
        trace_id=trace_id,
        active_namespace=active_namespace,
    )


def _company_id_from_connection_meta(meta: JsonObject | None) -> str | None:
    if meta is None:
        return None
    company_id = meta.get("company_id")
    if company_id is None:
        return None
    if not isinstance(company_id, str):
        raise WsCommandError("ws_invalid_payload", "connection meta.company_id must be string", error_code="ws_invalid_payload")
    if company_id == "":
        return None
    return company_id
