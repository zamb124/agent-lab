"""
Прокси первого сегмента пути для локальной разработки без общего ingress.

Ответ upstream пересылается потоком (httpx send(stream=True), Starlette StreamingResponse),
чтобы SSE и крупные тела не буферизовались целиком в памяти на стороне прокси.

В development/test при Host localhost или *.lvh.me запрос пересылается на URL из server.*_service_url.
Если текущий процесс уже обслуживает этот сервис (первый сегмент пути совпадает с именем процесса
или с публичным префиксом из _PREFIX_TO_SERVICE_URL_KEY, например office и /documents/...), прокси не используется.

OnlyOffice: префиксы /web-apps, /common, /cache, /fonts, /sdkjs, /downloadfile и пути
/{semver}-{hex}/web-apps/..., /{semver}-{hex}/sdkjs/..., /{semver}-{hex}/fonts/..., /{semver}-{hex}/doc/... (co-editing)
при server.document_server_dev_upstream_url проксируются на Document Server. Host к upstream — тот же, что у браузера (shell),
иначе DS подставляет netloc контейнера в подписанные URL (/cache/...) и ловится CORS.
"""

from __future__ import annotations

import asyncio
import re
from typing import FrozenSet
from urllib.parse import urlparse

import httpx
import websockets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from core.config import get_settings
from core.logging import get_log_context, get_logger
from core.utils.domain import is_local

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"
TRACE_ID_HEADER = "X-Trace-Id"

# Первый сегмент пути для прокси на другой локальный сервис. Исключение: browser (8009) —
# только межсервисные вызовы по URL из settings, без префикса в shell (см. infrastructure.mdc).
_SERVICE_PREFIXES: tuple[str, ...] = (
    "flows",
    "crm",
    "rag",
    "sync",
    "voice",
    "documents",
    "frontend",
    "litserve",
    "capability-gateway",
    "code-runner-python",
    "code-runner-node",
    "code-runner-go",
    "code-runner-csharp",
)

# Где публичный первый сегмент пути не совпадает с ключом get_service_url / SERVER__*_SERVICE_URL.
_PREFIX_TO_SERVICE_URL_KEY: dict[str, str] = {
    "documents": "office",
    "litserve": "provider_litserve",
    "capability-gateway": "capability_gateway",
    "code-runner-python": "code_runner_python",
    "code-runner-node": "code_runner_node",
    "code-runner-go": "code_runner_go",
    "code-runner-csharp": "code_runner_csharp",
}

_ONLYOFFICE_STATIC_SEGMENTS: frozenset[str] = frozenset(
    {"web-apps", "common", "cache", "fonts", "sdkjs"},
)

# Сессии редактора: POST/GET у корня хоста DS, не под /web-apps/
_ONLYOFFICE_DS_ROOT_SEGMENTS: frozenset[str] = frozenset(
    {"downloadfile"},
)

# DS (7.3+): под /{semver}-{hex}/ — web-apps, sdkjs, fonts, doc (шрифты и статика не только под /fonts/)
_ONLYOFFICE_VERSIONED_DS_PREFIX: re.Pattern[str] = re.compile(
    r"^/[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]+/(?:web-apps|sdkjs|fonts|doc)(?:/|$)",
    re.IGNORECASE,
)


def _is_onlyoffice_upstream_path(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] in _ONLYOFFICE_STATIC_SEGMENTS:
        return True
    if parts and parts[0] in _ONLYOFFICE_DS_ROOT_SEGMENTS:
        return True
    return _ONLYOFFICE_VERSIONED_DS_PREFIX.match(path) is not None


def _is_local_target_for_process(first_path_segment: str, process_service_name: str) -> bool:
    """True — запрос с таким первым сегментом должен обработать текущий процесс без HTTP-прокси."""
    if first_path_segment == process_service_name:
        return True
    if _PREFIX_TO_SERVICE_URL_KEY.get(first_path_segment) == process_service_name:
        return True
    return False


