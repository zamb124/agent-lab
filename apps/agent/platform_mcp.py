"""
Platform MCP endpoint для HumanitecAgent.

Flow компании доступны как MCP tools через streamable HTTP.
"""

import uuid

from a2a.types import Message, MessageSendParams, Part, Role, TextPart
from fastapi import APIRouter, HTTPException, Request

from apps.agent.device_auth import reject_revoked_device_bearer_if_present
from apps.agent.service import (
    build_flow_mcp_tools,
    record_agent_audit_event_redis,
)
from apps.agent.tunnel_bus import send_mcp_request_to_device
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep as FlowsContainerDep
from core.context import get_context, require_context
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)
router = APIRouter(tags=["agent-platform-mcp"])


async def _reject_revoked_device_bearer(request: Request, container: FlowsContainerDep) -> None:
    await reject_revoked_device_bearer_if_present(request, container)


@router.get("/agent/platform-mcp", tags=["agent-platform-mcp", "public"])
async def platform_mcp_discover(
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject:
    await _reject_revoked_device_bearer(request, container)
    _ = container
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "Humanitec Platform MCP",
            "version": "1.0.0",
        },
        "capabilities": {
            "tools": {},
        },
    }


async def _list_company_flow_tools(container: FlowsContainerDep) -> list[JsonObject]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    flows = await container.flow_repository.list(limit=500, offset=0)
    flow_payloads: list[JsonObject] = []
    for flow_config in flows:
        flow_payloads.append(
            {
                "flow_id": flow_config.flow_id,
                "name": flow_config.name,
                "description": flow_config.description,
            }
        )
    return build_flow_mcp_tools(flow_payloads)


def _extract_task_text(task_payload: JsonObject) -> str:
    history_raw = task_payload.get("history")
    if isinstance(history_raw, list):
        for message_item in reversed(history_raw):
            if not isinstance(message_item, dict):
                continue
            role = message_item.get("role")
            if role != "agent":
                continue
            parts_raw = message_item.get("parts")
            if not isinstance(parts_raw, list):
                continue
            text_chunks: list[str] = []
            for part_item in parts_raw:
                if not isinstance(part_item, dict):
                    continue
                if part_item.get("kind") != "text":
                    continue
                text_value = part_item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    text_chunks.append(text_value.strip())
            if text_chunks:
                return "\n".join(text_chunks)

    status_raw = task_payload.get("status")
    if isinstance(status_raw, dict):
        message_raw = status_raw.get("message")
        if isinstance(message_raw, dict):
            parts_raw = message_raw.get("parts")
            if isinstance(parts_raw, list):
                for part_item in parts_raw:
                    if not isinstance(part_item, dict):
                        continue
                    if part_item.get("kind") != "text":
                        continue
                    text_value = part_item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        return text_value.strip()

    raise ValueError("Flow task не содержит текстового ответа")


def _extract_task_state(task_payload: JsonObject) -> str:
    status_raw = task_payload.get("status")
    if not isinstance(status_raw, dict):
        raise ValueError("Flow task status missing")
    state = status_raw.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("Flow task status.state missing")
    return state


async def _execute_flow_tool_call(
    container: FlowsContainerDep,
    *,
    flow_id: str,
    user_message: str,
    context_id: str | None = None,
) -> tuple[str, str, str]:
    flow_config = await container.flow_repository.get(flow_id)
    if flow_config is None:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id!r} не найден")

    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Контекст не установлен")

    message_id = str(uuid.uuid4())
    resolved_context_id = context_id if context_id is not None else str(uuid.uuid4())
    a2a_message = Message(
        role=Role.user,
        message_id=message_id,
        context_id=resolved_context_id,
        parts=[Part(root=TextPart(text=user_message))],
    )
    params = MessageSendParams(message=a2a_message)
    channel = A2AChannel(
        flow_id,
        context=context,
        container=as_flow_runtime_container(container),
    )
    task = await channel.on_message_send(params)
    task_payload = require_json_object(
        task.model_dump(by_alias=True, exclude_none=True),
        "task.payload",
    )
    task_state = _extract_task_state(task_payload)
    if task_state == "failed":
        status_value = task_payload.get("status")
        if status_value is not None:
            status_object = require_json_object(status_value, "task.status")
            message_value = status_object.get("message")
            if message_value is not None:
                message_object = require_json_object(message_value, "task.status.message")
                parts_value = message_object.get("parts")
                if isinstance(parts_value, list):
                    for part_value in parts_value:
                        part_object = require_json_object(part_value, "task.status.message.part")
                        if part_object.get("kind") != "text":
                            continue
                        text_value = part_object.get("text")
                        if isinstance(text_value, str) and text_value.strip():
                            raise HTTPException(
                                status_code=500,
                                detail=text_value.strip(),
                            )
        raise HTTPException(status_code=500, detail="Flow task failed")
    response_text = _extract_task_text(task_payload)
    return response_text, resolved_context_id, task_state


