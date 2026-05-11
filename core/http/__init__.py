"""
HTTP клиент с поддержкой прокси.
"""

from core.http.client import ProxyStrategy, get_httpx_client, request_public_oauth

__all__ = [
    "ProxyStrategy",
    "get_httpx_client",
    "request_public_oauth",
]
