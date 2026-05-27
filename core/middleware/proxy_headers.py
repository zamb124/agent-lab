"""
ASGI middleware: парсит `X-Forwarded-Proto` / `X-Forwarded-For` /
`X-Forwarded-Host` от reverse proxy (Traefik/MicroK8s ingress) и
обновляет `scope["scheme"]`, `scope["client"]`, `scope["server"]` чтобы
downstream (auth, build_service_base_url, access log) видел реального
клиента и scheme.

Контракт совпадает с тем, что раньше делал
`uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(trusted_hosts=["*"])`.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from starlette.types import ASGIApp, Receive, Scope, Send

_FORWARDED_PROTO = b"x-forwarded-proto"
_FORWARDED_FOR = b"x-forwarded-for"
_FORWARDED_HOST = b"x-forwarded-host"


def _first_csv_token(value: bytes) -> str:
    decoded: str = value.decode("latin-1")
    tokens: list[str] = decoded.split(",", 1)
    first_token: str = tokens[0]
    return first_token.strip()


def _unpack_host_port(raw: object) -> tuple[str, int] | None:
    if not isinstance(raw, tuple):
        return None
    raw_tuple = cast(tuple[object, ...], raw)
    if len(raw_tuple) != 2:
        return None
    host_obj, port_obj = raw_tuple
    if not isinstance(host_obj, str) or not isinstance(port_obj, int):
        return None
    return host_obj, port_obj


def _is_bytes_pair(value: object) -> TypeGuard[tuple[bytes, bytes]]:
    if not isinstance(value, tuple):
        return False
    value_tuple = cast(tuple[object, ...], value)
    if len(value_tuple) != 2:
        return False
    return isinstance(value_tuple[0], bytes) and isinstance(value_tuple[1], bytes)


class ProxyHeadersMiddleware:
    """trusted_hosts='*' — доверять всем (равно uvicorn-овскому дефолту в нашем factory)."""

    def __init__(self, app: ASGIApp, trusted_hosts: str | list[str] = "*") -> None:
        self.app: ASGIApp = app
        self.trust_all: bool = trusted_hosts == "*" or trusted_hosts == ["*"]
        if isinstance(trusted_hosts, str):
            self.trusted_hosts: frozenset[str] = frozenset(
                [h.strip() for h in trusted_hosts.split(",") if h.strip()]
            )
        else:
            self.trusted_hosts = frozenset(trusted_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        client = _unpack_host_port(scope.get("client"))
        client_host = client[0] if client is not None else None

        if not self.trust_all and client_host not in self.trusted_hosts:
            await self.app(scope, receive, send)
            return

        raw_headers_obj = cast(object, scope.get("headers"))
        if raw_headers_obj is None:
            raw_headers: list[tuple[bytes, bytes]] = []
        elif not isinstance(raw_headers_obj, list):
            raise TypeError("scope['headers'] must be list[tuple[bytes, bytes]]")
        else:
            header_items = cast(list[object], raw_headers_obj)
            raw_headers = []
            for header_item in header_items:
                if not _is_bytes_pair(header_item):
                    raise TypeError("scope['headers'] must be list[tuple[bytes, bytes]]")
                raw_headers.append(header_item)
        headers: dict[bytes, bytes] = dict(raw_headers)

        proto = headers.get(_FORWARDED_PROTO)
        if proto:
            scope["scheme"] = _first_csv_token(proto)

        forwarded_for = headers.get(_FORWARDED_FOR)
        if forwarded_for and client is not None:
            real_ip = _first_csv_token(forwarded_for)
            if real_ip:
                scope["client"] = (real_ip, client[1])

        forwarded_host = headers.get(_FORWARDED_HOST)
        if forwarded_host:
            host = _first_csv_token(forwarded_host)
            server = _unpack_host_port(scope.get("server"))
            if host and server is not None:
                hostname = host.split(":", 1)[0]
                scope["server"] = (hostname, server[1])

        await self.app(scope, receive, send)
