"""
HTTP клиент с поддержкой прокси.
"""

from core.http.client import get_httpx_client, request_public_oauth

__all__ = [
    "get_httpx_client",
    "request_public_oauth",
]
