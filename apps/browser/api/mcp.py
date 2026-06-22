"""
MCP JSON-RPC 2.0 endpoint для Browser Runtime.

Назначение:
- Экспортировать Browser Control как MCP server, чтобы flows могли использовать browser как `type="mcp"`.

Методы:
- initialize
- tools/list
- tools/call

URL:
- `/browser/api/v1/mcp` (см. `apps/browser/main.py`).
"""

from __future__ import annotations

import json
import uuid
from html.parser import HTMLParser
from typing import ClassVar, Literal, override
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from apps.browser.api.control import (
    ContextSignatureBody,
    ControlClickBody,
    ControlFillBody,
    ControlNavigateBody,
    ControlObserveBody,
    ControlPressBody,
    ControlSaveStateBody,
    ControlSessionCreateBody,
    ControlWaitBody,
    control_click,
    control_fill,
    control_navigate,
    control_observe,
    control_press,
    control_wait,
    create_control_session,
    delete_control_session,
    save_control_session_state,
    wait_for_agent_control,
)
from apps.browser.container import BrowserContainer
from apps.browser.dependencies import ContainerDep
from apps.browser.engine.types import ContextSignature
from apps.browser.interaction.interaction_profiles import (
    InteractionProfileName,
    get_interaction_profile,
)
from core.clients.browser import (
    ToolCloseSessionArgs,
    ToolCreateSessionArgs,
    ToolNavigateArgs,
    ToolObserveArgs,
    ToolSaveStateArgs,
)
from core.integrations.mcp import MCP_PROTOCOL_VERSION, MCPToolDefinition
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object, require_json_value

router = APIRouter(prefix="/mcp", tags=["browser-mcp"])

AntiBotTier = Literal["white", "gray", "black"]


class JsonRpcRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: JsonObject | None = None


