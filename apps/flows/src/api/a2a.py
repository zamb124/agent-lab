"""
HTTP и JSON-RPC эндпоинты A2A для flows (a2a-sdk).
Полная реализация протокола; поддержаны все методы спецификации.
"""

import json
from typing import Any, Dict, List, Optional

from a2a.types import (
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigParams,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigRequest,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    SetTaskPushNotificationConfigRequest,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskResubscriptionRequest,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.services.embed_target_resolver import EmbedTarget, resolve_embed_target
from core.context import get_context
from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from core.logging import get_logger
from apps.flows.src.models import FlowConfig
from core.ui_events import publish_ui_event_to_user
from core.utils.tokens import TokenData, TokenType

logger = get_logger(__name__)


def _get_user_groups(request: Request) -> list[str]:
    """Извлекает группы пользователя из request.state.user."""
    if not hasattr(request.state, "user") or request.state.user is None:
        return []
    
    user = request.state.user
    if isinstance(user, dict):
        return user.get("grps", []) or user.get("groups", []) or []
    
    return getattr(user, "grps", []) or getattr(user, "groups", []) or []

router = APIRouter(tags=["public", "a2a"])


# Supported A2A methods
A2A_METHODS = {
    "message/send",
    "message/stream",
    "tasks/get",
    "tasks/cancel",
    "tasks/resubscribe",
    "tasks/pushNotificationConfig/get",
    "tasks/pushNotificationConfig/set",
    "tasks/pushNotificationConfig/delete",
    "tasks/pushNotificationConfig/list",
    "agent/getAuthenticatedExtendedCard",
}

_STREAM_METHODS = {"message/stream", "tasks/resubscribe"}


def _is_embed_session_token(token_data: Optional[TokenData]) -> bool:
    return token_data is not None and token_data.token_type == TokenType.EMBED_SESSION


def _validate_embed_session_request(
    *,
    request: Request,
    token_data: TokenData,
    embed_id: str | None,
    flow_id: str,
    method: str,
    params_dict: Dict[str, Any],
    expected_skill_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Проверяет claims embed-session токена для A2A вызова."""
    metadata = token_data.metadata if isinstance(token_data.metadata, dict) else {}
    embed_token_id = metadata.get("embed_id")
    if embed_id is not None:
        if not isinstance(embed_token_id, str) or not embed_token_id.strip():
            return {"code": -32000, "message": "Invalid embed session token: embed_id is required"}
        if embed_token_id.strip() != embed_id:
            return {"code": -32000, "message": "Embed session token is not allowed for this embed"}

    embed_flow_id = metadata.get("embed_flow_id")
    if not isinstance(embed_flow_id, str) or not embed_flow_id.strip():
        return {"code": -32000, "message": "Invalid embed session token: embed_flow_id is required"}
    if flow_id != embed_flow_id.strip():
        return {"code": -32000, "message": "Embed session token is not allowed for this flow"}

    if method not in {"message/send", "message/stream"}:
        return {"code": -32000, "message": "Embed session token supports only message/send and message/stream"}

    allowed_origin = metadata.get("allowed_origin")
    origin = request.headers.get("origin", "")
    if isinstance(allowed_origin, str) and allowed_origin.strip():
        if origin != allowed_origin.strip():
            return {"code": -32000, "message": "Origin is not allowed for this embed session token"}

    allowed_skill_id = metadata.get("embed_skill_id")
    if expected_skill_id is not None and isinstance(allowed_skill_id, str) and allowed_skill_id.strip():
        if allowed_skill_id.strip() != expected_skill_id:
            return {"code": -32000, "message": "Embed session token skill mismatch"}
    if isinstance(allowed_skill_id, str) and allowed_skill_id.strip():
        effective_skill_id = allowed_skill_id.strip()
        metadata_dict = params_dict.get("metadata")
        if metadata_dict is None:
            params_dict["metadata"] = {"skill": effective_skill_id}
        elif isinstance(metadata_dict, dict):
            request_skill = metadata_dict.get("skill")
            if request_skill is None:
                metadata_dict["skill"] = effective_skill_id
            elif str(request_skill).strip() != effective_skill_id:
                return {"code": -32000, "message": "Embed session token is not allowed for this skill"}
        else:
            return {"code": -32602, "message": "Invalid params: metadata must be object"}

    logger.info(
        "embed_session_validated flow_id=%s skill_id=%s company_id=%s origin=%s issuer=%s",
        flow_id,
        metadata.get("embed_skill_id", "default"),
        token_data.company_id,
        origin,
        metadata.get("issued_by", "unknown"),
    )
    return None


def _sse_error_response(rpc_id: str | None, code: int, message: str) -> StreamingResponse:
    """JSON-RPC ошибка в виде SSE, чтобы клиент мог её распарсить."""
    error_payload = json.dumps(
        {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}},
        ensure_ascii=False,
    )

    async def _gen():
        yield f"data: {error_payload}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


async def _get_flow_config(
    flow_id: str, container: FlowContainer, version: Optional[str] = None,
) -> Optional[FlowConfig]:
    """
    Получает конфигурацию агента.
    
    Args:
        flow_id: ID агента
        container: DI-контейнер
        version: Версия агента (опционально). Если не указана - возвращает latest.
    """
    if version:
        return await container.flow_repository.get_version(flow_id, version)
    return await container.flow_repository.get(flow_id)


def _get_base_url(request: Request) -> str:
    """Получает базовый URL из request с приоритетом X-Forwarded-Proto."""
    # Приоритет X-Forwarded-Proto над request.url.scheme
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto.lower()
    else:
        scheme = request.url.scheme
    
    # Используем X-Forwarded-Host, который содержит host:port от Nginx
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host
    else:
        host = request.headers.get("host") or request.url.netloc
        # Если host не содержит порт, добавляем порт
        if ":" not in host:
            if request.url.port:
                host = f"{host}:{request.url.port}"
            elif scheme == "https":
                host = f"{host}:443"
            elif scheme == "http":
                host = f"{host}:80"
    
    return f"{scheme}://{host}"


@router.get("/{flow_id}/.well-known/agent-card.json")
async def get_agent_card_well_known(
    flow_id: str, 
    request: Request,
    container: ContainerDep,
    v: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Agent Card по well-known URL.
    
    Query params:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    
    context = get_context()
    channel = A2AChannel(flow_id, context=context, flow_config=config)
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{flow_id}")
async def get_agent_card(
    flow_id: str, 
    request: Request,
    container: ContainerDep,
    v: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Agent Card по A2A спецификации - GET на URL агента.
    
    Query params:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    
    context = get_context()
    channel = A2AChannel(flow_id, context=context, flow_config=config)
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _handle_streaming(
    handler: A2AChannel,
    params: MessageSendParams,
    rpc_id: str,
    context: dict | None = None,
):
    try:
        async for event in handler.on_message_stream(params, context=context):
            event_data = event.model_dump(by_alias=True, exclude_none=True)
            response = {"jsonrpc": "2.0", "id": rpc_id, "result": event_data}
            yield f"data: {json.dumps(response, ensure_ascii=False, default=str)}\n\n"
    except PermissionDenied as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": e.error.to_json_rpc_error(),
        }
        yield f"data: {json.dumps(error_response, ensure_ascii=False, default=str)}\n\n"


async def _handle_resubscribe_streaming(
    handler: A2AChannel, params: TaskIdParams, rpc_id: str
):
    async for event in handler.on_resubscribe_to_task(params):
        event_data = event.model_dump(by_alias=True, exclude_none=True)
        response = {"jsonrpc": "2.0", "id": rpc_id, "result": event_data}
        yield f"data: {json.dumps(response, ensure_ascii=False, default=str)}\n\n"


async def _json_rpc_handler_internal(
    *,
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: Optional[str] = None,
    embed_target: EmbedTarget | None = None,
):
    """
    JSON-RPC handler для A2A протокола.
    
    Версия агента может быть указана:
    - Query param: ?v=20241226120000000000
    - В metadata запроса: {"metadata": {"version": "20241226120000000000"}}
    """
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
        )
    
    if not isinstance(body, dict):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: expected JSON object"},
            }
        )
    
    rpc_id = body.get("id")
    method = body.get("method")
    params_dict = body.get("params", {})
    
    token_data = getattr(request.state, "token_data", None)
    if _is_embed_session_token(token_data):
        if not isinstance(token_data, TokenData):
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": "Invalid embed session token"},
            }
        embed_error = _validate_embed_session_request(
            request=request,
            token_data=token_data,
            embed_id=embed_target.embed_id if embed_target is not None else None,
            flow_id=flow_id,
            method=method,
            params_dict=params_dict,
            expected_skill_id=embed_target.skill_id if embed_target is not None else None,
        )
        if embed_error is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": embed_error}

    if embed_target is not None:
        metadata_dict = params_dict.get("metadata")
        if metadata_dict is None:
            params_dict["metadata"] = {"skill": embed_target.skill_id}
        elif isinstance(metadata_dict, dict):
            request_skill = metadata_dict.get("skill")
            if request_skill is None:
                metadata_dict["skill"] = embed_target.skill_id
            elif str(request_skill).strip() != embed_target.skill_id:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32000, "message": "Embed config skill mismatch"},
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "Invalid params: metadata must be object"},
            }

    # Версия: приоритет query param > metadata.version
    metadata = params_dict.get("metadata") or {}
    version = v or metadata.get("version")
    
    config = await _get_flow_config(flow_id, container, version=version)
    if not config:
        version_info = f" version '{version}'" if version else ""
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": f"Flow not found: {flow_id}{version_info}"},
            }
        )
    
    if not method:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32600, "message": "Invalid Request: missing 'method' field"},
        }

    if method not in A2A_METHODS:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    # Получаем Context из middleware (установлен при авторизации)
    context = get_context()
    
    handler = A2AChannel(flow_id, context=context, flow_config=config)
    
    # Группы пользователя для проверки permissions
    # 1. Из metadata (для тестов и internal calls)
    # 2. Из request.state.user (из JWT через middleware)
    metadata = params_dict.get("metadata") or {}
    user_groups = metadata.get("__user_groups__") or _get_user_groups(request)
    channel_context = {"user_groups": user_groups}
    
    # Добавляем groups в metadata для передачи в worker (для проверки permissions на tools)
    if params_dict.get("metadata") is None:
        params_dict["metadata"] = {}
    params_dict["metadata"]["__user_groups__"] = user_groups

    try:
        if method == "message/send":
            req = SendMessageRequest(
                id=rpc_id, method="message/send", params=MessageSendParams(**params_dict)
            )
            result = await handler.on_message_send(req.params, context=channel_context)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "message/stream":
            req = SendStreamingMessageRequest(
                id=rpc_id, method="message/stream", params=MessageSendParams(**params_dict)
            )
            return StreamingResponse(
                _handle_streaming(handler, req.params, rpc_id, channel_context),
                media_type="text/event-stream",
            )

        elif method == "tasks/get":
            req = GetTaskRequest(
                id=rpc_id, method="tasks/get", params=TaskQueryParams(**params_dict)
            )
            result = await handler.on_get_task(req.params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/cancel":
            req = CancelTaskRequest(
                id=rpc_id, method="tasks/cancel", params=TaskIdParams(**params_dict)
            )
            result = await handler.on_cancel_task(req.params)
            if result is None:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32000, "message": "Task not found"},
                }
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "tasks/resubscribe":
            req = TaskResubscriptionRequest(
                id=rpc_id, method="tasks/resubscribe", params=TaskIdParams(**params_dict)
            )
            return StreamingResponse(
                _handle_resubscribe_streaming(handler, req.params, rpc_id),
                media_type="text/event-stream",
            )

        elif method == "tasks/pushNotificationConfig/get":
            req = GetTaskPushNotificationConfigRequest(
                id=rpc_id,
                method="tasks/pushNotificationConfig/get",
                params=GetTaskPushNotificationConfigParams(**params_dict),
            )
            result = await handler.on_get_task_push_notification_config(req.params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/pushNotificationConfig/set":
            req = SetTaskPushNotificationConfigRequest(
                id=rpc_id,
                method="tasks/pushNotificationConfig/set",
                params=TaskPushNotificationConfig(**params_dict),
            )
            result = await handler.on_set_task_push_notification_config(req.params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "tasks/pushNotificationConfig/delete":
            req = DeleteTaskPushNotificationConfigRequest(
                id=rpc_id,
                method="tasks/pushNotificationConfig/delete",
                params=DeleteTaskPushNotificationConfigParams(**params_dict),
            )
            await handler.on_delete_task_push_notification_config(req.params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": None}

        elif method == "tasks/pushNotificationConfig/list":
            req = ListTaskPushNotificationConfigRequest(
                id=rpc_id,
                method="tasks/pushNotificationConfig/list",
                params=ListTaskPushNotificationConfigParams(**params_dict),
            )
            result = await handler.on_list_task_push_notification_config(req.params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": [r.model_dump(by_alias=True, exclude_none=True) for r in result],
            }

        elif method == "agent/getAuthenticatedExtendedCard":
            base_url = _get_base_url(request)
            result = await handler.on_get_authenticated_extended_card(params_dict)
            if result:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": result.model_dump(by_alias=True, exclude_none=True),
                }
            card = await handler.get_agent_card(base_url)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": card,
            }
        
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

    except PermissionDenied as e:
        logger.warning(f"Permission denied for {method}: {e}")
        err = e.error.to_json_rpc_error()
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, err.get("code", -32000), err.get("message", str(e)))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
    except Exception as e:
        logger.exception(f"Error handling {method}: {e}")
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32000, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(e)}}


@router.post("/{flow_id}")
async def json_rpc_handler(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: Optional[str] = None,
):
    return await _json_rpc_handler_internal(
        flow_id=flow_id,
        request=request,
        container=container,
        v=v,
    )


@router.post("/embed/{embed_id}")
async def json_rpc_embed_handler(
    embed_id: str,
    request: Request,
    container: ContainerDep,
    v: Optional[str] = None,
):
    embed_target = await resolve_embed_target(container, embed_id)
    if embed_target is None:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Embed not found: {embed_id}"},
            },
            status_code=404,
        )
    if not embed_target.active:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Embed disabled: {embed_id}"},
            },
            status_code=403,
        )
    return await _json_rpc_handler_internal(
        flow_id=embed_target.flow_id,
        request=request,
        container=container,
        v=v,
        embed_target=embed_target,
    )


@router.get("/{flow_id}/skills")
async def list_skills(flow_id: str, container: ContainerDep) -> List[Dict[str, Any]]:
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return await channel.list_skills()


@router.get("/{flow_id}/skills/{skill_id}")
async def get_skill(flow_id: str, skill_id: str, container: ContainerDep) -> Dict[str, Any]:
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    
    result = await channel.get_skill(skill_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return result


@router.get("/{flow_id}/skills/{skill_id}/tools")
async def get_skill_tools(flow_id: str, skill_id: str, container: ContainerDep) -> List[Dict[str, Any]]:
    """Получить список tools для skill с полной информацией."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    
    # 'base' — это базовый агент без конкретного skill
    if skill_id != "base":
        skill = await channel.get_skill(skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    
    return await channel.get_skill_tools(skill_id)


@router.get("/{flow_id}/schema")
async def get_skill_schema(flow_id: str, container: ContainerDep) -> Dict[str, Any]:
    """Получить JSON Schema для создания навыка в формате ISchema."""
    _ = container
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    try:
        return await channel.get_skill_schema()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{flow_id}/skills")
async def create_skill(flow_id: str, request: Request, container: ContainerDep) -> Dict[str, Any]:
    """Создать новый skill."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    skill_id = data.get("skill_id")
    if not skill_id:
        raise HTTPException(status_code=400, detail="Field 'skill_id' is required")

    try:
        result = await channel.create_skill(skill_id, data)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/skill/created",
            payload={"flow_id": flow_id, "skill_id": skill_id},
        )

    return JSONResponse(result, status_code=201)


@router.put("/{flow_id}/skills/{skill_id}")
async def update_skill(flow_id: str, skill_id: str, request: Request, container: ContainerDep) -> Dict[str, Any]:
    """Обновить существующий skill."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        result = await channel.update_skill(skill_id, data)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found. Use POST to create.")
        raise HTTPException(status_code=400, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/skill/updated",
            payload={"flow_id": flow_id, "skill_id": skill_id},
        )

    return result


@router.delete("/{flow_id}/skills/{skill_id}")
async def delete_skill(flow_id: str, skill_id: str, container: ContainerDep) -> Dict[str, Any]:
    """Удалить skill."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        result = await channel.delete_skill(skill_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/skill/deleted",
            payload={"flow_id": flow_id, "skill_id": skill_id},
        )

    return result
