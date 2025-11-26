"""
HTTP - HTTP клиенты с поддержкой прокси.
"""

from core.http.client import get_httpx_client, get_proxy_url

__all__ = [
    "get_httpx_client",
    "get_proxy_url",
]