class JsonRpcError(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    code: int
    message: str
    data: JsonObject | None = None


class JsonRpcResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    result: JsonObject | None = None
    error: JsonRpcError | None = None


class McpInitializeResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    protocolVersion: str
    capabilities: JsonObject
    serverInfo: JsonObject


class McpToolsListResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    tools: list[MCPToolDefinition]


class McpToolCallResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    content: list[JsonObject]
    isError: bool = False


class ToolClickArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    ref: str
    timeout_ms: int = Field(default=10_000, ge=1000)


class ToolFillArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    ref: str
    text: str
    timeout_ms: int = Field(default=10_000, ge=1000)
    typing_delay_ms: int | None = Field(default=None, ge=0)


class ToolPressArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    key: str


class ToolWaitArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    selector: str | None = None
    load_state: Literal["domcontentloaded", "networkidle"] | None = None
    timeout_ms: int = Field(default=30_000, ge=1000)


class ToolSaveHtmlToS3Args(BaseModel): # убрать костыль
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    original_name: str = "snapshot.html"
    links_limit: int = Field(default=10, ge=1, le=100)
    metadata: JsonObject = Field(default_factory=dict)


class _AnchorHrefParser(HTMLParser):
    def __init__(self, base_url: str, limit: int):
        super().__init__(convert_charrefs=True)
        self._base_url: str = base_url
        self._limit: int = limit
        self._seen: set[str] = set()
        self.links: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or len(self.links) >= self._limit:
            return
        href: str | None = None
        for key, value in attrs:
            if key == "href":
                href = value
                break
        if href is None:
            return
        candidate = href.strip()
        if candidate == "":
            return
        absolute = urljoin(self._base_url, candidate)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            return
        if parsed.netloc == "":
            return
        if absolute in self._seen:
            return
        self._seen.add(absolute)
        self.links.append(absolute)


def _ensure_html_name(original_name: str) -> str:
    stripped = original_name.strip()
    if stripped == "":
        raise ValueError("original_name должен быть непустой строкой")
    if "." not in stripped:
        return f"{stripped}.html"
    return stripped


def _extract_clickable_links(*, html: str, base_url: str, limit: int) -> list[str]:
    parser = _AnchorHrefParser(base_url=base_url, limit=limit)
    parser.feed(html)
    return parser.links


def _schema_for_model(model: type[BaseModel]) -> JsonObject:
    # Pydantic v2: model_json_schema() возвращает JSON Schema.
    return require_json_object(model.model_json_schema(), f"{model.__name__}.schema")


def _tools() -> list[MCPToolDefinition]:
    return [
        MCPToolDefinition(
            name="browser_create_session",
            description="Создать control-сессию browser runtime (выделить страницу под session_id).",
            parameters_schema=_schema_for_model(ToolCreateSessionArgs),
        ),
        MCPToolDefinition(
            name="browser_navigate",
            description=(
                "Навигация в рамках сессии (url + wait_policy + optional artifacts). "
                "По умолчанию new_tab=true: новая вкладка (новая Playwright page) в том же контексте, "
                "предыдущая закрывается; refs observe сбрасываются до следующего browser_observe. "
                "new_tab=false — навигация в текущей вкладке."
            ),
            parameters_schema=_schema_for_model(ToolNavigateArgs),
        ),
        MCPToolDefinition(
            name="browser_observe",
            description=(
                "Получить LLM-friendly snapshot страницы: snapshot.text со строками вида "
                '- role "Name" [ref=eN]. Для click/fill передавай ref как @eN из этого текста. '
                "Поле include_snapshot_refs=true дублирует маппинг в snapshot.refs (лишние токены); "
                "по умолчанию false — сервер всё равно помнит refs для действий."
            ),
            parameters_schema=_schema_for_model(ToolObserveArgs),
        ),
        MCPToolDefinition(
            name="browser_click",
            description="Клик строго по ref из последнего browser_observe в этой сессии (human-like interaction).",
            parameters_schema=_schema_for_model(ToolClickArgs),
        ),
        MCPToolDefinition(
            name="browser_fill",
            description="Ввод текста строго в элемент по ref из последнего browser_observe в этой сессии (human-like interaction).",
            parameters_schema=_schema_for_model(ToolFillArgs),
        ),
        MCPToolDefinition(
            name="browser_press",
            description="Нажать клавишу (например Enter, Tab).",
            parameters_schema=_schema_for_model(ToolPressArgs),
        ),
        MCPToolDefinition(
            name="browser_wait",
            description="Ожидание selector и/или load_state в рамках сессии.",
            parameters_schema=_schema_for_model(ToolWaitArgs),
        ),
        MCPToolDefinition(
            name="browser_close_session",
            description="Закрыть сессию и освободить ресурсы.",
            parameters_schema=_schema_for_model(ToolCloseSessionArgs),
        ),
        MCPToolDefinition(
            name="browser_save_state",
            description=(
                "Сохранить состояние сессии (cookies/storage_state) в Redis и вернуть state_key. "
                "Передай state_key в browser_create_session как restore_state_key, чтобы поднять "
                "контекст с теми же cookies/storage (warm/restore)."
            ),
            parameters_schema=_schema_for_model(ToolSaveStateArgs),
        ),
        MCPToolDefinition(
            name="browser_save_html_to_s3",
            description=(
                "Сохранить HTML текущей страницы в S3 через file_processor и вернуть "
                "file_id/s3_path плюс первые кликабельные ссылки."
            ),
            parameters_schema=_schema_for_model(ToolSaveHtmlToS3Args),
        ),
    ]


def _model_json_object(model: BaseModel) -> JsonObject:
    return require_json_object(model.model_dump(mode="json"), model.__class__.__name__)


def _jsonrpc_payload(response: JsonRpcResponse) -> JsonObject:
    return require_json_object(response.model_dump(mode="json", exclude_none=True), "JsonRpcResponse")


def _json_text_content(value: JsonValue) -> list[JsonObject]:
    return [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]


def _error(code: int, message: str, data: JsonObject | None = None) -> JsonRpcError:
    return JsonRpcError(code=code, message=message, data=data)


def _mcp_tool_trace_attributes(*, tool_name: str, arguments: JsonObject) -> dict[str, str]:
    keys = list(arguments.keys())
    keys.sort()
    sid = arguments.get("session_id")
    out: dict[str, str] = {
        "platform.mcp.tool_name": tool_name.strip(),
        "platform.mcp.source": "browser_runtime",
        "platform.mcp.tool_args_keys": ",".join(keys[:50]),
    }
    if isinstance(sid, str) and sid.strip():
        out["platform.mcp.session_id"] = sid.strip()
    return out


def _parse_interaction_profile(value: object) -> InteractionProfileName:
    if value == "off":
        return "off"
    if value == "fast":
        return "fast"
    if value == "human":
        return "human"
    raise ValueError("interaction_profile должен быть одним из: off, fast, human")


def _parse_anti_bot_tier(value: object) -> AntiBotTier:
    if value == "white":
        return "white"
    if value == "gray":
        return "gray"
    if value == "black":
        return "black"
    raise ValueError("anti_bot_tier должен быть одним из: white, gray, black")


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"{field} должен быть строкой или null")


