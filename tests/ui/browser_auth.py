"""Cookie auth_token для Playwright на localhost (тот же механизм, что AuthMiddleware)."""

from __future__ import annotations

from playwright.async_api import BrowserContext

AUTH_TOKEN_COOKIE = "auth_token"

# Один токен на нескольких host, иначе cookie с domain=localhost не уйдёт на system.localhost (CRM/RAG).
_COOKIE_HOSTS = ("localhost", "system.localhost", "company2.localhost")


async def add_auth_token_cookie(context: BrowserContext, token: str) -> None:
    await context.add_cookies(
        [
            {
                "name": AUTH_TOKEN_COOKIE,
                "value": token,
                "domain": host,
                "path": "/",
                "httpOnly": True,
                "sameSite": "Lax",
            }
            for host in _COOKIE_HOSTS
        ]
    )
