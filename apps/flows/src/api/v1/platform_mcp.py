"""
Platform MCP endpoint для HumanitecAgent / LinnexAgent.

Полноценный Streamable HTTP MCP-сервер: lifecycle (initialize/ping/notifications),
flow компании как tools ``flow_{flow_id}`` и каталог тулов компании как
``tool_{tool_id}``. Session continuity flow — sticky A2A context_id по
``Mcp-Session-Id`` или device JWT (LaraOnly).
"""

import json
import uuid

from a2a.types import Message, Part, SendMessageRequest
from a2a.types.a2a_pb2 import ROLE_USER
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from google.protobuf.json_format import MessageToDict

from apps.agent.service import (
    build_flow_mcp_tools,
    device_tunnel_is_online,
    record_agent_audit_event_redis,
)
from apps.agent.tunnel_bus import send_mcp_request_to_device
from apps.flows.di import Di
from apps.flows.src.agent.device_auth import (
    extract_device_id_from_bearer,
    reject_revoked_device_bearer_if_present,
)
from apps.flows.src.channels.factory import get_channel
from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.agent_toolkit_service import (
    resolve_allowed_flow_ids,
    resolve_allowed_tool_ids,
)
from apps.flows.src.tools.base import sanitize_tool_name
from core.a2a import (
    extract_text_from_task_json,
    struct_from_mapping,
    wire_task_state_to_platform,
)
from core.config import get_settings
from core.context import get_context, require_context
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from core.websocket import WsCommandError

logger = get_logger(__name__)
router = APIRouter(tags=["agent-platform-mcp"])

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO: JsonObject = {"name": "Humanitec Platform MCP", "version": "1.0.0"}
_SERVER_CAPABILITIES: JsonObject = {"tools": {}}
_MCP_SESSION_HEADER = "Mcp-Session-Id"
_LARA_FLOW_ID = "lara"
_LINNEX_AGENT_BRANCH_ID = "linnex_agent"
_DEVICE_MCP_TIMEOUT_SECONDS = 120.0
_LARA_TOOLKIT_MCP_INSTRUCTIONS = (
    "Lara is the company platform assistant. "
    "For NetWorkle/CRM, Flows, Sync, documents, RAG, Worktracker, console, billing, "
    "AI settings, or any platform question: call tool flow_lara with the user's full question. "
    "Do not invent platform answers without a successful flow_lara result. "
    "Local PC files/shell/browser: prefer flow_lara (Lara device tools); "
    "use local developer tools only for clearly local machine tasks."
)


def _mcp_initialize_instructions(*, toolkit_id: str | None) -> str | None:
    if toolkit_id == _LARA_FLOW_ID:
        return _LARA_TOOLKIT_MCP_INSTRUCTIONS
    return None


async def _reject_revoked_device_bearer(request: Request, di: Di) -> None:
    await reject_revoked_device_bearer_if_present(request, di.shared_storage)


@router.get("/agent/platform-mcp", tags=["agent-platform-mcp", "public"], response_model=None)
async def platform_mcp_discover(
    request: Request,
    di: Di,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, di)
    _ = di
    accept_header = request.headers.get("accept", "")
    if "text/event-stream" in accept_header.lower():
        return Response(status_code=405)
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "serverInfo": _SERVER_INFO,
        "capabilities": _SERVER_CAPABILITIES,
    }


async def _list_company_flow_tools(
    *,
    toolkit_id: str | None,
) -> list[JsonObject]:
    context = require_context()
    company = context.active_company
    if company is None:
        return []

    allowed_flow_ids = await resolve_allowed_flow_ids(
        toolkit_id=toolkit_id,
    )
    if not allowed_flow_ids:
        return []

    flows = await FlowConfig.list_current(limit=500, offset=0)
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
    di: Di,
    *,
    toolkit_id: str | None,
) -> tuple[list[JsonObject], dict[str, str]]:
    """Каталог тулов компании как MCP tools ``tool_{tool_id}`` + индекс name -> tool_id."""
    allowed_tool_ids = await resolve_allowed_tool_ids(
        toolkit_id=toolkit_id,
    )
    if not allowed_tool_ids:
        return [], {}

    registry = di.tool_registry
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

    for tool_ref in await ToolReference.list_in_tool_id_order(limit=10000):
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
    di: Di,
    *,
    mcp_session_id: str | None,
    device_id: str | None,
    flow_id: str,
    context_id: str,
) -> None:
    """Persist sticky context. MCP session wins over device (no cross-dialog reuse)."""
    ttl_seconds = get_settings().agent.session_ttl_seconds
    if mcp_session_id is not None:
        _ = await di.redis_client.set(
            _session_context_key(mcp_session_id, flow_id),
            context_id,
            ttl=ttl_seconds,
        )
        return
    if device_id is not None:
        _ = await di.redis_client.set(
            _device_session_context_key(device_id, flow_id),
            context_id,
            ttl=ttl_seconds,
        )