async def _tool_call(
    *,
    tool_name: str,
    arguments: JsonObject,
    container: BrowserContainer,
) -> McpToolCallResult:
    runtime = container.browser_runtime

    if tool_name == "browser_create_session":
        args = ToolCreateSessionArgs.model_validate(arguments)
        sid = args.session_id if args.session_id else f"sess-{uuid.uuid4().hex}"
        run_id = args.run_id if args.run_id else f"run-{sid}"
        task_id = args.task_id if args.task_id else f"task-{sid}"
        endpoint_key = args.endpoint_key if args.endpoint_key else runtime.settings.default_endpoint_key
        ctx = dict(args.context or {})
        page_mode = args.page_mode
        ctx_page_mode = ctx.get("page_mode", page_mode)
        if ctx_page_mode != page_mode:
            raise ValueError("context.page_mode должен совпадать с page_mode")
        profile_name = _parse_interaction_profile(
            ctx.get("interaction_profile", args.interaction_profile)
        )
        _ = get_interaction_profile(profile_name)
        seed_value = ctx.get("interaction_seed", args.interaction_seed)
        if seed_value is not None and not isinstance(seed_value, int):
            raise ValueError("interaction_seed должен быть целым числом")
        shared_storage_key = _optional_str(
            ctx.get("shared_storage_key", args.shared_storage_key),
            field="shared_storage_key",
        )
        user_agent = _optional_str(ctx.get("user_agent"), field="user_agent")
        anti_bot_tier = _parse_anti_bot_tier(ctx.get("anti_bot_tier", args.anti_bot_tier))
        sig = ContextSignature(
            proxy_policy=str(ctx.get("proxy_policy", args.proxy_policy)),
            shared_storage_key=shared_storage_key,
            anti_bot_tier=anti_bot_tier,
            stealth_init_version=str(ctx.get("stealth_init_version", "v1")),
            locale=str(ctx.get("locale", "en-US")),
            timezone_id=str(ctx.get("timezone_id", "UTC")),
            user_agent=user_agent,
            page_mode=page_mode,
            permissions_fingerprint=str(ctx.get("permissions_fingerprint", "default")),
        )
        out_model = await create_control_session(
            body=ControlSessionCreateBody(
                session_id=sid,
                run_id=run_id,
                task_id=task_id,
                page_mode=page_mode,
                shared_storage_key=args.shared_storage_key,
                proxy_policy=args.proxy_policy,
                anti_bot_tier=args.anti_bot_tier,
                timeout_ms=args.timeout_ms,
                endpoint_key=endpoint_key,
                session_mode=args.session_mode,
                restore_state_key=args.restore_state_key,
                context=ContextSignatureBody(
                    proxy_policy=sig.proxy_policy,
                    shared_storage_key=sig.shared_storage_key,
                    anti_bot_tier=anti_bot_tier,
                    stealth_init_version=sig.stealth_init_version,
                    locale=sig.locale,
                    timezone_id=sig.timezone_id,
                    user_agent=sig.user_agent,
                    page_mode=sig.page_mode,
                    permissions_fingerprint=sig.permissions_fingerprint,
                    interaction_profile=profile_name,
                    interaction_seed=seed_value,
                ),
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(_model_json_object(out_model)), isError=False)

    if tool_name == "browser_navigate":
        args = ToolNavigateArgs.model_validate(arguments)
        out = await control_navigate(
            session_id=args.session_id,
            body=ControlNavigateBody(
                url=args.url,
                wait_policy=args.wait_policy,
                screenshot=args.screenshot,
                snapshot=args.snapshot,
                capture_pdf=args.capture_pdf,
                navigation_timeout_ms=args.navigation_timeout_ms,
                new_tab=args.new_tab,
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value(out, "browser_navigate result")), isError=False)

    if tool_name == "browser_observe":
        args = ToolObserveArgs.model_validate(arguments)
        payload = await control_observe(
            session_id=args.session_id,
            body=ControlObserveBody(include_snapshot_refs=args.include_snapshot_refs),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value(payload, "browser_observe result")), isError=False)

    if tool_name == "browser_click":
        args = ToolClickArgs.model_validate(arguments)
        _ = await control_click(
            session_id=args.session_id,
            body=ControlClickBody(ref=args.ref, timeout_ms=args.timeout_ms),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value({"ok": True}, "browser_click result")), isError=False)

    if tool_name == "browser_fill":
        args = ToolFillArgs.model_validate(arguments)
        _ = await control_fill(
            session_id=args.session_id,
            body=ControlFillBody(
                ref=args.ref,
                text=args.text,
                timeout_ms=args.timeout_ms,
                typing_delay_ms=args.typing_delay_ms,
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value({"ok": True}, "browser_fill result")), isError=False)

    if tool_name == "browser_press":
        args = ToolPressArgs.model_validate(arguments)
        _ = await control_press(
            session_id=args.session_id,
            body=ControlPressBody(key=args.key),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value({"ok": True}, "browser_press result")), isError=False)

    if tool_name == "browser_wait":
        args = ToolWaitArgs.model_validate(arguments)
        _ = await control_wait(
            session_id=args.session_id,
            body=ControlWaitBody(
                selector=args.selector,
                load_state=args.load_state,
                timeout_ms=args.timeout_ms,
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value({"ok": True}, "browser_wait result")), isError=False)

    if tool_name == "browser_close_session":
        args = ToolCloseSessionArgs.model_validate(arguments)
        out = await delete_control_session(
            session_id=args.session_id,
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value(out, "browser_close_session result")), isError=False)

    if tool_name == "browser_save_state":
        args = ToolSaveStateArgs.model_validate(arguments)
        out = await save_control_session_state(
            session_id=args.session_id,
            body=ControlSaveStateBody(shared_storage_key=args.shared_storage_key),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(require_json_value(out, "browser_save_state result")), isError=False)

    if tool_name == "browser_save_html_to_s3":
        args = ToolSaveHtmlToS3Args.model_validate(arguments)
        await wait_for_agent_control(runtime, args.session_id)
        async with runtime.lease_manager.session_navigate_exclusive(args.session_id):
            await wait_for_agent_control(runtime, args.session_id)
            try:
                page = await runtime.lease_manager.get_page_for_session(args.session_id)
            except KeyError as exc:
                raise ValueError(str(exc)) from exc
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
            html = await page.content()
            links = _extract_clickable_links(html=html, base_url=page.url, limit=args.links_limit)
            record = await container.file_processor.process_file_from_bytes(
                data=html.encode("utf-8"),
                original_name=_ensure_html_name(args.original_name),
                content_type="text/html",
                metadata={
                    "source": "browser_mcp",
                    "session_id": args.session_id,
                    **args.metadata,
                },
                public=False,
            )
            payload = {
                "file_id": record.file_id,
                "s3_bucket": record.s3_bucket,
                "s3_key": record.s3_key,
                "s3_path": f"s3://{record.s3_bucket}/{record.s3_key}",
                "storage_url": record.storage_url,
                "file_size": record.file_size,
                "content_type": record.content_type,
                "source_url": page.url,
                "links": links,
            }
        return McpToolCallResult(content=_json_text_content(require_json_value(payload, "browser_save_html_to_s3 result")), isError=False)

    raise ValueError(f"Tool not found: {tool_name}")


