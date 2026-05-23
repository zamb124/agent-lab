"""
API endpoints для триггеров агентов.

CRUD для триггеров + webhook endpoints для приема входящих событий.
"""

import json
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import TriggerConfig, TriggerStatus, TriggerType
from apps.flows.src.models.channel_config import (
    OutputAction,
    default_output_actions_for_trigger,
)
from apps.flows.src.triggers import TriggerValidationError
from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
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
from apps.flows.src.triggers.webhook_inbound import check_webhook_rate_limit, client_ip_allowed
from core.context import get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.variables.resolver import VariableResolutionError

logger = get_logger(__name__)

_SENSITIVE_TRIGGER_CONFIG_KEYS = frozenset(
    {"bot_token", "secret_token", "imap_password", "password"},
)

# Сообщение list/get/SINGLE и POST verify не должны путать: UI подставляет это в _config
# и иначе verify шлёт буквально .../bot(redacted)/getMe (HTTP 404).
_REDACTED_CONFIG_SECRET = "(redacted)"


def _public_trigger_config(config: dict[str, Any]) -> dict[str, Any]:
    """Убирает служебные ключи и скрывает секреты в ответах API."""
    out: dict[str, Any] = {}
    for k, v in config.items():
        if k.startswith("_"):
            continue
        if k in _SENSITIVE_TRIGGER_CONFIG_KEYS and v not in (None, ""):
            out[k] = _REDACTED_CONFIG_SECRET
        else:
            out[k] = v
    return out


def _webhook_secret_from_request(request: Request) -> str | None:
    for header in ("X-Trigger-Secret", "X-Webhook-Secret"):
        v = request.headers.get(header)
        if v:
            return v
    return request.query_params.get("secret")


async def _resolve_company_from_flow_storage_identifier(
    container: Any,
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

    logger.warning(
        "Flow storage company identifier has no persisted Company; using minimal context",
        company_identifier=company_identifier,
    )
    return Company(
        company_id=company_identifier,
        subdomain=company_identifier,
        name=company_identifier,
    )

router = APIRouter(tags=["triggers"])


# Request/Response models

class TriggerCreateRequest(BaseModel):
    """Запрос на создание триггера."""
    trigger_id: str = Field(..., description="ID триггера")
    name: str = Field(..., description="Название")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен")
    config: dict[str, Any] = Field(default_factory=dict, description="Конфигурация")
    output_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг payload -> state (state.path -> payload.path)",
    )
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="DEPRECATED: используйте output_mapping",
    )
    output_actions: list[OutputAction] = Field(
        default_factory=list,
        description="Действия отправки ответа в канал после агента",
    )
    post_flow_output_enabled: bool | None = Field(
        default=None,
        description="Включить рассылку после flow; None — дефолт по типу триггера",
    )
    branch_id: str = Field(
        default="default",
        description="ID ветки из FlowConfig.branches; default — entry базового flow",
    )


class TriggerUpdateRequest(BaseModel):
    """Запрос на обновление триггера."""
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    output_mapping: dict[str, str] | None = None
    input_mapping: dict[str, str] | None = None
    output_actions: list[OutputAction] | None = None
    post_flow_output_enabled: bool | None = None
    branch_id: str | None = None


class TriggerResponse(BaseModel):
    """Ответ с данными триггера."""
    trigger_id: str
    name: str
    type: TriggerType
    enabled: bool
    config: dict[str, Any]
    output_mapping: dict[str, str]
    input_mapping: dict[str, str]
    output_actions: list[OutputAction]
    post_flow_output_enabled: bool
    branch_id: str
    webhook_url: str | None = None
    status: TriggerStatus
    last_error: str | None = None


class TriggerVerifyRequest(BaseModel):
    """Проверка чернового конфига триггера (без сохранения)."""
    type: TriggerType = Field(..., description="Тип триггера")
    config: dict[str, Any] = Field(default_factory=dict, description="Конфиг как в trigger.config")
    trigger_id: str | None = Field(
        default=None,
        description="Черновой ID триггера (для подсказки пути webhook)",
    )
    branch_id: str = Field(
        default="default",
        description="Ветка (branch_id) для резолва @var: (как при выполнении flow с этой веткой)",
    )


