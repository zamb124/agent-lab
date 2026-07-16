"""
Platform MCP endpoint для HumanitecAgent / LinnexAgent.

Полноценный Streamable HTTP MCP-сервер: lifecycle (initialize/ping/notifications),
flow компании как tools ``flow_{flow_id}`` и каталог тулов компании как
``tool_{tool_id}``. Session continuity flow — sticky A2A context_id по
``Mcp-Session-Id`` или device JWT (LaraOnly).
"""

import json
import uuid

from a2a.types import Message, MessageSendParams, Part, Role, TextPart
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from apps.agent.config import get_agent_settings
from apps.agent.device_auth import (
    extract_device_id_from_bearer,
    reject_revoked_device_bearer_if_present,
)
from apps.agent.service import (
    build_flow_mcp_tools,
    record_agent_audit_event_redis,
)
from apps.agent.tunnel_bus import send_mcp_request_to_device
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep as FlowsContainerDep
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.agent_toolkit_service import (
    get_agent_toolkit,
    resolve_allowed_flow_ids,
    resolve_allowed_tool_ids,
)
from apps.flows.src.tools.base import sanitize_tool_name
from core.context import get_context, require_context
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)
router = APIRouter(tags=["agent-platform-mcp"])

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO: JsonObject = {"name": "Humanitec Platform MCP", "version": "1.0.0"}
_SERVER_CAPABILITIES: JsonObject = {"tools": {}}
_MCP_SESSION_HEADER = "Mcp-Session-Id"
_LARA_FLOW_ID = "lara"
_LINNEX_AGENT_BRANCH_ID = "linnex_agent"
_DEVICE_MCP_TIMEOUT_SECONDS = 120.0


async def _reject_revoked_device_bearer(request: Request, container: FlowsContainerDep) -> None:
    await reject_revoked_device_bearer_if_present(request, container)


@router.get("/agent/platform-mcp", tags=["agent-platform-mcp", "public"], response_model=None)
async def platform_mcp_discover(
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, container)
    _ = container
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" in accept_header.lower():
        return Response(status_code=405)
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "serverInfo": _SERVER_INFO,
        "capabilities": _SERVER_CAPABILITIES,
    }


async def _list_company_flow_tools(
    container: FlowsContainerDep,
    *,
    toolkit_id: str | None,
) -> list[JsonObject]:
    context = require_context()
    company = context.active_company
    if company is None:
        return []

    allowed_flow_ids = await resolve_allowed_flow_ids(
        container.agent_toolkit_repository,
        toolkit_id=toolkit_id,
    )
    if not allowed_flow_ids:
        return []

    flows = await container.flow_repository.list(limit=500, offset=0)
    flow_payloads: list[JsonObject] = []
    for flow_config in flows:
        if flow_config.flow_id not in allowed_flow_ids:
            continue
        flow_payloads.append(
            {
                "flow_id": flow_config.flow_id,
                "name": flow_config.name,
                "description": flow_config.description,
            }
        )
    flow_tools = build_flow_mcp_tools(flow_payloads)
    for flow_tool in flow_tools:
        description = flow_tool.get("description")
        flow_tool["description"] = f"[Flow] {description}" if isinstance(description, str) else "[Flow]"
    return flow_tools


def _unique_mcp_tool_name(base: str, seen: set[str]) -> str:
    if base not in seen:
        return base
    suffix = 2
    while f"{base}_{suffix}" in seen:
        suffix += 1
    return f"{base}_{suffix}"


