"""MCP JSON-RPC endpoint for Search service."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from apps.search.di import Di
from core.context import get_context
from core.integrations.mcp import (
    MCP_PROTOCOL_VERSION,
    MCPInitializeResult,
    MCPJsonRpcError,
    MCPJsonRpcRequest,
    MCPJsonRpcResponse,
    MCPToolCallResult,
    MCPToolDefinition,
    MCPToolsListResult,
)
from core.models.identity_models import Company
from core.search import (
    MetaSearchRefineRequest,
    MetaSearchRequest,
    MetaSearchResponse,
    SearchResultInsightsRequest,
    SearchResultInsightsResponse,
    SearchSuggestRequest,
    SearchSuggestResponse,
)
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

router = APIRouter(prefix="/mcp", tags=["search-mcp"])


def _schema_for_model(model: type[BaseModel]) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.schema")


def _tools() -> list[MCPToolDefinition]:
    return [
        MCPToolDefinition(
            name="meta_web_search",
            title="Meta Web Search",
            description=(
                "Первичный web search через Search service. Провайдеры: TinyFish, Linkup, "
                "Serper/Google, Tavily; результат нормализован для flow: query, results, providers."
            ),
            parameters_schema=_schema_for_model(MetaSearchRequest),
            output_schema=_schema_for_model(MetaSearchResponse),
            annotations={
                "readOnlyHint": True,
                "openWorldHint": True,
            },
        ),
        MCPToolDefinition(
            name="refine_serp",
            title="Refine SERP",
            description=(
                "Доранжирование ранее закэшированного preview-пула SERP реранкером. "
                "Возвращает refined-порядок результатов для плавного reorder в UI."
            ),
            parameters_schema=_schema_for_model(MetaSearchRefineRequest),
            output_schema=_schema_for_model(MetaSearchResponse),
            annotations={
                "readOnlyHint": True,
                "openWorldHint": False,
            },
        ),
        MCPToolDefinition(
            name="search_suggest",
            title="Search Suggestions",
            description=(
                "Генерирует typed подсказки, уточнения и follow-up вопросы поверх "
                "нормализованной поисковой выдачи."
            ),
            parameters_schema=_schema_for_model(SearchSuggestRequest),
            output_schema=_schema_for_model(SearchSuggestResponse),
            annotations={
                "readOnlyHint": True,
                "openWorldHint": False,
            },
        ),
        MCPToolDefinition(
            name="search_result_insights",
            title="Search Result Insights",
            description=(
                "Генерирует typed per-result relevance hints и UI actions для SERP "
                "и поискового flow."
            ),
            parameters_schema=_schema_for_model(SearchResultInsightsRequest),
            output_schema=_schema_for_model(SearchResultInsightsResponse),
            annotations={
                "readOnlyHint": True,
                "openWorldHint": False,
            },
        ),
    ]


def _model_json_object(model: BaseModel) -> JsonObject:
    return require_json_object(
        model.model_dump(mode="json", by_alias=True, exclude_none=True),
        model.__class__.__name__,
    )


def _jsonrpc_payload(response: MCPJsonRpcResponse) -> JsonObject:
    return require_json_object(
        response.model_dump(mode="json", exclude_none=True),
        "MCPJsonRpcResponse",
    )


def _json_text_content(value: JsonValue) -> list[JsonObject]:
    return [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]


def _error(code: int, message: str, data: JsonObject | None = None) -> MCPJsonRpcError:
    return MCPJsonRpcError(code=code, message=message, data=data)


async def _tool_call(
    *,
    tool_name: str,
    arguments: JsonObject,
    di: Di,
    company: Company | None,
    user_id: str | None,
) -> MCPToolCallResult:
    if tool_name == "meta_web_search":
        request = MetaSearchRequest.model_validate(arguments)
        response = await di.meta_search_service.search(
            request,
            company=company,
            user_id=user_id,
        )
        payload = require_json_object(response.model_dump(mode="json"), "MetaSearchResponse")
        return MCPToolCallResult(
            content=_json_text_content(require_json_value(payload, "meta_web_search result")),
            structured_content=payload,
            is_error=False,
        )
    if tool_name == "refine_serp":
        refine_request = MetaSearchRefineRequest.model_validate(arguments)
        refine_response = await di.meta_search_service.refine(refine_request)
        payload = require_json_object(refine_response.model_dump(mode="json"), "MetaSearchResponse")
        return MCPToolCallResult(
            content=_json_text_content(require_json_value(payload, "refine_serp result")),
            structured_content=payload,
            is_error=False,
        )
    if tool_name == "search_suggest":
        request = SearchSuggestRequest.model_validate(arguments)
        response = di.search_suggestion_service.suggest(request)
        payload = require_json_object(response.model_dump(mode="json"), "SearchSuggestResponse")
        return MCPToolCallResult(
            content=_json_text_content(require_json_value(payload, "search_suggest result")),
            structured_content=payload,
            is_error=False,
        )
    if tool_name == "search_result_insights":
        request = SearchResultInsightsRequest.model_validate(arguments)
        response = di.search_result_insight_service.insights(request)
        payload = require_json_object(
            response.model_dump(mode="json"),
            "SearchResultInsightsResponse",
        )
        return MCPToolCallResult(
            content=_json_text_content(require_json_value(payload, "search_result_insights result")),
            structured_content=payload,
            is_error=False,
        )
    raise ValueError(f"Tool not found: {tool_name}")


@router.post("")
async def mcp_jsonrpc(
    req: MCPJsonRpcRequest,
    request: Request,
    response: Response,
    di: Di,
) -> JsonObject:
    method = req.method
    req_id = req.id
    params = req.params or {}

    if method == "initialize":
        mcp_session_id = response.headers.get("Mcp-Session-Id")
        if not mcp_session_id:
            response.headers["Mcp-Session-Id"] = str(uuid.uuid4())
        res = MCPInitializeResult(
            protocol_version=MCP_PROTOCOL_VERSION,
            capabilities={},
            server_info={"name": "platform-search", "version": "1.0.0"},
        )
        return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, result=_model_json_object(res)))

    protocol_header = request.headers.get("MCP-Protocol-Version")
    if protocol_header != MCP_PROTOCOL_VERSION:
        response.status_code = 400
        err = _error(-32000, "MCP-Protocol-Version header is required")
        return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, error=err))

    if method == "notifications/initialized":
        response.status_code = 202
        return {}

    if method == "tools/list":
        res = MCPToolsListResult(tools=_tools())
        result = require_json_object(
            res.model_dump(mode="json", by_alias=True, exclude_none=True),
            "MCPToolsListResult",
        )
        return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, result=result))

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or not name.strip():
            err = _error(-32602, "tools/call: params.name is required")
            return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, error=err))
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            err = _error(-32602, "tools/call: params.arguments must be object")
            return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, error=err))
        arguments_obj = require_json_object(arguments, "tools/call.params.arguments")
        try:
            context = get_context()
            company = context.active_company if context is not None else None
            user_id = context.user.user_id if context is not None else None
            async with traced_operation(
                "search.mcp.tool_call",
                event_type="mcp.tool_call",
                operation_category="mcp",
                extra_attributes={
                    "platform.mcp.tool_name": name.strip(),
                    "platform.mcp.source": "search",
                    "platform.mcp.tool_args_keys": ",".join(sorted(arguments_obj.keys())[:50]),
                },
            ) as span:
                call_res = await _tool_call(
                    tool_name=name,
                    arguments=arguments_obj,
                    di=di,
                    company=company,
                    user_id=user_id,
                )
                span.set_attribute("platform.mcp.tool_result_is_error", bool(call_res.is_error))
        except Exception as exc:
            err = _error(-32000, str(exc), data={"tool": name})
            return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, error=err))
        return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, result=_model_json_object(call_res)))

    err = _error(-32601, f"Method not found: {method}")
    return _jsonrpc_payload(MCPJsonRpcResponse(id=req_id, error=err))