_HOP_BY_HOP_REQUEST: FrozenSet[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

_EXCLUDED_RESPONSE_HEADERS: FrozenSet[str] = frozenset(
    {
        "connection",
        "content-encoding",
        "content-length",
        "keep-alive",
        "transfer-encoding",
        "server",
    }
)


class DevInterServiceProxyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def _forward_http(
        self,
        request: Request,
        *,
        upstream_base: str,
        path: str,
        upstream_host: str,
    ) -> Response:
        base = upstream_base.rstrip("/")
        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный upstream base: {upstream_base!r}")

        query = request.url.query
        upstream = f"{base}{path}"
        if query:
            upstream = f"{upstream}?{query}"

        forward_headers: list[tuple[str, str]] = []
        seen_lower: set[str] = set()
        for key, value in request.headers.items():
            lk = key.lower()
            if lk in _HOP_BY_HOP_REQUEST:
                continue
            if lk == "host":
                continue
            forward_headers.append((key, value))
            seen_lower.add(lk)
        forward_headers.append(("host", upstream_host))

        log_ctx = get_log_context()
        if "x-request-id" not in seen_lower:
            request_id = log_ctx.get("request_id")
            if isinstance(request_id, str) and request_id.strip():
                forward_headers.append((REQUEST_ID_HEADER, request_id.strip()))
        if "x-trace-id" not in seen_lower:
            trace_id = log_ctx.get("trace_id")
            if isinstance(trace_id, str) and trace_id.strip():
                forward_headers.append((TRACE_ID_HEADER, trace_id.strip()))

        body = await request.body()

        client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            trust_env=False,
        )
        try:
            httpx_request = client.build_request(
                request.method,
                upstream,
                headers=dict(forward_headers),
                content=body if body else None,
            )
            upstream_response = await client.send(httpx_request, stream=True)
        except httpx.RequestError as e:
            await client.aclose()
            logger.warning(
                "dev_proxy.upstream_failed",
                upstream=upstream,
                **{"exception.message": str(e), "exception.type": type(e).__name__},
            )
            hint = (
                f"Inter-service dev proxy: нет HTTP-ответа от {base}.\n"
                f"Проверьте, что целевой сервис запущен (для /litserve — provider_litserve на 8014: "
                f'"uv run python scripts/run.py provider_litserve" или `make app`).\n'
            )
            return Response(
                content=hint.encode("utf-8"),
                status_code=502,
                media_type="text/plain; charset=utf-8",
            )

        out_headers: dict[str, str] = {}
        for key, value in upstream_response.headers.items():
            if key.lower() in _EXCLUDED_RESPONSE_HEADERS:
                continue
            out_headers[key] = value

        logger.debug(
            "dev_proxy.forwarded",
            http_method=request.method,
            http_path=path,
            upstream=upstream,
            http_status_code=upstream_response.status_code,
        )

        resp = upstream_response
        cli = client

        async def body_iter():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await cli.aclose()

        return StreamingResponse(
            body_iter(),
            status_code=upstream_response.status_code,
            headers=out_headers,
        )

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.server.env not in ("development", "test"):
            return await call_next(request)

        host = request.headers.get("host") or ""
        if not is_local(host):
            return await call_next(request)

        path = request.scope.get("path") or ""
        parts = [p for p in path.split("/") if p]
        if not parts:
            return await call_next(request)

        target = parts[0]
        if _is_onlyoffice_upstream_path(path):
            ds_base = (settings.server.document_server_dev_upstream_url or "").strip().rstrip("/")
            if not ds_base:
                return await call_next(request)
            parsed_ds = urlparse(ds_base)
            if not parsed_ds.netloc:
                raise RuntimeError(f"Некорректный server.document_server_dev_upstream_url: {ds_base!r}")
            client_host = (request.headers.get("host") or "").strip() or parsed_ds.netloc
            return await self._forward_http(
                request,
                upstream_base=ds_base,
                path=path,
                upstream_host=client_host,
            )

        if target not in _SERVICE_PREFIXES:
            return await call_next(request)

        if _is_local_target_for_process(target, self._service_name):
            return await call_next(request)

        url_key = _PREFIX_TO_SERVICE_URL_KEY.get(target, target)
        base = settings.server.get_service_url(url_key).rstrip("/")
        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный URL сервиса {url_key} (path {target}): {base!r}")

        upstream_host = (request.headers.get("host") or "").strip() or parsed.netloc

        return await self._forward_http(
            request,
            upstream_base=base,
            path=path,
            upstream_host=upstream_host,
        )


