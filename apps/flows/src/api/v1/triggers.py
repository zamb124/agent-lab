"""
API endpoints для триггеров агентов.

CRUD для триггеров + webhook endpoints для приема входящих событий.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.flows.src.container import get_container
from apps.flows.src.models import TriggerConfig, TriggerStatus, TriggerType
from apps.flows.src.triggers import TriggerRegistry, TriggerValidationError
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["triggers"])


# Request/Response models

class TriggerCreateRequest(BaseModel):
    """Запрос на создание триггера."""
    trigger_id: str = Field(..., description="ID триггера")
    name: str = Field(..., description="Название")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен")
    config: Dict[str, Any] = Field(default_factory=dict, description="Конфигурация")
    input_mapping: Dict[str, str] = Field(default_factory=dict, description="Маппинг")


class TriggerUpdateRequest(BaseModel):
    """Запрос на обновление триггера."""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    input_mapping: Optional[Dict[str, str]] = None


class TriggerResponse(BaseModel):
    """Ответ с данными триггера."""
    trigger_id: str
    name: str
    type: TriggerType
    enabled: bool
    config: Dict[str, Any]
    input_mapping: Dict[str, str]
    webhook_url: Optional[str] = None
    status: TriggerStatus
    last_error: Optional[str] = None


class TriggerListResponse(BaseModel):
    """Список триггеров."""
    triggers: List[TriggerResponse]


# CRUD endpoints

@router.get("/flows/{flow_id}/triggers")
async def list_triggers(flow_id: str) -> TriggerListResponse:
    """Получить список триггеров агента."""
    container = get_container()
    flow_config = await container.flow_repository.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    triggers = [
        TriggerResponse(
            trigger_id=t.trigger_id,
            name=t.name,
            type=t.type,
            enabled=t.enabled,
            config={k: v for k, v in t.config.items() if not k.startswith("_")},
            input_mapping=t.input_mapping,
            webhook_url=t.webhook_url,
            status=t.status,
            last_error=t.last_error,
        )
        for t in flow_config.triggers.values()
    ]
    
    return TriggerListResponse(triggers=triggers)


@router.get("/flows/{flow_id}/triggers/{trigger_id}")
async def get_trigger(flow_id: str, trigger_id: str) -> TriggerResponse:
    """Получить триггер по ID."""
    container = get_container()
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
        config={k: v for k, v in trigger.config.items() if not k.startswith("_")},
        input_mapping=trigger.input_mapping,
        webhook_url=trigger.webhook_url,
        status=trigger.status,
        last_error=trigger.last_error,
    )


@router.post("/flows/{flow_id}/triggers")
async def create_trigger(flow_id: str, request: TriggerCreateRequest) -> TriggerResponse:
    """Создать новый триггер."""
    container = get_container()
    flow_config = await container.flow_repository.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
    
    if request.trigger_id in flow_config.triggers:
        raise HTTPException(
            status_code=400,
            detail=f"Trigger already exists: {request.trigger_id}"
        )
    
    trigger = TriggerConfig(
        trigger_id=request.trigger_id,
        name=request.name,
        type=request.type,
        enabled=request.enabled,
        config=request.config,
        input_mapping=request.input_mapping,
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
        config={k: v for k, v in updated_trigger.config.items() if not k.startswith("_")},
        input_mapping=updated_trigger.input_mapping,
        webhook_url=updated_trigger.webhook_url,
        status=updated_trigger.status,
        last_error=updated_trigger.last_error,
    )


@router.put("/flows/{flow_id}/triggers/{trigger_id}")
async def update_trigger(
    flow_id: str,
    trigger_id: str,
    request: TriggerUpdateRequest,
) -> TriggerResponse:
    """Обновить триггер."""
    container = get_container()
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
    if request.input_mapping is not None:
        trigger.input_mapping = request.input_mapping
    
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
        config={k: v for k, v in updated_trigger.config.items() if not k.startswith("_")},
        input_mapping=updated_trigger.input_mapping,
        webhook_url=updated_trigger.webhook_url,
        status=updated_trigger.status,
        last_error=updated_trigger.last_error,
    )


@router.delete("/flows/{flow_id}/triggers/{trigger_id}")
async def delete_trigger(flow_id: str, trigger_id: str) -> Dict[str, str]:
    """Удалить триггер."""
    container = get_container()
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
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
) -> Dict[str, str]:
    """
    Webhook endpoint для Telegram Bot API.
    
    Telegram посылает Update сюда после setWebhook.
    """
    container = get_container()
    flow_config = await container.flow_repository.get(flow_id)
    
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
) -> Dict[str, Any]:
    """
    Generic webhook endpoint для внешних сервисов.
    """
    container = get_container()
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
    
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}") from e

    payload_keys = list(payload.keys()) if isinstance(payload, dict) else None
    logger.info(
        f"Webhook received: flow_id={flow_id}, trigger={trigger_id}, payload_type={type(payload).__name__}, keys={payload_keys}"
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
) -> Dict[str, Any]:
    """
    Тестирует триггер с заданным payload.
    
    Полезно для отладки input_mapping.
    """
    container = get_container()
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
