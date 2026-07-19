"""Cookie auth_token для Playwright (тот же механизм, что AuthMiddleware)."""

from __future__ import annotations

from playwright.async_api import BrowserContext

from tests.ui.e2e_worker import ui_e2e_subdomain, ui_e2e_subdomain_company2

AUTH_TOKEN_COOKIE = "auth_token"


def _cookie_hosts() -> tuple[str, ...]:
    # localhost: Domain=localhost покрывает *.localhost (см. core.utils.domain.get_cookie_domain).
    # lvh.me: .lvh.me покрывает ui-gwN / system и сервисы на разных портах.
    # Worker-subdomain.*.localhost — явный Host для CRM/RAG/Office без wildcard.
    primary = ui_e2e_subdomain()
    company2 = ui_e2e_subdomain_company2()
    return (
        "localhost",
        f"{primary}.localhost",
        f"{company2}.localhost",
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
            for host in _cookie_hosts()
        ]
    )