_WS_HOP_BY_HOP: FrozenSet[str] = frozenset(
    {
        "host",
        "connection",
        "upgrade",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-extensions",
        "sec-websocket-accept",
        "sec-websocket-protocol",
    }
)


class DevInterServiceWsProxyMiddleware:
    """Pure ASGI middleware: проксирует WebSocket-апгрейды первого сегмента
    пути на upstream-сервис в development/test. Для HTTP пропускает дальше.

    Параллельно с `DevInterServiceProxyMiddleware` (он только HTTP).
    Без неё WS-апгрейды на чужой сервис из браузера получают 403/404,
    т.к. handler смонтирован только в целевом процессе.
    """

    def __init__(self, app, *, service_name: str) -> None:
        self.app = app
        self._service_name = service_name

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "websocket":
            return await self.app(scope, receive, send)

        settings = get_settings()
        if settings.server.env not in ("development", "test"):
            return await self.app(scope, receive, send)

        host = ""
        for k, v in scope.get("headers") or []:
            if k.decode("latin-1").lower() == "host":
                host = v.decode("latin-1")
                break
        if not is_local(host):
            return await self.app(scope, receive, send)

        path = scope.get("path") or ""
        parts = [p for p in path.split("/") if p]
        if not parts:
            return await self.app(scope, receive, send)

        target = parts[0]
        if target not in _SERVICE_PREFIXES:
            return await self.app(scope, receive, send)
        if _is_local_target_for_process(target, self._service_name):
            return await self.app(scope, receive, send)

        url_key = _PREFIX_TO_SERVICE_URL_KEY.get(target, target)
        base = settings.server.get_service_url(url_key).rstrip("/")
        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный URL сервиса {url_key} (path {target}): {base!r}")

        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        query = scope.get("query_string", b"").decode("latin-1")
        upstream_url = f"{ws_scheme}://{parsed.netloc}{path}"
        if query:
            upstream_url = f"{upstream_url}?{query}"

        forward_headers: list[tuple[str, str]] = []
        for raw_k, raw_v in scope.get("headers") or []:
            lk = raw_k.decode("latin-1").lower()
            if lk in _WS_HOP_BY_HOP:
                continue
            forward_headers.append((raw_k.decode("latin-1"), raw_v.decode("latin-1")))

        subprotocols = scope.get("subprotocols") or []

        try:
            upstream = await websockets.connect(
                upstream_url,
                additional_headers=forward_headers,
                subprotocols=subprotocols if subprotocols else None,
                open_timeout=10,
                ping_interval=None,
                max_size=None,
            )
        except Exception as exc:
            logger.warning(
                "dev_proxy.ws_upstream_failed",
                upstream_url=upstream_url,
                **{"exception.type": type(exc).__name__, "exception.message": str(exc)},
            )
            await send({"type": "websocket.close", "code": 1011})
            return

        accept_msg: dict[str, object] = {"type": "websocket.accept"}
        if upstream.subprotocol:
            accept_msg["subprotocol"] = upstream.subprotocol
        await send(accept_msg)

        async def _client_to_upstream() -> None:
            try:
                while True:
                    msg = await receive()
                    mtype = msg.get("type")
                    if mtype == "websocket.disconnect":
                        await upstream.close(code=msg.get("code", 1000) or 1000)
                        return
                    if mtype != "websocket.receive":
                        continue
                    if msg.get("bytes") is not None:
                        await upstream.send(msg["bytes"])
                    elif msg.get("text") is not None:
                        await upstream.send(msg["text"])
            except websockets.ConnectionClosed:
                return

        async def _upstream_to_client() -> None:
            try:
                async for frame in upstream:
                    if isinstance(frame, bytes):
                        await send({"type": "websocket.send", "bytes": frame})
                    else:
                        await send({"type": "websocket.send", "text": frame})
            except websockets.ConnectionClosed:
                return

        try:
            done, pending = await asyncio.wait(
                {
                    asyncio.create_task(_client_to_upstream()),
                    asyncio.create_task(_upstream_to_client()),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            try:
                await upstream.close()
            except Exception:
                pass
            try:
                await send({"type": "websocket.close", "code": 1000})
            except Exception:
                pass
