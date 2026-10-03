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

type ScopeScalar = str | bytes | int | None
type ScopeTuple = tuple[ScopeScalar, ...]
type ScopeCandidate = ScopeTuple | ScopeScalar | list[ScopeTuple | ScopeScalar]
type ScopeField = ScopeCandidate | list[ScopeCandidate] | None


def _scope_field(scope: Scope, key: str) -> ScopeField:
    return cast(ScopeField, scope.get(key))


def _first_csv_token(value: bytes) -> str:
    decoded: str = value.decode("latin-1")
    tokens: list[str] = decoded.split(",", 1)
    first_token: str = tokens[0]
    return first_token.strip()


def _unpack_host_port(raw: ScopeField) -> tuple[str, int] | None:
    if not isinstance(raw, tuple) or len(raw) != 2:
        return None
    host, port = raw
    if not isinstance(host, str) or not isinstance(port, int):
        return None
    return host, port


def _is_bytes_pair(value: ScopeCandidate) -> TypeGuard[tuple[bytes, bytes]]:
    if not isinstance(value, tuple) or len(value) != 2:
        return False
    return isinstance(value[0], bytes) and isinstance(value[1], bytes)


def _header_pairs(raw: ScopeField) -> list[tuple[bytes, bytes]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("scope['headers'] must be list[tuple[bytes, bytes]]")
    pairs: list[tuple[bytes, bytes]] = []
    for item in raw:
        if not _is_bytes_pair(item):
            raise TypeError("scope['headers'] must be list[tuple[bytes, bytes]]")
        pairs.append(item)
    return pairs


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

        client = _unpack_host_port(_scope_field(scope, "client"))
        client_host = client[0] if client is not None else None

        if not self.trust_all and client_host not in self.trusted_hosts:
            await self.app(scope, receive, send)
            return

        raw_headers = _header_pairs(_scope_field(scope, "headers"))
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
            server = _unpack_host_port(_scope_field(scope, "server"))
            if host and server is not None:
                hostname = host.split(":", 1)[0]
                scope["server"] = (hostname, server[1])

        await self.app(scope, receive, send)