class TriggerVerifyResponse(BaseModel):
    """Результат проверки (getMe, cron, схема пути)."""
    ok: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


# CRUD-endpoints

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
            output_actions=effective_output_actions_for_trigger(t),
            post_flow_output_enabled=t.post_flow_output_enabled,
            branch_id=t.branch_id,
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
        output_actions=effective_output_actions_for_trigger(trigger),
        post_flow_output_enabled=trigger.post_flow_output_enabled,
        branch_id=trigger.branch_id,
        webhook_url=trigger.webhook_url,
        status=trigger.status,
        last_error=trigger.last_error,
    )


@router.post("/flows/{flow_id}/triggers/verify", response_model=TriggerVerifyResponse)
async def verify_trigger_draft(
    flow_id: str, request: TriggerVerifyRequest, container: ContainerDep
) -> TriggerVerifyResponse:
    """
    Проверяет черновик конфига: Telegram getMe, валидность cron, подсказки для webhook.
    """
    flow_config = await container.flow_repository.get(flow_id)
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")

    cfg: dict[str, Any] = dict(request.config)
    if request.type == TriggerType.TELEGRAM:
        raw_token = cfg.get("bot_token")
        if isinstance(raw_token, str) and raw_token == _REDACTED_CONFIG_SECRET:
            tid = request.trigger_id
            if isinstance(tid, str) and tid.strip() != "":
                stored = flow_config.triggers.get(tid)
                if stored is not None:
                    st = stored.config.get("bot_token")
                    if st is not None and str(st).strip() != "":
                        cfg["bot_token"] = st
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
                    flow_id,
                    raw_token,
                    branch_id=request.branch_id,
                )
            except VariableResolutionError as e:
                return TriggerVerifyResponse(
                    ok=False,
                    metadata={},
                    error_code="variable_not_found",
                    error_message=str(e),
                )

    ok, metadata, err_code, err_msg = await run_verify(
        request.type, cfg, flow_id, request.trigger_id
    )
    return TriggerVerifyResponse(
        ok=ok,
        metadata=metadata,
        error_code=err_code,
        error_message=err_msg,
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

    post_enabled = request.post_flow_output_enabled
    if post_enabled is None:
        post_enabled = default_post_flow_output_enabled(request.type)
    if post_enabled and len(request.output_actions) == 0:
        out_actions = default_output_actions_for_trigger(request.trigger_id, request.type)
    else:
        out_actions = list(request.output_actions)

    trigger = TriggerConfig(
        trigger_id=request.trigger_id,
        name=request.name,
        type=request.type,
        enabled=request.enabled,
        config=request.config,
        output_mapping=request.output_mapping,
        input_mapping=request.input_mapping,
        output_actions=out_actions,
        post_flow_output_enabled=post_enabled,
        branch_id=request.branch_id,
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
    if updated_trigger is None:
        raise RuntimeError(f"Trigger '{request.trigger_id}' missing after sync")

    logger.info(f"Trigger created: flow_id={flow_id}, trigger={request.trigger_id}")

    return TriggerResponse(
        trigger_id=updated_trigger.trigger_id,
        name=updated_trigger.name,
        type=updated_trigger.type,
        enabled=updated_trigger.enabled,
        config=_public_trigger_config(updated_trigger.config),
        output_mapping=updated_trigger.output_mapping,
        input_mapping=updated_trigger.input_mapping,
        output_actions=effective_output_actions_for_trigger(updated_trigger),
        post_flow_output_enabled=updated_trigger.post_flow_output_enabled,
        branch_id=updated_trigger.branch_id,
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
    if request.post_flow_output_enabled is not None:
        trigger.post_flow_output_enabled = request.post_flow_output_enabled
    if request.branch_id is not None:
        trigger.branch_id = request.branch_id

    cur = flow_config.triggers[trigger_id]
    flow_config.triggers[trigger_id] = TriggerConfig.model_validate(cur.model_dump())

    # Синхронизируем триггеры
    flow_config = await container.trigger_registry.sync_triggers(
        flow_id=flow_id,
        old_config=old_config,
        new_config=flow_config,
    )

    # Сохраняем агента
    await container.flow_repository.set(flow_config)

    updated_trigger = flow_config.triggers.get(trigger_id)
    if updated_trigger is None:
        raise RuntimeError(f"Trigger '{trigger_id}' missing after sync")

    logger.info(f"Trigger updated: flow_id={flow_id}, trigger={trigger_id}")

    return TriggerResponse(
        trigger_id=updated_trigger.trigger_id,
        name=updated_trigger.name,
        type=updated_trigger.type,
        enabled=updated_trigger.enabled,
        config=_public_trigger_config(updated_trigger.config),
        output_mapping=updated_trigger.output_mapping,
        input_mapping=updated_trigger.input_mapping,
        output_actions=effective_output_actions_for_trigger(updated_trigger),
        post_flow_output_enabled=updated_trigger.post_flow_output_enabled,
        branch_id=updated_trigger.branch_id,
        webhook_url=updated_trigger.webhook_url,
        status=updated_trigger.status,
        last_error=updated_trigger.last_error,
    )


@router.post("/flows/{flow_id}/triggers/{trigger_id}/reregister", response_model=TriggerResponse)
async def reregister_flow_trigger(
    flow_id: str, trigger_id: str, container: ContainerDep
) -> TriggerResponse:
    """
    Снимает триггер с внешней стороны и регистрирует заново (для Telegram — deleteWebhook + setWebhook).
    """
    old_config = await container.flow_repository.get(flow_id)
    if not old_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    if trigger_id not in old_config.triggers:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")

    flow_config = old_config.model_copy(deep=True)
    trigger = flow_config.triggers[trigger_id]
    try:
        updated = await container.trigger_registry.reregister_trigger(flow_id, trigger)
    except TriggerReregisterDisabledError as e:
        raise HTTPException(
            status_code=400,
            detail="Включите триггер перед перерегистрацией хуков.",
        ) from e
    except TriggerReregisterUnsupportedError as e:
        tstr = (
            e.trigger_type.value
            if hasattr(e.trigger_type, "value")
            else str(e.trigger_type)
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Перерегистрация внешних хуков для типа {tstr} "
                "не реализована. Сейчас поддерживается только Telegram (setWebhook)."
            ),
        ) from e

    flow_config.triggers[trigger_id] = updated
    await container.flow_repository.set(flow_config)
    out = flow_config.triggers[trigger_id]
    logger.info("Trigger reregistered: flow_id=%s trigger=%s", flow_id, trigger_id)
    return TriggerResponse(
        trigger_id=out.trigger_id,
        name=out.name,
        type=out.type,
        enabled=out.enabled,
        config=_public_trigger_config(out.config),
        output_mapping=out.output_mapping,
        input_mapping=out.input_mapping,
        output_actions=effective_output_actions_for_trigger(out),
        post_flow_output_enabled=out.post_flow_output_enabled,
        branch_id=out.branch_id,
        webhook_url=out.webhook_url,
        status=out.status,
        last_error=out.last_error,
    )


@router.delete("/flows/{flow_id}/triggers/{trigger_id}")
async def delete_trigger(flow_id: str, trigger_id: str, container: ContainerDep) -> dict[str, str]:
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


# Webhook-endpoints

@router.post("/triggers/telegram/{flow_id}/{trigger_id}")
async def telegram_webhook(
    flow_id: str,
    trigger_id: str,
    request: Request,
    container: ContainerDep,
    x_telegram_bot_api_secret_token: str | None = Header(None),
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
            set_context(
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
) -> dict[str, Any]:
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
        try:
            expected = await resolve_at_var_for_flow(
                container.flow_factory,
                flow_id,
                str(raw_secret),
                branch_id=trigger.branch_id,
            )
        except VariableResolutionError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
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


# Тестовый endpoint

@router.post("/flows/{flow_id}/triggers/{trigger_id}/test")
async def test_trigger(
    flow_id: str,
    trigger_id: str,
    payload: dict[str, Any],
    container: ContainerDep,
) -> dict[str, Any]:
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

    mapper = InputMapper()
    mapping = {**dict(trigger.input_mapping), **dict(trigger.output_mapping)}
    mapped_data = mapper.map(trigger_id, payload, mapping)

    trigger_type_str = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)

    return {
        "status": "ok",
        "trigger_id": trigger_id,
        "trigger_type": trigger_type_str,
        "input_payload": payload,
        "mapped_data": mapped_data,
    }
