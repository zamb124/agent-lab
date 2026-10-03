"""SSRF-safe HTTP fetch для inbound A2A Part.url."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from core.config.testing import is_testing
from core.http import get_httpx_client, http_header_text
from core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _hostname_resolves_to_blocked_ip(hostname: str) -> bool:
    """True если любой A/AAAA адрес hostname — private/loopback/link-local/reserved."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Part.url DNS resolve failed for host {hostname!r}") from exc
    if not addr_infos:
        raise ValueError(f"Part.url DNS returned no addresses for host {hostname!r}")
    for info in addr_infos:
        raw_ip = info[4][0]
        if _ip_is_blocked(ipaddress.ip_address(raw_ip)):
            return True
    return False


def assert_public_http_url(url: str) -> str:
    """Валидирует http(s) URL и блокирует private/loopback targets (SSRF).

    В TESTING loopback/private разрешены для ephemeral file/webhook hosts.
    """
    normalized = url.strip()
    if not normalized:
        raise ValueError("Part.url is empty")
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Part.url scheme must be http or https, got {parsed.scheme!r}")
    hostname = parsed.hostname
    if hostname is None or not hostname.strip():
        raise ValueError("Part.url must include hostname")
    host = hostname.strip().lower()
    if is_testing():
        return normalized
    if host in {"localhost", "metadata.google.internal"}:
        raise ValueError(f"Part.url host blocked: {host!r}")
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if _ip_is_blocked(literal_ip):
            raise ValueError(f"Part.url IP blocked: {host!r}")
    elif _hostname_resolves_to_blocked_ip(host):
        raise ValueError(f"Part.url resolves to blocked address: {host!r}")
    return normalized


async def fetch_public_url_bytes(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bytes, str | None]:
    """
    GET Part.url с SSRF-защитой.

    Возвращает (body, content-type из заголовка при наличии).
    """
    safe_url = assert_public_http_url(url)
    async with get_httpx_client(timeout=timeout_seconds) as client:
        # follow_redirects=False: redirect на private IP = SSRF-вектор.
        response = await client.get(safe_url, follow_redirects=False)
        if 300 <= response.status_code < 400:
            raise ValueError("Part.url redirects are not followed (SSRF)")
        if response.status_code >= 400:
            raise ValueError(f"Part.url fetch failed: HTTP {response.status_code}")
        data = response.content
        if len(data) == 0:
            raise ValueError("Part.url returned empty body")
        if len(data) > max_bytes:
            raise ValueError(
                f"Part.url exceeds size limit {max_bytes} bytes (got {len(data)})"
            )
        content_type: str | None = None
        content_type_header = http_header_text(response.headers, "content-type")
        if content_type_header is not None and content_type_header.strip():
            content_type = content_type_header.split(";", 1)[0].strip()
        return data, content_type
