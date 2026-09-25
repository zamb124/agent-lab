"""Endpoint хранилища компании не должен указывать внутрь кластера или на link-local."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from core.files.object_store.resolved import resolve_platform_storage

_BLOCKED_HOST_SUFFIXES = (".svc", ".cluster.local", ".internal")


def _platform_is_loopback() -> bool:
    try:
        platform = resolve_platform_storage()
    except ValueError:
        return False
    host = urlparse(platform.endpoint_url).hostname
    return host in ("localhost", "127.0.0.1", "::1")


def _address_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_company_endpoint(endpoint_url: str) -> None:
    parsed = urlparse(endpoint_url.strip())
    host = parsed.hostname
    if host is None or parsed.scheme not in ("https", "http"):
        raise ValueError("storage endpoint must be an absolute http(s) URL")
    lowered = host.lower().rstrip(".")
    if lowered.endswith(_BLOCKED_HOST_SUFFIXES) or ".svc." in lowered:
        raise ValueError("storage endpoint must not target cluster DNS")
    loopback_ok = _platform_is_loopback() and lowered in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not loopback_ok:
        raise ValueError("storage endpoint must be https")
    if loopback_ok:
        return
    try:
        addresses = socket.getaddrinfo(lowered, parsed.port or 443)
    except socket.gaierror as exc:
        raise ValueError("storage endpoint host does not resolve") from exc
    for info in addresses:
        raw = info[4][0]
        ip = ipaddress.ip_address(raw)
        if not _address_is_public(ip):
            raise ValueError("storage endpoint must be a public address")
