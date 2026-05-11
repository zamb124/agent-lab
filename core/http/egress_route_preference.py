"""
Redis: предпочтение egress proxy по origin (нормализованный scheme://host:port).

Ключ platform:http_egress:prefer_proxy:{origin}; SET только с TTL; DEL при инвалидации.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

REDIS_KEY_PREFIX = "platform:http_egress:prefer_proxy:"
_PREFER_MARKER = "1"

_redis: Any = None


def _redis_client() -> Any:
    global _redis
    if _redis is None:
        from core.clients.redis_client import RedisClient

        _redis = RedisClient(get_settings().database.redis_url)
    return _redis


def redis_key_for_origin(normalized_origin: str) -> str:
    return f"{REDIS_KEY_PREFIX}{normalized_origin}"


def normalized_http_origin(absolute_url: str) -> str:
    """
    Нормализует origin для ключа Redis: lower host, explicit port (80/443 по умолчанию).
    Только absolute URL с netloc.
    """
    parsed = urlparse(absolute_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"egress preference requires absolute URL with host: {absolute_url!r}")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    return f"{scheme}://{host}:{port}"


async def egress_prefer_proxy_get(normalized_origin: str) -> bool:
    if not _platform_proxy_configured():
        return False
    key = redis_key_for_origin(normalized_origin)
    raw = await _redis_client().get(key)
    return raw == _PREFER_MARKER


async def egress_prefer_proxy_set(normalized_origin: str) -> None:
    if not _platform_proxy_configured():
        return
    ttl = get_settings().proxy.prefer_proxy_ttl_seconds
    key = redis_key_for_origin(normalized_origin)
    ok = await _redis_client().set(key, _PREFER_MARKER, ttl=ttl)
    if not ok:
        logger.warning("egress_prefer_proxy_set: Redis SET failed for origin=%s", normalized_origin)


async def egress_prefer_proxy_delete(normalized_origin: str) -> None:
    deleted = await _redis_client().delete(redis_key_for_origin(normalized_origin))
    if deleted:
        logger.debug("egress_prefer_proxy_delete: origin=%s", normalized_origin)


def _platform_proxy_configured() -> bool:
    p = get_settings().proxy
    return bool(p.enabled and p.proxies)
