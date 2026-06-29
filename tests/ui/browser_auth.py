"""Cookie auth_token для Playwright (тот же механизм, что AuthMiddleware)."""

from __future__ import annotations

from playwright.async_api import BrowserContext

AUTH_TOKEN_COOKIE = "auth_token"

# localhost: Domain=localhost покрывает *.localhost (см. core.utils.domain.get_cookie_domain).
# lvh.me: .lvh.me покрывает system/company2 и сервисы на разных портах.
# Оба набора — чтобы UI_E2E_USE_LVH_ME мог включаться отдельными модулями без потери auth.
_COOKIE_HOSTS = (
    "localhost",
    "system.localhost",
    "company2.localhost",
    ".lvh.me",
)


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
