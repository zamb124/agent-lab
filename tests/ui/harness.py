"""Обёртка Playwright (async) над реестром SERVICE_UI_REGISTRY: открытие SPA и проверка shell."""

from __future__ import annotations

from playwright.async_api import Page, expect

from tests.ui.apps import ServiceUiSpec


class AppUI:
    """Доступ к одному сервису по фиксированному ServiceUiSpec."""

    def __init__(self, spec: ServiceUiSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> ServiceUiSpec:
        return self._spec

    def _host(self) -> str:
        if self._spec.subdomain_prefix:
            return f"{self._spec.subdomain_prefix}.localhost"
        return "localhost"

    @property
    def origin(self) -> str:
        return f"http://{self._host()}:{self._spec.port}"

    def spa_url(self) -> str:
        path = self._spec.spa_path
        if not path.startswith("/"):
            raise ValueError(f"spa_path must start with /: {path!r}")
        return f"{self.origin}{path}"

    async def open(self, page: Page, *, wait_until: str = "domcontentloaded") -> None:
        await page.goto(self.spa_url(), wait_until=wait_until)

    async def expect_shell(self, page: Page, *, timeout_ms: int = 30_000) -> None:
        await expect(page.locator(self._spec.shell_selector)).to_be_visible(timeout=timeout_ms)
        if self._spec.title is not None:
            await expect(page).to_have_title(self._spec.title, timeout=timeout_ms)