@router.post("/agent/platform-mcp", tags=["agent-platform-mcp", "public"])
async def platform_mcp_message(
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject:
    await _reject_revoked_device_bearer(request, container)
    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=400, detail="Пустое MCP сообщение")

    message = parse_json_object(raw_body.decode("utf-8"), "agent.platform_mcp.message")
    method = message.get("method")
    rpc_id: JsonValue = message.get("id")
    if rpc_id is None:
        rpc_id = 1

    if method == "tools/list":
        tools = await _list_company_flow_tools(container)
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": tools,
            },
        }

    if method == "tools/call":
        params_raw = message.get("params")
        params = require_json_object(params_raw, "agent.platform_mcp.params") if params_raw is not None else {}
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.startswith("flow_"):
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32602,
                    "message": "Unsupported tool name",
                },
            }
        flow_id = tool_name.removeprefix("flow_")
        arguments_raw = params.get("arguments")
        arguments = (
            require_json_object(arguments_raw, "agent.platform_mcp.arguments")
            if arguments_raw is not None
            else {}
        )
        user_message = arguments.get("message")
        if not isinstance(user_message, str) or not user_message.strip():
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32602,
                    "message": "arguments.message is required",
                },
            }
        context_id_raw = arguments.get("context_id")
        resolved_context_id: str | None = None
        if isinstance(context_id_raw, str) and context_id_raw.strip():
            resolved_context_id = context_id_raw.strip()
        logger.info("agent.platform_mcp.tools_call", flow_id=flow_id)
        active_context = require_context()
        active_company = active_context.active_company
        if active_company is None:
            raise HTTPException(status_code=400, detail="Компания не выбрана")
        try:
            response_text, used_context_id, task_state = await _execute_flow_tool_call(
                container,
                flow_id=flow_id,
                user_message=user_message.strip(),
                context_id=resolved_context_id,
            )
        except HTTPException as exc:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32000,
                    "message": str(exc.detail),
                },
            }
        except ValueError as exc:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32000,
                    "message": str(exc),
                },
            }
        await record_agent_audit_event_redis(
            container.redis_client,
            company_id=active_company.company_id,
            event_type="agent.platform_mcp.tools_call",
            actor_user_id=active_context.user.user_id,
            device_id=None,
            detail=f"flow_id={flow_id}",
        )
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": response_text,
                    }
                ],
                "isError": False,
                "context_id": used_context_id,
                "task_state": task_state,
            },
        }

    if method == "device/mcp":
        params_raw = message.get("params")
        params = require_json_object(params_raw, "agent.platform_mcp.device.params")
        device_id = params.get("device_id")
        mcp_method = params.get("method")
        mcp_params_raw = params.get("params")
        if not isinstance(device_id, str) or not device_id:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "params.device_id is required"},
            }
        if not isinstance(mcp_method, str) or not mcp_method:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "params.method is required"},
            }
        mcp_params = (
            require_json_object(mcp_params_raw, "agent.platform_mcp.device.mcp_params")
            if mcp_params_raw is not None
            else {}
        )
        try:
            device_result = await send_mcp_request_to_device(
                container.redis_client,
                device_id,
                method=mcp_method,
                params=mcp_params,
                timeout_seconds=2.0,
            )
        except ValueError as exc:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        active_context = require_context()
        active_company = active_context.active_company
        if active_company is None:
            raise HTTPException(status_code=400, detail="Компания не выбрана")
        await record_agent_audit_event_redis(
            container.redis_client,
            company_id=active_company.company_id,
            event_type="agent.platform_mcp.device_mcp",
            actor_user_id=active_context.user.user_id,
            device_id=device_id,
            detail=f"method={mcp_method}",
        )
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": device_result,
        }

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {
            "code": -32601,
            "message": f"Unsupported MCP method: {method!r}",
        },
    }
