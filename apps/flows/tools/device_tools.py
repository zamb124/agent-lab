"""Builtin tools: вызов локальных MCP tools LinnexAgent через tunnel."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.agent.tunnel_bus import send_mcp_request_to_device
from apps.flows.src.container_state import require_current_container
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

_DEVICE_TOOL_TIMEOUT_SECONDS = 120.0


class DeviceToolsListArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class DeviceToolsCallArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Имя локального MCP tool на устройстве")
    arguments: JsonObject = Field(
        default_factory=dict,
        description="Аргументы локального MCP tool (JSON object)",
    )


def _require_device_id(state: "ExecutionState") -> str:
    variables = state.variables
    device_id_raw = variables.get("device_id")
    if not isinstance(device_id_raw, str) or not device_id_raw.strip():
        raise ValueError(
            "device_id is missing in execution variables; "
            + "bind an online LinnexAgent device to the session "
            + "(user must have an active tunnel)"
        )
    return device_id_raw.strip()


@tool(
    name="device_tools_list",
    description=(
        "List MCP tools available on the user's LinnexAgent desktop (local PC) "
        "via the device tunnel. Call before device_tools_call when unsure which "
        "local tools exist. Fails if the device tunnel is offline."
    ),
    tags=["device"],
    parameters_model=DeviceToolsListArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def device_tools_list(*, state: "ExecutionState") -> JsonObject:
    device_id = _require_device_id(state)
    container = require_current_container()
    result = await send_mcp_request_to_device(
        container.redis_client,
        device_id,
        method="tools/list",
        params={},
        timeout_seconds=_DEVICE_TOOL_TIMEOUT_SECONDS,
    )
    return {
        "success": True,
        "device_id": device_id,
        "result": result,
    }


@tool(
    name="device_tools_call",
    description=(
        "Call a local MCP tool on the user's LinnexAgent desktop through the tunnel. "
        "Use device_tools_list first for available names. device_id comes from the "
        "session (cannot be overridden). Honors DevicePolicy on the desktop."
    ),
    tags=["device"],
    parameters_model=DeviceToolsCallArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def device_tools_call(
    name: str,
    arguments: JsonObject | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    device_id = _require_device_id(state)
    tool_name = name.strip()
    if not tool_name:
        raise ValueError("name is required")
    call_arguments = arguments if arguments is not None else {}
    _ = require_json_object(call_arguments, "device_tools_call.arguments")
    container = require_current_container()
    result = await send_mcp_request_to_device(
        container.redis_client,
        device_id,
        method="tools/call",
        params={"name": tool_name, "arguments": call_arguments},
        timeout_seconds=_DEVICE_TOOL_TIMEOUT_SECONDS,
    )
    return {
        "success": True,
        "device_id": device_id,
        "name": tool_name,
        "result": result,
    }