async def _list_company_catalog_tools(
    container: FlowsContainerDep,
    *,
    toolkit_id: str | None,
) -> tuple[list[JsonObject], dict[str, str]]:
    """Каталог тулов компании как MCP tools ``tool_{tool_id}`` + индекс name -> tool_id."""
    allowed_tool_ids = await resolve_allowed_tool_ids(
        container.agent_toolkit_repository,
        toolkit_id=toolkit_id,
    )
    if not allowed_tool_ids:
        return [], {}

    registry = container.tool_registry
    registry.register_builtin_tools()

    tools: list[JsonObject] = []
    name_to_tool_id: dict[str, str] = {}
    seen: set[str] = set()

    for tool_id, tool in registry.list_all().items():
        if tool_id not in allowed_tool_ids:
            continue
        mcp_name = _unique_mcp_tool_name(f"tool_{sanitize_tool_name(tool_id)}", seen)
        seen.add(mcp_name)
        name_to_tool_id[mcp_name] = tool_id
        tools.append(
            {
                "name": mcp_name,
                "description": f"[Tool] {tool.description}",
                "inputSchema": tool.parameters,
            }
        )

    for tool_ref in await container.tool_repository.list(limit=10000):
        if tool_ref.tool_id not in allowed_tool_ids:
            continue
        if tool_ref.tool_id in name_to_tool_id.values():
            continue
        mcp_name = _unique_mcp_tool_name(f"tool_{sanitize_tool_name(tool_ref.tool_id)}", seen)
        seen.add(mcp_name)
        name_to_tool_id[mcp_name] = tool_ref.tool_id
        description = tool_ref.description or f"Platform tool {tool_ref.tool_id}"
        tools.append(
            {
                "name": mcp_name,
                "description": f"[Tool] {description}",
                "inputSchema": tool_ref.effective_parameters_schema(),
            }
        )

    return tools, name_to_tool_id


def _session_context_key(mcp_session_id: str, flow_id: str) -> str:
    return f"agent_mcp_session:{mcp_session_id}:flow:{flow_id}"


def _device_session_context_key(device_id: str, flow_id: str) -> str:
    return f"agent_mcp_session:device:{device_id}:flow:{flow_id}"


async def _persist_sticky_context_id(
    container: FlowsContainerDep,
    *,
    mcp_session_id: str | None,
    device_id: str | None,
    flow_id: str,
    context_id: str,
) -> None:
    ttl_seconds = get_agent_settings().session_ttl_seconds
    if mcp_session_id is not None:
        _ = await container.redis_client.set(
            _session_context_key(mcp_session_id, flow_id),
            context_id,
            ttl=ttl_seconds,
        )
    if device_id is not None:
        _ = await container.redis_client.set(
            _device_session_context_key(device_id, flow_id),
            context_id,
            ttl=ttl_seconds,
        )


async def _resolve_flow_context_id(
    container: FlowsContainerDep,
    *,
    mcp_session_id: str | None,
    device_id: str | None,
    flow_id: str,
    explicit_context_id: str | None,
) -> str:
    """Sticky A2A context_id: explicit → MCP session → device → new UUID."""
    if explicit_context_id is not None:
        await _persist_sticky_context_id(
            container,
            mcp_session_id=mcp_session_id,
            device_id=device_id,
            flow_id=flow_id,
            context_id=explicit_context_id,
        )
        return explicit_context_id

    if mcp_session_id is not None:
        session_key = _session_context_key(mcp_session_id, flow_id)
        existing_session = await container.redis_client.get(session_key)
        if isinstance(existing_session, str) and existing_session.strip():
            await _persist_sticky_context_id(
                container,
                mcp_session_id=mcp_session_id,
                device_id=device_id,
                flow_id=flow_id,
                context_id=existing_session.strip(),
            )
            return existing_session.strip()

    if device_id is not None:
        device_key = _device_session_context_key(device_id, flow_id)
        existing_device = await container.redis_client.get(device_key)
        if isinstance(existing_device, str) and existing_device.strip():
            await _persist_sticky_context_id(
                container,
                mcp_session_id=mcp_session_id,
                device_id=device_id,
                flow_id=flow_id,
                context_id=existing_device.strip(),
            )
            return existing_device.strip()

    if mcp_session_id is None and device_id is None:
        logger.info("agent.platform_mcp.no_sticky_anchor", flow_id=flow_id)

    new_context_id = str(uuid.uuid4())
    await _persist_sticky_context_id(
        container,
        mcp_session_id=mcp_session_id,
        device_id=device_id,
        flow_id=flow_id,
        context_id=new_context_id,
    )
    return new_context_id


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
    device_id: str | None = None,
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
    metadata: JsonObject = {}
    if flow_id == _LARA_FLOW_ID:
        metadata["branch"] = _LINNEX_AGENT_BRANCH_ID
    variables: JsonObject = {"linnex_agent_client": "linnex_agent"}
    if device_id is not None:
        variables["device_id"] = device_id
    if flow_id == _LARA_FLOW_ID or device_id is not None:
        metadata["variables"] = variables
    params = MessageSendParams(message=a2a_message, metadata=metadata if metadata else None)
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


