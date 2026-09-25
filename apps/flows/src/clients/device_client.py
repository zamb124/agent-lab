"""DeviceClient — MCP tunnel к LinnexAgent desktop для device_* tools."""

from __future__ import annotations

from apps.agent.tunnel_bus import send_mcp_request_to_device
from core.clients.redis_client import RedisClient
from core.types import JsonObject


class DeviceClient:
    """tools/list и tools/call через device tunnel."""

    _redis_client: RedisClient

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    async def tools_list(
        self,
        device_id: str,
        *,
        timeout_seconds: float,
    ) -> JsonObject:
        return await send_mcp_request_to_device(
            self._redis_client,
            device_id,
            method="tools/list",
            params={},
            timeout_seconds=timeout_seconds,
        )

    async def tools_call(
        self,
        device_id: str,
        *,
        name: str,
        arguments: JsonObject,
        timeout_seconds: float,
    ) -> JsonObject:
        return await send_mcp_request_to_device(
            self._redis_client,
            device_id,
            method="tools/call",
            params={"name": name, "arguments": arguments},
            timeout_seconds=timeout_seconds,
        )