@router.post("")
async def mcp_jsonrpc(
    req: JsonRpcRequest,
    request: Request,
    response: Response,
    container: ContainerDep,
) -> JsonObject:
    """
    MCP JSON-RPC endpoint (single POST).

    Возвращает JSON-RPC envelope; для initialize выставляет `Mcp-Session-Id` header.
    """
    method = req.method
    req_id = req.id
    params = req.params or {}

    # Простой session-id для MCP: клиент получает его на initialize и отдаёт обратно в headers.
    # Никакого серверного состояния по этому ID не требуется: состояние состояние control-сессий живёт в browser session_id.
    if method == "initialize":
        mcp_session_id = response.headers.get("Mcp-Session-Id")
        if not mcp_session_id:
            mcp_session_id = str(uuid.uuid4())
            response.headers["Mcp-Session-Id"] = mcp_session_id
        res = McpInitializeResult(
            protocolVersion=MCP_PROTOCOL_VERSION,
            capabilities={},
            serverInfo={"name": "platform-browser-runtime", "version": "1.0.0"},
        )
        return _jsonrpc_payload(JsonRpcResponse(id=req_id, result=_model_json_object(res)))

    protocol_header = request.headers.get("MCP-Protocol-Version")
    if protocol_header != MCP_PROTOCOL_VERSION:
        response.status_code = 400
        err = _error(-32000, "MCP-Protocol-Version header is required")
        return _jsonrpc_payload(JsonRpcResponse(id=req_id, error=err))

    if method == "notifications/initialized":
        response.status_code = 202
        return {}

    if method == "tools/list":
        tools = _tools()
        res = McpToolsListResult(tools=tools)
        # by_alias=True: на проводе MCP всегда camelCase `inputSchema`, как
        # того требует спецификация JSON-RPC MCP; внутри платформы поле
        # называется `parameters_schema`.
        return _jsonrpc_payload(JsonRpcResponse(id=req_id, result=require_json_object(res.model_dump(mode="json", by_alias=True), "McpToolsListResult")))

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or not name.strip():
            err = _error(-32602, "tools/call: params.name is required")
            return _jsonrpc_payload(JsonRpcResponse(id=req_id, error=err))
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            err = _error(-32602, "tools/call: params.arguments must be object")
            return _jsonrpc_payload(JsonRpcResponse(id=req_id, error=err))
        arguments_obj = require_json_object(arguments, "tools/call.params.arguments")
        try:
            async with traced_operation(
                "browser.mcp.tool_call",
                event_type="mcp.tool_call",
                operation_category="mcp",
                extra_attributes=_mcp_tool_trace_attributes(tool_name=name, arguments=arguments_obj),
            ) as span:
                call_res = await _tool_call(
                    tool_name=name,
                    arguments=arguments_obj,
                    container=container,
                )
                span.set_attribute("platform.mcp.tool_result_is_error", bool(call_res.isError))
        except Exception as exc:
            err = _error(-32000, str(exc), data={"tool": name})
            return _jsonrpc_payload(JsonRpcResponse(id=req_id, error=err))
        return _jsonrpc_payload(JsonRpcResponse(id=req_id, result=_model_json_object(call_res)))

    err = _error(-32601, f"Method not found: {method}")
    return _jsonrpc_payload(JsonRpcResponse(id=req_id, error=err))