def _rpc_error(rpc_id: JsonValue, code: int, message: str) -> JsonObject:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


async def _handle_flow_tools_call(
    request: Request,
    container: FlowsContainerDep,
    *,
    rpc_id: JsonValue,
    tool_name: str,
    arguments: JsonObject,
    toolkit_id: str | None,
) -> JsonObject:
    flow_id = tool_name.removeprefix("flow_")
    active_context = require_context()
    active_company = active_context.active_company
    if active_company is None:
        return _rpc_error(rpc_id, -32603, "Компания не выбрана")
    allowed_flow_ids = await resolve_allowed_flow_ids(
        container.agent_toolkit_repository,
        toolkit_id=toolkit_id,
    )
    if flow_id not in allowed_flow_ids:
        return _rpc_error(
            rpc_id, -32602, f"Flow '{flow_id}' is not available for HumanitecAgent"
        )
    mcp_session_id = request.headers.get(_MCP_SESSION_HEADER)
    device_id = extract_device_id_from_bearer(request)
    context_id_raw = arguments.get("context_id")
    explicit_context_id: str | None = None
    if isinstance(context_id_raw, str) and context_id_raw.strip():
        explicit_context_id = context_id_raw.strip()
    sticky_context_id = await _resolve_flow_context_id(
        container,
        mcp_session_id=mcp_session_id,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=explicit_context_id,
    )

    flow_config = await container.flow_repository.get(flow_id)
    if flow_config is None:
        return _rpc_error(
            rpc_id, -32602, f"Flow '{flow_id}' is not available for HumanitecAgent"
        )
    user_message = arguments.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        return _rpc_error(rpc_id, -32602, "arguments.message is required")
    logger.info(
        "agent.platform_mcp.tools_call",
        flow_id=flow_id,
        device_id=device_id,
        branch=_LINNEX_AGENT_BRANCH_ID if flow_id == _LARA_FLOW_ID else None,
    )
    try:
        response_text, used_context_id, task_state = await _execute_flow_tool_call(
            container,
            flow_id=flow_id,
            user_message=user_message.strip(),
            context_id=sticky_context_id,
            device_id=device_id,
        )
    except HTTPException as exc:
        return _rpc_error(rpc_id, -32000, str(exc.detail))
    except ValueError as exc:
        return _rpc_error(rpc_id, -32000, str(exc))
    await _persist_sticky_context_id(
        container,
        mcp_session_id=mcp_session_id,
        device_id=device_id,
        flow_id=flow_id,
        context_id=used_context_id,
    )
    await record_agent_audit_event_redis(
        container.redis_client,
        company_id=active_company.company_id,
        event_type="agent.platform_mcp.tools_call",
        actor_user_id=active_context.user.user_id,
        device_id=device_id,
        detail=f"flow_id={flow_id}",
    )
    result_text = f"{response_text}\n\ncontext_id: {used_context_id}"
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
            "context_id": used_context_id,
            "task_state": task_state,
        },
    }


async def _handle_catalog_tools_call(
    container: FlowsContainerDep,
    *,
    rpc_id: JsonValue,
    tool_name: str,
    arguments: JsonObject,
    toolkit_id: str | None,
) -> JsonObject:
    _, name_to_tool_id = await _list_company_catalog_tools(container, toolkit_id=toolkit_id)
    tool_id = name_to_tool_id.get(tool_name)
    if tool_id is None:
        return _rpc_error(rpc_id, -32602, "Unsupported tool name")
    active_context = require_context()
    active_company = active_context.active_company
    if active_company is None:
        return _rpc_error(rpc_id, -32603, "Компания не выбрана")
    logger.info("agent.platform_mcp.tools_call", tool_id=tool_id)
    tool_context_id = str(uuid.uuid4())
    state = ExecutionState.create(
        task_id=str(uuid.uuid4()),
        context_id=tool_context_id,
        user_id=active_context.user.user_id,
        session_id=f"platform_mcp_tool:{tool_context_id}",
    )
    try:
        tool = await container.tool_registry.materialize({"tool_id": tool_id})
        result = await tool.run(arguments, state)
    except FlowInterrupt:
        return _rpc_error(rpc_id, -32000, f"Tool {tool_id!r} требует HITL и не поддержан в Platform MCP")
    except ValueError as exc:
        return _rpc_error(rpc_id, -32000, str(exc))
    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    await record_agent_audit_event_redis(
        container.redis_client,
        company_id=active_company.company_id,
        event_type="agent.platform_mcp.tools_call",
        actor_user_id=active_context.user.user_id,
        device_id=None,
        detail=f"tool_id={tool_id}",
    )
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        },
    }


