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
from typing import Any, Literal, Optional
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from apps.browser.api.control import (
    ControlClickBody,
    ControlFillBody,
    ControlNavigateBody,
    ControlObserveBody,
    ControlPressBody,
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
)
from apps.browser.dependencies import ContainerDep
from apps.browser.engine.types import ContextSignature
from apps.browser.interaction.interaction_profiles import (
    InteractionProfileName,
    get_interaction_profile,
)
from core.tracing.operation_span import traced_operation

router = APIRouter(prefix="/mcp", tags=["browser-mcp"])

MCP_PROTOCOL_VERSION = "2024-11-05"


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    message: str
    data: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None


class McpInitializeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocolVersion: str
    capabilities: dict[str, Any]
    serverInfo: dict[str, Any]


class McpToolInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    inputSchema: dict[str, Any]


class McpToolsListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[McpToolInfo]


class McpToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: list[dict[str, Any]]
    isError: bool = False


class ToolCreateSessionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    shared_storage_key: Optional[str] = None
    proxy_policy: str = ""
    anti_bot_tier: str = "gray"
    timeout_ms: int = Field(default=90_000, ge=1000)
    endpoint_key: Optional[str] = None
    session_mode: Literal["warm", "restore"] = "warm"
    restore_state_key: Optional[str] = None
    interaction_profile: InteractionProfileName = "human"
    interaction_seed: Optional[int] = None
    context: dict[str, Any] = Field(default_factory=dict)


class ToolNavigateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    url: str
    wait_policy: str = "domcontentloaded"
    screenshot: bool = False
    snapshot: bool = False
    capture_pdf: bool = False
    navigation_timeout_ms: int = Field(default=5_000, ge=1000)
    new_tab: bool = True


class ToolObserveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    include_snapshot_refs: bool = False


class ToolClickArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    ref: str
    timeout_ms: int = Field(default=10_000, ge=1000)


class ToolFillArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    ref: str
    text: str
    timeout_ms: int = Field(default=10_000, ge=1000)
    typing_delay_ms: Optional[int] = Field(default=None, ge=0)


class ToolPressArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    key: str


class ToolWaitArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    selector: Optional[str] = None
    load_state: Optional[Literal["domcontentloaded", "networkidle"]] = None
    timeout_ms: int = Field(default=30_000, ge=1000)


class ToolCloseSessionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str


