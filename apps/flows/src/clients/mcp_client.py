"""Строгий MCP 2025-11-25 JSON-RPC клиент."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

import httpx

from apps.flows.src.models.mcp import (
    MCPCallResult,
    MCPDiscoveredTool,
    MCPInitializeResult,
    MCPServerConfig,
    MCPToolDefinition,
)
from apps.flows.src.services.browser_preview import emit_browser_preview_mcp_event
from core.http import ProxyStrategy, get_httpx_client
from core.integrations.mcp import MCP_PROTOCOL_VERSION
from core.logging import get_logger
from core.tracing.attributes import (
    ATTR_MCP_HAS_SESSION,
    ATTR_MCP_METHOD,
    ATTR_MCP_NOTIFICATION,
    ATTR_MCP_PROTOCOL_VERSION,
    ATTR_MCP_REQUEST_PREVIEW,
    ATTR_MCP_RESPONSE_BYTES,
    ATTR_MCP_RESPONSE_CONTENT_TYPE,
    ATTR_MCP_RESPONSE_PREVIEW,
    ATTR_MCP_RESPONSE_SESSION_ID,
    ATTR_MCP_RESPONSE_SHA256,
    ATTR_MCP_SERVER_ID,
    ATTR_MCP_TOOL_ARGS_KEYS,
    ATTR_MCP_TOOL_NAME,
)
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object
from core.variables import VarResolver

logger = get_logger(__name__)

_TRACE_TEXT_LIMIT = 2000


class MCPClientError(Exception):
    """Ошибка MCP-клиента."""


class MCPClient:
    """MCP Streamable HTTP клиент со строгими контрактами 2025-11-25."""

    def __init__(
        self,
        config: MCPServerConfig,
        variables: Mapping[str, JsonValue] | None = None,
        timeout: float = 60.0,
    ) -> None:
        variables_copy: dict[str, JsonValue] = dict(variables) if variables is not None else {}
        self.config: MCPServerConfig = config
        self._variables: Mapping[str, JsonValue] = MappingProxyType(variables_copy)
        self.timeout: float = timeout
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._request_id: int = 0
        self._initialized: bool = False
        self._initialize_result: MCPInitializeResult | None = None

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _active_protocol_version(self) -> str:
        if self.protocol_version is None:
            raise RuntimeError("MCP client is not initialized")
        return self.protocol_version

    def _resolve_headers(
        self,
        *,
        include_session: bool,
        include_protocol_version: bool,
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if include_protocol_version:
            headers["MCP-Protocol-Version"] = self._active_protocol_version()
        if include_session and self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id

        for key, value in self.config.headers.items():
            headers[key] = VarResolver.resolve_text(value, self._variables)
        return headers

    @staticmethod
    def _jsonrpc_envelope_from_body(text: str) -> JsonObject | None:
        if not text or not text.strip():
            return None
        source = text.strip()
        if source.startswith("{"):
            try:
                envelope = require_json_object(
                    cast(JsonValue, json.loads(source)),
                    "MCP JSON-RPC envelope",
                )
            except (json.JSONDecodeError, ValueError):
                envelope = None
            else:
                if (
                    envelope.get("jsonrpc") == "2.0"
                    or "result" in envelope
                    or "error" in envelope
                ):
                    return envelope
        for line in source.splitlines():
            item = line.strip()
            if not item:
                continue
            if not item.lower().startswith("data:"):
                continue
            payload = item[5:].lstrip()
            if not payload or payload == "[DONE]":
                continue
            try:
                envelope = require_json_object(
                    cast(JsonValue, json.loads(payload)),
                    "MCP SSE JSON-RPC envelope",
                )
            except (json.JSONDecodeError, ValueError):
                continue
            if (
                envelope.get("jsonrpc") == "2.0"
                or "result" in envelope
                or "error" in envelope
            ):
                return envelope
        return None

    @staticmethod
    def _trace_text(value: JsonValue, *, limit: int = _TRACE_TEXT_LIMIT) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            raw = value.encode("unicode_escape", errors="backslashreplace").decode(
                "ascii",
                errors="replace",
            )
        else:
            raw = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "...[truncated]"

    @staticmethod
    def _sha256_hex(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    async def _read_response_text(response: httpx.Response) -> str:
        _ = await response.aread()
        return response.text

    async def _post_jsonrpc(
        self,
        *,
        method: str,
        payload: JsonObject,
        include_session: bool,
        include_protocol_version: bool,
        notification: bool,
    ) -> tuple[JsonObject | None, httpx.Headers, int, str]:
        headers = self._resolve_headers(
            include_session=include_session,
            include_protocol_version=include_protocol_version,
        )
        operation_name = "flows.mcp.tool_call" if method == "tools/call" else "flows.mcp.rpc_call"
        event_type = "mcp.tool_call" if method == "tools/call" else "mcp.rpc_call"

        async with traced_operation(
            operation_name,
            event_type=event_type,
            operation_category="mcp",
            extra_attributes={
                ATTR_MCP_SERVER_ID: self.config.server_id,
                ATTR_MCP_METHOD: method,
                ATTR_MCP_PROTOCOL_VERSION: (
                    self.protocol_version if self.protocol_version is not None else ""
                ),
                ATTR_MCP_HAS_SESSION: bool(self.session_id) if include_session else False,
                ATTR_MCP_NOTIFICATION: notification,
                ATTR_MCP_REQUEST_PREVIEW: MCPClient._trace_text(payload),
            },
        ) as span:
            params_raw = payload.get("params")
            if method == "tools/call" and isinstance(params_raw, dict):
                raw_name = params_raw.get("name")
                raw_args = params_raw.get("arguments")
                if isinstance(raw_name, str) and raw_name.strip():
                    span.set_attribute(ATTR_MCP_TOOL_NAME, raw_name.strip())
                if isinstance(raw_args, dict):
                    keys = sorted(str(key) for key in raw_args.keys())
                    span.set_attribute(ATTR_MCP_TOOL_ARGS_KEYS, ",".join(keys[:50]))

            async with get_httpx_client(
                timeout=self.timeout,
                strategy=ProxyStrategy.DIRECT_ONLY,
            ) as client:
                response = await client.post(
                    self.config.url,
                    json=payload,
                    headers=headers,
                )
                response_headers = response.headers
                text = await self._read_response_text(response)
                content_type = cast(str, response.headers.get("content-type", ""))

                span.set_attribute("http.status_code", int(response.status_code))
                span.set_attribute(ATTR_MCP_RESPONSE_CONTENT_TYPE, content_type.strip())
                span.set_attribute(
                    ATTR_MCP_RESPONSE_BYTES,
                    len(text.encode("utf-8", errors="replace")),
                )
                span.set_attribute(ATTR_MCP_RESPONSE_SHA256, MCPClient._sha256_hex(text))
                span.set_attribute(ATTR_MCP_RESPONSE_PREVIEW, MCPClient._trace_text(text))
                sid = cast(
                    str | None,
                    response_headers.get("mcp-session-id"),
                )
                if sid is not None and sid.strip():
                    span.set_attribute(ATTR_MCP_RESPONSE_SESSION_ID, sid.strip())

                return (
                    self._jsonrpc_envelope_from_body(text),
                    response_headers,
                    int(response.status_code),
                    text,
                )

    async def _rpc_call(
        self,
        method: str,
        params: JsonObject | None = None,
        *,
        include_session: bool = True,
        include_protocol_version: bool = True,
    ) -> tuple[JsonValue, httpx.Headers]:
        request_id = self._next_request_id()
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        envelope, headers, status_code, text = await self._post_jsonrpc(
            method=method,
            payload=payload,
            include_session=include_session,
            include_protocol_version=include_protocol_version,
            notification=False,
        )
        if status_code >= 400:
            raise MCPClientError(f"MCP HTTP error: {status_code} {text}")
        if envelope is None:
            raise MCPClientError(
                f"MCP: empty response for {method} (status={status_code}, body={text[:500]!r})"
            )

        error_raw = envelope.get("error")
        if error_raw is not None:
            error = require_json_object(error_raw, "MCP RPC error")
            raise MCPClientError(
                f"MCP RPC error: {error.get('code')} - {error.get('message')}"
            )

        return envelope.get("result"), headers

    async def _rpc_notification(
        self,
        method: str,
        params: JsonObject | None = None,
    ) -> None:
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        envelope, _headers, status_code, text = await self._post_jsonrpc(
            method=method,
            payload=payload,
            include_session=True,
            include_protocol_version=True,
            notification=True,
        )
        if status_code >= 400:
            raise MCPClientError(f"MCP notification HTTP error: {status_code} {text}")
        if envelope is None:
            return
        error_raw = envelope.get("error")
        if error_raw is not None:
            error = require_json_object(error_raw, "MCP notification error")
            raise MCPClientError(
                f"MCP notification error: {error.get('code')} - {error.get('message')}"
            )

    async def initialize(self) -> MCPInitializeResult:
        if self._initialized:
            if self._initialize_result is None:
                raise RuntimeError("MCP client initialized without initialize result")
            return self._initialize_result

        raw_result, headers = await self._rpc_call(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "agent-lab",
                    "version": "1.0.0",
                },
            },
            include_session=False,
            include_protocol_version=False,
        )
        result = MCPInitializeResult.model_validate(
            require_json_object(raw_result, "MCP initialize result")
        )
        self.protocol_version = result.protocol_version
        session_id = cast(
            str | None,
            headers.get("mcp-session-id"),
        )
        self.session_id = session_id.strip() if session_id is not None and session_id.strip() else None
        self._initialize_result = result
        self._initialized = True
        await self._rpc_notification("notifications/initialized")
        logger.info("MCP session initialized: server_id=%s session=%s", self.config.server_id, self.session_id)
        return result

    async def list_tools(self) -> list[MCPDiscoveredTool]:
        if not self._initialized:
            _ = await self.initialize()

        raw_result, _headers = await self._rpc_call("tools/list")
        result = require_json_object(raw_result, "MCP tools/list result")
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise MCPClientError("MCP tools/list result.tools must be an array")

        schema_version = self._active_protocol_version()
        tools: list[MCPDiscoveredTool] = []
        for index, tool_data in enumerate(raw_tools):
            definition = MCPToolDefinition.from_wire(
                require_json_object(tool_data, f"MCP tools[{index}]")
            )
            tools.append(
                definition.to_discovered(
                    server_id=self.config.server_id,
                    schema_version=schema_version,
                )
            )

        logger.info("MCP server %s: %s tools available", self.config.server_id, len(tools))
        return tools

    async def require_tool_contract(
        self,
        tool_name: str,
        *,
        expected_schema_hash: str,
        expected_schema_version: str,
    ) -> MCPDiscoveredTool:
        for discovered in await self.list_tools():
            if discovered.tool_name != tool_name:
                continue
            if discovered.schema_version != expected_schema_version:
                raise MCPClientError(
                    "MCP tool schema_version mismatch for "
                    + f"{self.config.server_id}/{tool_name}: expected "
                    + f"{expected_schema_version!r}, got {discovered.schema_version!r}"
                )
            if discovered.schema_hash != expected_schema_hash:
                raise MCPClientError(
                    "MCP tool schema_hash mismatch for "
                    + f"{self.config.server_id}/{tool_name}: expected "
                    + f"{expected_schema_hash!r}, got {discovered.schema_hash!r}"
                )
            return discovered
        raise MCPClientError(f"MCP tool not found: {self.config.server_id}/{tool_name}")

    async def call_tool(self, tool_name: str, arguments: JsonObject) -> MCPCallResult:
        if not tool_name.strip():
            raise MCPClientError("MCP tool_name is required")
        if not self._initialized:
            _ = await self.initialize()
        args = require_json_object(arguments, "MCP tool arguments")

        await emit_browser_preview_mcp_event(
            config=self.config,
            tool_name=tool_name,
            arguments=args,
            phase="started",
        )
        try:
            raw_result, _headers = await self._rpc_call(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": args,
                },
            )
        except Exception as exc:
            await emit_browser_preview_mcp_event(
                config=self.config,
                tool_name=tool_name,
                arguments=args,
                phase="failed",
                error=str(exc),
            )
            raise

        result = MCPCallResult.model_validate(
            require_json_object(raw_result, "MCP tools/call result")
        )
        await emit_browser_preview_mcp_event(
            config=self.config,
            tool_name=tool_name,
            arguments=args,
            phase="failed" if result.is_error else "finished",
            result=result,
        )
        return result


async def get_mcp_client(
    config: MCPServerConfig,
    variables: Mapping[str, JsonValue] | None = None,
    timeout: float = 60.0,
) -> MCPClient:
    client = MCPClient(config, variables, timeout)
    _ = await client.initialize()
    return client
