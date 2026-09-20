"""REST-зеркало триггеров + inbound webhook Telegram/HTTP."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from apps.flows.realtime.operations import FlowsFlowIdPayload
from apps.flows.realtime.trigger_operations import (
    op_flows_triggers_create,
    op_flows_triggers_item,
    op_flows_triggers_list,
    op_flows_triggers_remove,
    op_flows_triggers_reregister,
    op_flows_triggers_test,
    op_flows_triggers_update,
    op_flows_triggers_verify,
)
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import TelegramUpdate, TriggerType
from apps.flows.src.models.trigger_config import (
    TriggerCreatePayload,
    TriggerCreateRequest,
    TriggerDeletedResponse,
    TriggerFlowIdPayload,
    TriggerResponse,
    TriggerTestRequest,
    TriggerTestResponse,
    TriggerUpdatePayload,
    TriggerUpdateRequest,
    TriggerVerifyPayload,
    TriggerVerifyRequest,
    TriggerVerifyResponse,
)
from apps.flows.src.triggers import TriggerValidationError
from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.handlers.webhook import WebhookTriggerHandler
from apps.flows.src.triggers.webhook_inbound import (
    DEFAULT_WEBHOOK_SECRET_HEADER,
    build_webhook_trigger_payload,
    check_webhook_rate_limit,
    client_ip_allowed,
    parse_webhook_json_body,
    webhook_secret_from_request,
)
from core.context import get_context, require_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.pagination import ListResponse
from core.types import JsonObject
from core.variables.resolver import VariableResolutionError
from core.websocket import WsCommandError

logger = get_logger(__name__)


def _webhook_secret_header_from_config(config: JsonObject) -> str:
    raw = config.get("secret_header")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_WEBHOOK_SECRET_HEADER
    return str(raw).strip()


async def _resolve_company_from_flow_storage_identifier(
    container: ContainerDep,
    company_identifier: str,
) -> Company:
    """
    Восстанавливает полную Company для публичного webhook-контекста.

    Flow keys используют `active_company.subdomain or company_id`, поэтому
    company_identifier из unscoped flow lookup может быть как company_id, так
    и subdomain. В контекст нужно класть persisted Company целиком: metadata
    содержит AI provider overrides и другие per-company настройки.
    """
    company = await container.company_repository.get(company_identifier)
    if company is not None:
        return company

    company_id = await container.subdomain_repository.get_company_id(company_identifier)
    if company_id:
        company = await container.company_repository.get(company_id)
        if company is not None:
            return company

    raise RuntimeError(
        f"Flow storage company identifier has no persisted Company: {company_identifier!r}"
    )

router = APIRouter(tags=["triggers"])


@router.get("/flows/{flow_id}/triggers", response_model=ListResponse[TriggerResponse])
async def list_triggers(flow_id: str, container: ContainerDep) -> ListResponse[TriggerResponse]:
    return await op_flows_triggers_list(
        FlowsFlowIdPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.get("/flows/{flow_id}/triggers/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(flow_id: str, trigger_id: str, container: ContainerDep) -> TriggerResponse:
    return await op_flows_triggers_item(
        TriggerFlowIdPayload(flow_id=flow_id, trigger_id=trigger_id),
        user=require_context().user,
        container=container,
    )


@router.post("/flows/{flow_id}/triggers/verify", response_model=TriggerVerifyResponse)
async def verify_trigger_draft(
    flow_id: str, request: TriggerVerifyRequest, container: ContainerDep
) -> TriggerVerifyResponse:
    return await op_flows_triggers_verify(
        TriggerVerifyPayload.model_validate({"flow_id": flow_id, **request.model_dump()}),
        user=require_context().user,
        container=container,
    )


@router.post("/flows/{flow_id}/triggers", response_model=TriggerResponse)
async def create_trigger(
    flow_id: str, request: TriggerCreateRequest, container: ContainerDep
) -> TriggerResponse:
    return await op_flows_triggers_create(
        TriggerCreatePayload.model_validate({"flow_id": flow_id, **request.model_dump()}),
        user=require_context().user,
        container=container,
    )


@router.put("/flows/{flow_id}/triggers/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    flow_id: str,
    trigger_id: str,
    request: TriggerUpdateRequest,
    container: ContainerDep,
) -> TriggerResponse:
    return await op_flows_triggers_update(
        TriggerUpdatePayload.model_validate(
            {"flow_id": flow_id, "trigger_id": trigger_id, **request.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/flows/{flow_id}/triggers/{trigger_id}/reregister",
    response_model=TriggerResponse,
)
async def reregister_flow_trigger(
    flow_id: str, trigger_id: str, container: ContainerDep
) -> TriggerResponse:
    return await op_flows_triggers_reregister(
        TriggerFlowIdPayload(flow_id=flow_id, trigger_id=trigger_id),
        user=require_context().user,
        container=container,
    )


@router.delete("/flows/{flow_id}/triggers/{trigger_id}", response_model=TriggerDeletedResponse)
async def delete_trigger(
    flow_id: str, trigger_id: str, container: ContainerDep
) -> TriggerDeletedResponse:
    return await op_flows_triggers_remove(
        TriggerFlowIdPayload(flow_id=flow_id, trigger_id=trigger_id),
        user=require_context().user,
        container=container,
    )


@router.post("/flows/{flow_id}/triggers/{trigger_id}/test", response_model=TriggerTestResponse)
async def test_trigger(
    flow_id: str,
    trigger_id: str,
    payload: TriggerTestRequest,
    container: ContainerDep,
) -> TriggerTestResponse:
    if payload.flow_id != flow_id or payload.trigger_id != trigger_id:
        raise WsCommandError(
            "ws_invalid_payload",
            "flow_id or trigger_id in path must match payload",
        )
    return await op_flows_triggers_test(
        payload,
        user=require_context().user,
        container=container,
    )


# Webhook-endpoints

@router.post("/triggers/telegram/{flow_id}/{trigger_id}")
async def telegram_webhook(
    flow_id: str,
    trigger_id: str,
    request: Request,
    container: ContainerDep,
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """
    Webhook endpoint для Telegram Bot API.

    Telegram посылает Update сюда после setWebhook.
    """
    ctx = get_context()
    if ctx and ctx.active_company:
        flow_config = await container.flow_repository.get(flow_id)
    else:
        unscoped = await container.flow_repository.get_latest_by_flow_id_unscoped(flow_id)
        if not unscoped:
            flow_config = None
        else:
            flow_config, company_identifier = unscoped
            company = await _resolve_company_from_flow_storage_identifier(
                container,
                company_identifier,
            )
            inbound_user = User(
                user_id="telegram_inbound",
                name="Telegram Inbound",
                groups=["guest"],
            )
            _ = set_context(
                Context(
                    user=inbound_user,
                    host=ctx.host if ctx else "",
                    session_id=ctx.session_id if ctx and ctx.session_id else "telegram_inbound",
                    channel="triggers/telegram",
                    language=ctx.language if ctx else Language.RU,
                    active_company=company,
                    user_companies=[company],
                    trace_id=ctx.trace_id if ctx else None,
                    metadata={**(ctx.metadata if ctx else {}), "inbound": "telegram"},
                )
            )

    if not flow_config:
        logger.warning(f"Telegram webhook: flow not found: {flow_id}")
        raise HTTPException(status_code=404, detail="Flow not found")

    trigger = flow_config.triggers.get(trigger_id)

    if not trigger:
        logger.warning(f"Telegram webhook: trigger not found: {trigger_id}")
        raise HTTPException(status_code=404, detail="Trigger not found")

    if trigger.type != TriggerType.TELEGRAM:
        raise HTTPException(status_code=400, detail="Not a Telegram trigger")

    telegram_handler = TelegramTriggerHandler(
        base_url="",
        container=as_flow_runtime_container(container),
    )

    if not trigger.config.get("_secret_token"):
        logger.warning(
            "Telegram webhook: trigger %s has no _secret_token (register or reregister)",
            trigger_id,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Telegram webhook secret is not configured for this trigger; "
                "save the flow or POST .../reregister."
            ),
        )
    if not x_telegram_bot_api_secret_token:
        raise HTTPException(
            status_code=403,
            detail="Missing X-Telegram-Bot-Api-Secret-Token",
        )
    if not telegram_handler.verify_secret_token(trigger, x_telegram_bot_api_secret_token):
        logger.warning("Telegram webhook: invalid secret token: %s", trigger_id)
        raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        update = TelegramUpdate.model_validate_json(await request.body())
    except ValidationError as e:
        logger.error(f"Telegram webhook: failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON") from e
    payload = update.to_payload()

    logger.info(
        "Telegram webhook received: flow_id=%s, trigger=%s, update_id=%s",
        flow_id,
        trigger_id,
        update.update_id,
    )

    # Обрабатываем
    try:
        result = await telegram_handler.handle(flow_id, trigger_id, payload)
        task_id = result["task_id"]
        if not isinstance(task_id, str):
            raise RuntimeError("Telegram trigger result.task_id must be a string")
        return {"status": "ok", "task_id": task_id}
    except TriggerValidationError as e:
        logger.warning(f"Telegram webhook validation error: {e}")
        return {"status": "skipped", "reason": str(e)}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/triggers/webhook/{flow_id}/{trigger_id}")
async def generic_webhook(
    flow_id: str,
    trigger_id: str,
    request: Request,
    container: ContainerDep,
) -> JSONResponse:
    """
    Generic webhook endpoint для внешних сервисов.

    Payload envelope: {body, headers, query}. Запуск через TriggerExecutor.
    """
    ctx = get_context()
    if ctx and ctx.active_company:
        flow_config = await container.flow_repository.get(flow_id)
    else:
        unscoped = await container.flow_repository.get_latest_by_flow_id_unscoped(flow_id)
        if not unscoped:
            flow_config = None
        else:
            flow_config, company_identifier = unscoped
            company = await _resolve_company_from_flow_storage_identifier(
                container,
                company_identifier,
            )
            inbound_user = User(
                user_id="webhook_inbound",
                name="Webhook Inbound",
                groups=["guest"],
            )
            _ = set_context(
                Context(
                    user=inbound_user,
                    host=ctx.host if ctx else "",
                    session_id=ctx.session_id if ctx and ctx.session_id else "webhook_inbound",
                    channel="triggers/webhook",
                    language=ctx.language if ctx else Language.RU,
                    active_company=company,
                    user_companies=[company],
                    trace_id=ctx.trace_id if ctx else None,
                    metadata={**(ctx.metadata if ctx else {}), "inbound": "webhook"},
                )
            )

    if not flow_config:
        raise HTTPException(status_code=404, detail="Flow not found")

    trigger = flow_config.triggers.get(trigger_id)

    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if trigger.type != TriggerType.WEBHOOK:
        raise HTTPException(status_code=400, detail="Not a webhook trigger")

    if not trigger.enabled:
        raise HTTPException(status_code=400, detail="Trigger is disabled")

    client = request.client
    client_host = client.host if client else "unknown"
    if not check_webhook_rate_limit(flow_id, trigger_id, client_host):
        raise HTTPException(status_code=429, detail="Too many requests")
    if not client_ip_allowed(client_host, trigger.config.get("allowed_ips")):
        raise HTTPException(status_code=403, detail="Client IP not allowed")

    secret_header = _webhook_secret_header_from_config(trigger.config)
    raw_secret = trigger.config.get("secret_token")
    if raw_secret is not None and str(raw_secret).strip() != "":
        try:
            expected = await resolve_at_var_for_flow(
                container.flow_factory,
                flow_id,
                str(raw_secret),
                branch_id=trigger.branch_id,
            )
        except VariableResolutionError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        received = webhook_secret_from_request(request, secret_header)
        if not received:
            raise HTTPException(status_code=403, detail="Secret required")
        if not secrets.compare_digest(expected, received):
            raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        body = await parse_webhook_json_body(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e

    payload = build_webhook_trigger_payload(request, body)
    body_obj = payload.get("body")
    body_keys: list[str] = []
    if isinstance(body_obj, dict):
        body_keys = list(body_obj.keys())
        if len(body_keys) > 24:
            body_keys = body_keys[:24] + ["..."]
    logger.info(
        "Webhook received: flow_id=%s, trigger=%s, body_key_count=%s, top_keys=%s",
        flow_id,
        trigger_id,
        len(body_keys),
        body_keys,
    )

    webhook_handler = WebhookTriggerHandler(
        base_url="",
        container=as_flow_runtime_container(container),
    )
    try:
        result = await webhook_handler.handle(flow_id, trigger_id, payload)
    except Exception as e:
        logger.error(f"Webhook trigger error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

    task_id = result.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise HTTPException(status_code=500, detail="Webhook trigger did not return task_id")
    context_id = result.get("context_id")
    if not isinstance(context_id, str) or not context_id.strip():
        raise HTTPException(status_code=500, detail="Webhook trigger did not return context_id")
    session_id = result.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise HTTPException(status_code=500, detail="Webhook trigger did not return session_id")

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "task_id": task_id,
            "context_id": context_id,
            "session_id": session_id,
        },
    )