class ToolSaveHtmlToS3Args(BaseModel): # убрать костыль
    model_config = ConfigDict(extra="forbid")

    session_id: str
    original_name: str = "snapshot.html"
    links_limit: int = Field(default=10, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _AnchorHrefParser(HTMLParser):
    def __init__(self, base_url: str, limit: int):
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._limit = limit
        self._seen: set[str] = set()
        self.links: list[str] = []

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


def _schema_for_model(model: type[BaseModel]) -> dict[str, Any]:
    # Pydantic v2: model_json_schema() возвращает JSON Schema.
    return model.model_json_schema()


def _tools() -> list[McpToolInfo]:
    return [
        McpToolInfo(
            name="browser_create_session",
            description="Создать control-сессию browser runtime (выделить страницу под session_id).",
            inputSchema=_schema_for_model(ToolCreateSessionArgs),
        ),
        McpToolInfo(
            name="browser_navigate",
            description=(
                "Навигация в рамках сессии (url + wait_policy + optional artifacts). "
                "По умолчанию new_tab=true: новая вкладка (новая Playwright page) в том же контексте, "
                "предыдущая закрывается; refs observe сбрасываются до следующего browser_observe. "
                "new_tab=false — навигация в текущей вкладке."
            ),
            inputSchema=_schema_for_model(ToolNavigateArgs),
        ),
        McpToolInfo(
            name="browser_observe",
            description=(
                "Получить LLM-friendly snapshot страницы: snapshot.text со строками вида "
                '- role "Name" [ref=eN]. Для click/fill передавай ref как @eN из этого текста. '
                "Поле include_snapshot_refs=true дублирует маппинг в snapshot.refs (лишние токены); "
                "по умолчанию false — сервер всё равно помнит refs для действий."
            ),
            inputSchema=_schema_for_model(ToolObserveArgs),
        ),
        McpToolInfo(
            name="browser_click",
            description="Клик строго по ref из последнего browser_observe в этой сессии (human-like interaction).",
            inputSchema=_schema_for_model(ToolClickArgs),
        ),
        McpToolInfo(
            name="browser_fill",
            description="Ввод текста строго в элемент по ref из последнего browser_observe в этой сессии (human-like interaction).",
            inputSchema=_schema_for_model(ToolFillArgs),
        ),
        McpToolInfo(
            name="browser_press",
            description="Нажать клавишу (например Enter, Tab).",
            inputSchema=_schema_for_model(ToolPressArgs),
        ),
        McpToolInfo(
            name="browser_wait",
            description="Ожидание selector и/или load_state в рамках сессии.",
            inputSchema=_schema_for_model(ToolWaitArgs),
        ),
        McpToolInfo(
            name="browser_close_session",
            description="Закрыть сессию и освободить ресурсы.",
            inputSchema=_schema_for_model(ToolCloseSessionArgs),
        ),
        McpToolInfo(
            name="browser_save_html_to_s3",
            description=(
                "Сохранить HTML текущей страницы в S3 через file_processor и вернуть "
                "file_id/s3_path плюс первые кликабельные ссылки."
            ),
            inputSchema=_schema_for_model(ToolSaveHtmlToS3Args),
        ),
    ]


def _json_text_content(obj: Any) -> list[dict[str, Any]]:
    return [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]


def _error(code: int, message: str, data: dict[str, Any] | None = None) -> JsonRpcError:
    return JsonRpcError(code=code, message=message, data=data)


def _mcp_tool_trace_attributes(*, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    keys = [k for k in arguments.keys() if isinstance(k, str)]
    keys.sort()
    sid = arguments.get("session_id")
    out: dict[str, Any] = {
        "platform.mcp.tool_name": tool_name.strip(),
        "platform.mcp.source": "browser_runtime",
        "platform.mcp.tool_args_keys": ",".join(keys[:50]),
    }
    if isinstance(sid, str) and sid.strip():
        out["platform.mcp.session_id"] = sid.strip()
    return out


async def _tool_call(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    container: Any,
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
        profile_name = ctx.get("interaction_profile", args.interaction_profile)
        if not isinstance(profile_name, str):
            raise ValueError("interaction_profile должен быть строкой")
        get_interaction_profile(profile_name)
        seed_value = ctx.get("interaction_seed", args.interaction_seed)
        if seed_value is not None and not isinstance(seed_value, int):
            raise ValueError("interaction_seed должен быть целым числом")
        sig = ContextSignature(
            proxy_policy=str(ctx.get("proxy_policy", args.proxy_policy)),
            shared_storage_key=ctx.get("shared_storage_key", args.shared_storage_key),
            anti_bot_tier=str(ctx.get("anti_bot_tier", args.anti_bot_tier)),
            stealth_init_version=str(ctx.get("stealth_init_version", "v1")),
            locale=str(ctx.get("locale", "en-US")),
            timezone_id=str(ctx.get("timezone_id", "UTC")),
            user_agent=ctx.get("user_agent"),
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
                context={
                    "proxy_policy": sig.proxy_policy,
                    "shared_storage_key": sig.shared_storage_key,
                    "anti_bot_tier": sig.anti_bot_tier,
                    "stealth_init_version": sig.stealth_init_version,
                    "locale": sig.locale,
                    "timezone_id": sig.timezone_id,
                    "user_agent": sig.user_agent,
                    "page_mode": sig.page_mode,
                    "permissions_fingerprint": sig.permissions_fingerprint,
                    "interaction_profile": profile_name,
                    "interaction_seed": seed_value,
                },
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(out_model.model_dump()), isError=False)

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
        return McpToolCallResult(content=_json_text_content(out), isError=False)

    if tool_name == "browser_observe":
        args = ToolObserveArgs.model_validate(arguments)
        payload = await control_observe(
            session_id=args.session_id,
            body=ControlObserveBody(include_snapshot_refs=args.include_snapshot_refs),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(payload), isError=False)

    if tool_name == "browser_click":
        args = ToolClickArgs.model_validate(arguments)
        await control_click(
            session_id=args.session_id,
            body=ControlClickBody(ref=args.ref, timeout_ms=args.timeout_ms),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content({"ok": True}), isError=False)

    if tool_name == "browser_fill":
        args = ToolFillArgs.model_validate(arguments)
        await control_fill(
            session_id=args.session_id,
            body=ControlFillBody(
                ref=args.ref,
                text=args.text,
                timeout_ms=args.timeout_ms,
                typing_delay_ms=args.typing_delay_ms,
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content({"ok": True}), isError=False)

    if tool_name == "browser_press":
        args = ToolPressArgs.model_validate(arguments)
        await control_press(
            session_id=args.session_id,
            body=ControlPressBody(key=args.key),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content({"ok": True}), isError=False)

    if tool_name == "browser_wait":
        args = ToolWaitArgs.model_validate(arguments)
        await control_wait(
            session_id=args.session_id,
            body=ControlWaitBody(
                selector=args.selector,
                load_state=args.load_state,
                timeout_ms=args.timeout_ms,
            ),
            container=container,
        )
        return McpToolCallResult(content=_json_text_content({"ok": True}), isError=False)

    if tool_name == "browser_close_session":
        args = ToolCloseSessionArgs.model_validate(arguments)
        out = await delete_control_session(
            session_id=args.session_id,
            container=container,
        )
        return McpToolCallResult(content=_json_text_content(out), isError=False)

    if tool_name == "browser_save_html_to_s3":
        args = ToolSaveHtmlToS3Args.model_validate(arguments)
        async with runtime.lease_manager.session_navigate_exclusive(args.session_id):
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
        return McpToolCallResult(content=_json_text_content(payload), isError=False)

    raise ValueError(f"Tool not found: {tool_name}")


@router.post("")
async def mcp_jsonrpc(
    req: JsonRpcRequest,
    response: Response,
    container: ContainerDep,
) -> dict[str, Any]:
    """
    MCP JSON-RPC endpoint (single POST).

    Возвращает JSON-RPC envelope; для initialize выставляет `Mcp-Session-Id` header.
    """
    method = req.method
    req_id = req.id
    params = req.params or {}

    # Простой session-id для MCP: клиент получает его на initialize и отдаёт обратно в headers.
    # Никакого server-side состояния по этому ID не требуется: состояние control сессий живёт в browser session_id.
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
        return JsonRpcResponse(id=req_id, result=res.model_dump()).model_dump(exclude_none=True)

    if method == "tools/list":
        tools = _tools()
        res = McpToolsListResult(tools=tools)
        return JsonRpcResponse(id=req_id, result=res.model_dump()).model_dump(exclude_none=True)

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or not name.strip():
            err = _error(-32602, "tools/call: params.name is required")
            return JsonRpcResponse(id=req_id, error=err).model_dump(exclude_none=True)
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            err = _error(-32602, "tools/call: params.arguments must be object")
            return JsonRpcResponse(id=req_id, error=err).model_dump(exclude_none=True)
        try:
            async with traced_operation(
                "browser.mcp.tool_call",
                event_type="mcp.tool_call",
                operation_category="mcp",
                extra_attributes=_mcp_tool_trace_attributes(tool_name=name, arguments=arguments),
            ) as span:
                call_res = await _tool_call(
                    tool_name=name,
                    arguments=arguments,
                    container=container,
                )
                span.set_attribute("platform.mcp.tool_result_is_error", bool(call_res.isError))
        except Exception as exc:
            err = _error(-32000, str(exc), data={"tool": name})
            return JsonRpcResponse(id=req_id, error=err).model_dump(exclude_none=True)
        return JsonRpcResponse(id=req_id, result=call_res.model_dump()).model_dump(exclude_none=True)

    err = _error(-32601, f"Method not found: {method}")
    return JsonRpcResponse(id=req_id, error=err).model_dump(exclude_none=True)