async def _resolve_flow_context_id(
    di: Di,
    *,
    mcp_session_id: str | None,
    device_id: str | None,
    flow_id: str,
    explicit_context_id: str | None,
) -> str:
    """Sticky A2A context_id: explicit → MCP session → device (only without MCP session) → new UUID.

    New Mcp-Session-Id always gets a new context_id (new LinnexAgent dialog ≠ old Lara session).
    Device sticky key is used only when the caller omits Mcp-Session-Id.
    """
    if explicit_context_id is not None:
        await _persist_sticky_context_id(
            di,
            mcp_session_id=mcp_session_id,
            device_id=device_id,
            flow_id=flow_id,
            context_id=explicit_context_id,
        )
        return explicit_context_id

    if mcp_session_id is not None:
        session_key = _session_context_key(mcp_session_id, flow_id)
        existing_session = await di.redis_client.get(session_key)
        if isinstance(existing_session, str) and existing_session.strip():
            await _persist_sticky_context_id(
                di,
                mcp_session_id=mcp_session_id,
                device_id=None,
                flow_id=flow_id,
                context_id=existing_session.strip(),
            )
            return existing_session.strip()
        new_context_id = str(uuid.uuid4())
        await _persist_sticky_context_id(
            di,
            mcp_session_id=mcp_session_id,
            device_id=None,
            flow_id=flow_id,
            context_id=new_context_id,
        )
        return new_context_id

    if device_id is not None:
        device_key = _device_session_context_key(device_id, flow_id)
        existing_device = await di.redis_client.get(device_key)
        if isinstance(existing_device, str) and existing_device.strip():
            await _persist_sticky_context_id(
                di,
                mcp_session_id=None,
                device_id=device_id,
                flow_id=flow_id,
                context_id=existing_device.strip(),
            )
            return existing_device.strip()

    logger.info("agent.platform_mcp.no_sticky_anchor", flow_id=flow_id)
    new_context_id = str(uuid.uuid4())
    await _persist_sticky_context_id(
        di,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        context_id=new_context_id,
    )
    return new_context_id


def _extract_task_text(task_payload: JsonObject) -> str:
    try:
        return extract_text_from_task_json(task_payload)
    except ValueError as exc:
        raise ValueError("Flow task has no text response") from exc


def _extract_task_state(task_payload: JsonObject) -> str:
    """A2A Task.status.state (ProtoJSON) → platform kebab `task_state`."""
    status_raw = task_payload.get("status")
    if not isinstance(status_raw, dict):
        raise ValueError("Flow task status missing")
    state = status_raw.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("Flow task status.state missing")
    return wire_task_state_to_platform(state)


async def _execute_flow_tool_call(
    di: Di,
    *,
    flow_id: str,
    user_message: str,
    context_id: str | None = None,
    device_id: str | None = None,
) -> tuple[str, str, str]:
    flow_config = await FlowConfig.get_latest(flow_id)
    if flow_config is None:
        raise WsCommandError(
            "not_found",
            f"flow {flow_id!r} not found",
            error_code="flow_not_found",
            error_params={"flow_id": flow_id},
        )

    context = get_context()
    if context is None:
        raise WsCommandError(
            "unauthorized",
            "context is not set",
            error_code="context_not_set",
        )

    message_id = str(uuid.uuid4())
    resolved_context_id = context_id if context_id is not None else str(uuid.uuid4())
    a2a_message = Message(
        role=ROLE_USER,
        message_id=message_id,
        context_id=resolved_context_id,
        parts=[Part(text=user_message)],
    )
    metadata: JsonObject = {}
    if flow_id == _LARA_FLOW_ID:
        metadata["branch"] = _LINNEX_AGENT_BRANCH_ID
    variables: JsonObject = {"linnex_agent_client": "linnex_agent"}
    if device_id is not None:
        variables["device_id"] = device_id
    if flow_id == _LARA_FLOW_ID or device_id is not None:
        metadata["variables"] = variables
    params = SendMessageRequest(message=a2a_message)
    if metadata:
        params.metadata.CopyFrom(struct_from_mapping(metadata))
    channel = get_channel(
        "a2a",
        flow_id,
        context,
        variables_service=di.variables_service,
        authz_service=di.authz_service,
        workflow_runtime=di.workflow_runtime,
        redis_client=di.redis_client,
        handoff_orchestrator_service=di.handoff_orchestrator_service,
        flow_factory=di.flow_factory,
        tool_registry=di.tool_registry,
        projection_service=di.a2a_task_projection_service,
        shared_storage=di.shared_storage,
        channel_registry=di.channel_registry,
        mail_service=di.mail_service,
        flow_ui_share_service=di.flow_ui_share_service,
        hitl_conversation_service=di.hitl_conversation_service,
        files_service=di.files_service,
    )
    task = await channel.on_message_send(params)
    task_payload = require_json_object(MessageToDict(task), "task.payload")
    task_state = _extract_task_state(task_payload)
    if task_state == "failed":
        try:
            fail_text = extract_text_from_task_json(task_payload)
        except ValueError:
            fail_text = None
        if fail_text is not None:
            raise WsCommandError(
                "internal",
                fail_text,
                error_code="flow_task_failed",
            )
        raise WsCommandError(
            "internal",
            "flow task failed",
            error_code="flow_task_failed",
        )
    response_text = _extract_task_text(task_payload)
    return response_text, resolved_context_id, task_state


