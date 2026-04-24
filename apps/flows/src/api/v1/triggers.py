"""
API endpoints для триггеров агентов.

CRUD для триггеров + webhook endpoints для приема входящих событий.
"""

import json
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import TriggerConfig, TriggerStatus, TriggerType
from apps.flows.src.models.channel_config import (
    OutputAction,
    default_output_actions_for_trigger_type,
)
from apps.flows.src.triggers import TriggerRegistry, TriggerValidationError
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.webhook_inbound import check_webhook_rate_limit, client_ip_allowed
from core.context import get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context, Language
from core.models.identity_models import Company, User

logger = get_logger(__name__)

_SENSITIVE_TRIGGER_CONFIG_KEYS = frozenset(
    {"bot_token", "secret_token", "imap_password", "password"},
)


def _trigger_response_output_actions(trigger: TriggerConfig) -> List[OutputAction]:
    if trigger.output_actions:
        return trigger.output_actions
    return default_output_actions_for_trigger_type(trigger.type)


def _public_trigger_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Убирает служебные ключи и скрывает секреты в ответах API."""
    out: Dict[str, Any] = {}
    for k, v in config.items():
        if k.startswith("_"):
            continue
        if k in _SENSITIVE_TRIGGER_CONFIG_KEYS and v not in (None, ""):
            out[k] = "(redacted)"
        else:
            out[k] = v
    return out


async def _resolve_config_secret_value(container: Any, raw: str) -> str:
    """Резолвит @var:key для secret_token в конфиге webhook."""
    if not raw:
        return ""
    s = str(raw)
    if s.startswith("@var:"):
        var_key = s[5:]
        value = await container.variables_service.get_var(var_key)
        if value is None:
            raise HTTPException(
                status_code=500,
                detail=f"Variable not found: {var_key}",
            )
        return str(value)
    return s


def _webhook_secret_from_request(request: Request) -> Optional[str]:
    for header in ("X-Trigger-Secret", "X-Webhook-Secret"):
        v = request.headers.get(header)
        if v:
            return v
    return request.query_params.get("secret")

router = APIRouter(tags=["triggers"])


# Request/Response models

class TriggerCreateRequest(BaseModel):
    """Запрос на создание триггера."""
    trigger_id: str = Field(..., description="ID триггера")
    name: str = Field(..., description="Название")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен")
    config: Dict[str, Any] = Field(default_factory=dict, description="Конфигурация")
    output_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг payload -> state (state.path -> payload.path)",
    )
    input_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="DEPRECATED: используйте output_mapping",
    )
    output_actions: List[OutputAction] = Field(
        default_factory=list,
        description="Действия отправки ответа в канал после агента",
    )


class TriggerUpdateRequest(BaseModel):
    """Запрос на обновление триггера."""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    output_mapping: Optional[Dict[str, str]] = None
    input_mapping: Optional[Dict[str, str]] = None
    output_actions: Optional[List[OutputAction]] = None


class TriggerResponse(BaseModel):
    """Ответ с данными триггера."""
    trigger_id: str
    name: str
    type: TriggerType
    enabled: bool
    config: Dict[str, Any]
    output_mapping: Dict[str, str]
    input_mapping: Dict[str, str]
    output_actions: List[OutputAction]
    webhook_url: Optional[str] = None
    status: TriggerStatus
    last_error: Optional[str] = None


# CRUD endpoints

@router.get("/flows/{flow_id}/triggers")
async def list_triggers(flow_id: str, container: ContainerDep) -> list[TriggerResponse]:
    """Получить список триггеров агента."""
    flow_config = await container.flow_repository.get(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    return [
        TriggerResponse(
            trigger_id=t.trigger_id,
            name=t.name,
            type=t.type,
            enabled=t.enabled,
            config=_public_trigger_config(t.config),
            output_mapping=t.output_mapping,
            input_mapping=t.input_mapping,
            output_actions=_trigger_response_output_actions(t),
            webhook_url=t.webhook_url,
            status=t.status,
            last_error=t.last_error,
        )
        for t in flow_config.triggers.values()
    ]


@router.get("/flows/{flow_id}/triggers/{trigger_id}")
async def get_trigger(flow_id: str, trigger_id: str, container: ContainerDep) -> TriggerResponse:
    """Получить триггер по ID."""
    flow_config = await container.flow_repository.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    trigger = flow_config.triggers.get(trigger_id)
    
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    
    return TriggerResponse(
        trigger_id=trigger.trigger_id,
        name=trigger.name,
        type=trigger.type,
        enabled=trigger.enabled,
        config=_public_trigger_config(trigger.config),
        output_mapping=trigger.output_mapping,
        input_mapping=trigger.input_mapping,
        output_actions=_trigger_response_output_actions(trigger),
        webhook_url=trigger.webhook_url,
        status=trigger.status,
        last_error=trigger.last_error,
    )


@router.post("/flows/{flow_id}/triggers")
async def create_trigger(flow_id: str, request: TriggerCreateRequest, container: ContainerDep) -> TriggerResponse:
    """Создать новый триггер."""
    flow_config = await container.flow_repository.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    if request.trigger_id in flow_config.triggers:
        raise HTTPException(
            status_code=400,
            detail=f"Trigger already exists: {request.trigger_id}"
        )
    
    out_actions = request.output_actions
    if len(out_actions) == 0:
        out_actions = default_output_actions_for_trigger_type(request.type)
    
    trigger = TriggerConfig(
        trigger_id=request.trigger_id,
        name=request.name,
        type=request.type,
        enabled=request.enabled,
        config=request.config,
        output_mapping=request.output_mapping,
        input_mapping=request.input_mapping,
        output_actions=out_actions,
    )
    
    # Сохраняем старый конфиг для sync
    old_config = await container.flow_repository.get(flow_id)
    
    # Добавляем триггер в конфиг
    flow_config.triggers[request.trigger_id] = trigger
    
    # Синхронизируем триггеры
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    
    # Сохраняем агента
    await container.flow_repository.set(flow_config)
    
    updated_trigger = flow_config.triggers.get(request.trigger_id)
    
    logger.info(f"Trigger created: flow_id={flow_id}, trigger={request.trigger_id}")
    
    return TriggerResponse(
        trigger_id=updated_trigger.trigger_id,
        name=updated_trigger.name,
        type=updated_trigger.type,
        enabled=updated_trigger.enabled,
        config=_public_trigger_config(updated_trigger.config),
        output_mapping=updated_trigger.output_mapping,
        input_mapping=updated_trigger.input_mapping,
        output_actions=_trigger_response_output_actions(updated_trigger),
        webhook_url=updated_trigger.webhook_url,
        status=updated_trigger.status,
        last_error=updated_trigger.last_error,
    )


@router.put("/flows/{flow_id}/triggers/{trigger_id}")
async def update_trigger(
    flow_id: str,
    trigger_id: str,
    request: TriggerUpdateRequest,
    container: ContainerDep,
) -> TriggerResponse:
    """Обновить триггер."""
    old_config = await container.flow_repository.get(flow_id)
    
    if not old_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    trigger = old_config.triggers.get(trigger_id)
    
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    
    # Копируем конфиг для изменений
    flow_config = old_config.model_copy(deep=True)
    trigger = flow_config.triggers[trigger_id]
    
    # Обновляем поля
    if request.name is not None:
        trigger.name = request.name
    if request.enabled is not None:
        trigger.enabled = request.enabled
    if request.config is not None:
        trigger.config = request.config
    if request.output_mapping is not None:
        trigger.output_mapping = request.output_mapping
    if request.input_mapping is not None:
        trigger.input_mapping = request.input_mapping
    if request.output_actions is not None:
        trigger.output_actions = request.output_actions

    flow_config.triggers[trigger_id] = trigger
    
    # Синхронизируем триггеры
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    
    # Сохраняем агента
    await container.flow_repository.set(flow_config)
    
    updated_trigger = flow_config.triggers.get(trigger_id)
    
    logger.info(f"Trigger updated: flow_id={flow_id}, trigger={trigger_id}")
    
    return TriggerResponse(
        trigger_id=updated_trigger.trigger_id,
        name=updated_trigger.name,
        type=updated_trigger.type,
        enabled=updated_trigger.enabled,
        config=_public_trigger_config(updated_trigger.config),
        output_mapping=updated_trigger.output_mapping,
        input_mapping=updated_trigger.input_mapping,
        output_actions=_trigger_response_output_actions(updated_trigger),
        webhook_url=updated_trigger.webhook_url,
        status=updated_trigger.status,
        last_error=updated_trigger.last_error,
    )


@router.delete("/flows/{flow_id}/triggers/{trigger_id}")
async def delete_trigger(flow_id: str, trigger_id: str, container: ContainerDep) -> Dict[str, str]:
    """Удалить триггер."""
    old_config = await container.flow_repository.get(flow_id)
    
    if not old_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    if trigger_id not in old_config.triggers:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    
    # Копируем конфиг
    flow_config = old_config.model_copy(deep=True)
    
    # Удаляем триггер
    del flow_config.triggers[trigger_id]
    
    # Синхронизируем (unregister удаленного)
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=flow_id,
        old_config=old_config,
        new_config=flow_config,
    )
    
    # Сохраняем агента
    await container.flow_repository.set(flow_config)
    
    logger.info(f"Trigger deleted: flow_id={flow_id}, trigger={trigger_id}")
    
    return {"status": "deleted", "trigger_id": trigger_id}


# Webhook endpoints

@router.post("/triggers/telegram/{flow_id}/{trigger_id}")
async def telegram_webhook(
    flow_id: str,
    trigger_id: str,
    request: Request,
    container: ContainerDep,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
) -> Dict[str, str]:
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
            comp = Company(
                company_id=company_identifier,
                subdomain=company_identifier,
                name=company_identifier,
            )
            inbound_user = User(
                user_id="telegram_inbound",
                name="Telegram Inbound",
                groups=["guest"],
            )
            set_context(
                Context(
                    user=inbound_user,
                    host=ctx.host if ctx else "",
                    session_id=ctx.session_id if ctx and ctx.session_id else "telegram_inbound",
                    channel="triggers/telegram",
                    language=ctx.language if ctx else Language.RU,
                    active_company=comp,
                    user_companies=[comp],
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
    
    # Верификация secret_token
    telegram_handler = TelegramTriggerHandler(base_url="")
    
    if x_telegram_bot_api_secret_token:
        if not telegram_handler.verify_secret_token(trigger, x_telegram_bot_api_secret_token):
            logger.warning(f"Telegram webhook: invalid secret token: {trigger_id}")
            raise HTTPException(status_code=403, detail="Invalid secret token")
    
    # Парсим Update
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Telegram webhook: failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    logger.info(
        f"Telegram webhook received: flow_id={flow_id}, trigger={trigger_id}, "
        f"update_id={payload.get('update_id')}"
    )
    
    # Обрабатываем
    try:
        result = await telegram_handler.handle(flow_id, trigger_id, payload)
        return {"status": "ok", "task_id": result.get("task_id", "")}
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
) -> Dict[str, Any]:
    """
    Generic webhook endpoint для внешних сервисов.
    """
    flow_config = await container.flow_repository.get(flow_id)
    
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

    raw_secret = trigger.config.get("secret_token")
    if raw_secret is not None and str(raw_secret).strip() != "":
        expected = await _resolve_config_secret_value(container, str(raw_secret))
        received = _webhook_secret_from_request(request)
        if not received:
            raise HTTPException(status_code=403, detail="Secret required")
        if not secrets.compare_digest(expected, received):
            raise HTTPException(status_code=403, detail="Invalid secret")
    
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e

    if isinstance(payload, dict):
        keys = list(payload.keys())
        n = len(keys)
        if n > 24:
            keys = keys[:24] + ["..."]
        logger.info(
            f"Webhook received: flow_id={flow_id}, trigger={trigger_id}, key_count={n}, top_keys={keys}"
        )
    else:
        logger.info(
            f"Webhook received: flow_id={flow_id}, trigger={trigger_id}, payload_type={type(payload).__name__}"
        )

    raise HTTPException(
        status_code=501,
        detail="Webhook trigger execution is not implemented",
    )


# Test endpoint

@router.post("/flows/{flow_id}/triggers/{trigger_id}/test")
async def test_trigger(
    flow_id: str,
    trigger_id: str,
    payload: Dict[str, Any],
    container: ContainerDep,
) -> Dict[str, Any]:
    """
    Тестирует триггер с заданным payload.
    
    Полезно для отладки input_mapping.
    """
    flow_config = await container.flow_repository.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    trigger = flow_config.triggers.get(trigger_id)
    
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    
    # Тестируем output_mapping
    from apps.flows.src.triggers.input_mapper import InputMapper
    
    mapper = InputMapper()
    mapping = trigger.output_mapping or trigger.input_mapping or {}
    mapped_data = mapper.map(trigger_id, payload, mapping)
    
    trigger_type_str = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)
    
    return {
        "status": "ok",
        "trigger_id": trigger_id,
        "trigger_type": trigger_type_str,
        "input_payload": payload,
        "mapped_data": mapped_data,
    }