@router.post("/agent/platform-mcp", tags=["agent-platform-mcp", "public"], response_model=None)
async def platform_mcp_message(
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject | Response:
    return await _platform_mcp_message_handler(request, container, toolkit_id=None)


@router.get(
    "/agent/platform-mcp/{toolkit_id}",
    tags=["agent-platform-mcp", "public"],
    response_model=None,
)
async def platform_mcp_discover_toolkit(
    toolkit_id: str,
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, container)
    toolkit = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    if toolkit is None:
        raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" in accept_header.lower():
        return Response(status_code=405)
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "serverInfo": {"name": toolkit.name, "version": "1.0.0"},
        "capabilities": _SERVER_CAPABILITIES,
    }


@router.post(
    "/agent/platform-mcp/{toolkit_id}",
    tags=["agent-platform-mcp", "public"],
    response_model=None,
)
async def platform_mcp_message_toolkit(
    toolkit_id: str,
    request: Request,
    container: FlowsContainerDep,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, container)
    toolkit = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    if toolkit is None:
        raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
    return await _platform_mcp_message_handler(request, container, toolkit_id=toolkit_id)


async def _platform_mcp_message_handler(
    request: Request,
    container: FlowsContainerDep,
    *,
    toolkit_id: str | None,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, container)
    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=400, detail="Пустое MCP сообщение")

    message = parse_json_object(raw_body.decode("utf-8"), "agent.platform_mcp.message")
    method = message.get("method")
    has_id = "id" in message
    rpc_id: JsonValue = message.get("id")

    if not has_id or (isinstance(method, str) and method.startswith("notifications/")):
        return Response(status_code=202)

    if method == "initialize":
        server_info: JsonObject = _SERVER_INFO
        if toolkit_id is not None:
            toolkit = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
            if toolkit is None:
                raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
            server_info = {"name": toolkit.name, "version": "1.0.0"}
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": _SERVER_CAPABILITIES,
                    "serverInfo": server_info,
                },
            },
            headers={_MCP_SESSION_HEADER: str(uuid.uuid4())},
        )

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {}}

    if method == "tools/list":
        flow_tools = await _list_company_flow_tools(container, toolkit_id=toolkit_id)
        catalog_tools, _ = await _list_company_catalog_tools(container, toolkit_id=toolkit_id)
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": [*flow_tools, *catalog_tools],
            },
        }

    if method == "tools/call":
        params_raw = message.get("params")
        params = require_json_object(params_raw, "agent.platform_mcp.params") if params_raw is not None else {}
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            return _rpc_error(rpc_id, -32602, "Unsupported tool name")
        arguments_raw = params.get("arguments")
        arguments = (
            require_json_object(arguments_raw, "agent.platform_mcp.arguments")
            if arguments_raw is not None
            else {}
        )
        if tool_name.startswith("flow_"):
            return await _handle_flow_tools_call(
                request,
                container,
                rpc_id=rpc_id,
                tool_name=tool_name,
                arguments=arguments,
                toolkit_id=toolkit_id,
            )
        if tool_name.startswith("tool_"):
            return await _handle_catalog_tools_call(
                container,
                rpc_id=rpc_id,
                tool_name=tool_name,
                arguments=arguments,
                toolkit_id=toolkit_id,
            )
        return _rpc_error(rpc_id, -32602, "Unsupported tool name")

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
                timeout_seconds=_DEVICE_MCP_TIMEOUT_SECONDS,
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
            return _rpc_error(rpc_id, -32603, "Компания не выбрана")
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