def _rpc_error(rpc_id: JsonValue, code: int, message: str) -> JsonObject:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


async def _handle_flow_tools_call(
    request: Request,
    di: Di,
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
        di,
        mcp_session_id=mcp_session_id,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=explicit_context_id,
    )

    flow_config = await FlowConfig.get_latest(flow_id)
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
            di,
            flow_id=flow_id,
            user_message=user_message.strip(),
            context_id=sticky_context_id,
            device_id=device_id,
        )
    except WsCommandError as exc:
        return _rpc_error(rpc_id, -32000, exc.detail)
    except ValueError as exc:
        return _rpc_error(rpc_id, -32000, str(exc))
    await _persist_sticky_context_id(
        di,
        mcp_session_id=mcp_session_id,
        device_id=device_id,
        flow_id=flow_id,
        context_id=used_context_id,
    )
    await record_agent_audit_event_redis(
        di.redis_client,
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
    di: Di,
    *,
    rpc_id: JsonValue,
    tool_name: str,
    arguments: JsonObject,
    toolkit_id: str | None,
) -> JsonObject:
    _, name_to_tool_id = await _list_company_catalog_tools(di, toolkit_id=toolkit_id)
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
        tool = await di.tool_registry.materialize({"tool_id": tool_id})
        result = await tool.run(arguments, state)
    except FlowInterrupt:
        return _rpc_error(rpc_id, -32000, f"Tool {tool_id!r} требует HITL и не поддержан в Platform MCP")
    except ValueError as exc:
        return _rpc_error(rpc_id, -32000, str(exc))
    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    await record_agent_audit_event_redis(
        di.redis_client,
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
    di: Di,
) -> JsonObject | Response:
    return await _platform_mcp_message_handler(request, di, toolkit_id=None)


@router.get(
    "/agent/platform-mcp/{toolkit_id}",
    tags=["agent-platform-mcp", "public"],
    response_model=None,
)
async def platform_mcp_discover_toolkit(
    toolkit_id: str,
    request: Request,
    di: Di,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, di)
    toolkit = await AgentToolkit.by_toolkit_id(toolkit_id)
    if toolkit is None:
        raise WsCommandError(
            "not_found",
            f"toolkit {toolkit_id!r} not found",
            error_code="toolkit_not_found",
            error_params={"toolkit_id": toolkit_id},
        )
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
    di: Di,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, di)
    toolkit = await AgentToolkit.by_toolkit_id(toolkit_id)
    if toolkit is None:
        raise WsCommandError(
            "not_found",
            f"toolkit {toolkit_id!r} not found",
            error_code="toolkit_not_found",
            error_params={"toolkit_id": toolkit_id},
        )
    return await _platform_mcp_message_handler(request, di, toolkit_id=toolkit_id)


async def _platform_mcp_message_handler(
    request: Request,
    di: Di,
    *,
    toolkit_id: str | None,
) -> JsonObject | Response:
    await _reject_revoked_device_bearer(request, di)
    raw_body = await request.body()
    if not raw_body:
        raise WsCommandError(
            "ws_invalid_payload",
            "MCP message is empty",
            error_code="mcp_message_empty",
        )

    message = parse_json_object(raw_body.decode("utf-8"), "agent.platform_mcp.message")
    method = message.get("method")
    has_id = "id" in message
    rpc_id: JsonValue = message.get("id")

    if not has_id or (isinstance(method, str) and method.startswith("notifications/")):
        return Response(status_code=202)

    if method == "initialize":
        server_info: JsonObject = _SERVER_INFO
        if toolkit_id is not None:
            toolkit = await AgentToolkit.by_toolkit_id(toolkit_id)
            if toolkit is None:
                raise WsCommandError(
            "not_found",
            f"toolkit {toolkit_id!r} not found",
            error_code="toolkit_not_found",
            error_params={"toolkit_id": toolkit_id},
        )
            server_info = {"name": toolkit.name, "version": "1.0.0"}
        initialize_result: JsonObject = {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": _SERVER_CAPABILITIES,
            "serverInfo": server_info,
        }
        instructions = _mcp_initialize_instructions(toolkit_id=toolkit_id)
        if instructions is not None:
            initialize_result["instructions"] = instructions
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": initialize_result,
            },
            headers={_MCP_SESSION_HEADER: str(uuid.uuid4())},
        )

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {}}

    if method == "tools/list":
        flow_tools = await _list_company_flow_tools(toolkit_id=toolkit_id)
        catalog_tools, _ = await _list_company_catalog_tools(di, toolkit_id=toolkit_id)
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
                di,
                rpc_id=rpc_id,
                tool_name=tool_name,
                arguments=arguments,
                toolkit_id=toolkit_id,
            )
        if tool_name.startswith("tool_"):
            return await _handle_catalog_tools_call(
                di,
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
        if not await device_tunnel_is_online(di.shared_storage, device_id):
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32000,
                    "message": f"Device tunnel offline: {device_id}",
                },
            }
        try:
            device_result = await send_mcp_request_to_device(
                di.redis_client,
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
            di.redis_client,
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
