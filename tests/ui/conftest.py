"""Фикстуры `*_ui`, персоны браузера и async Playwright (совместимо с pytest-asyncio)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.browser_auth import add_auth_token_cookie
from tests.ui.click_highlight import install_click_highlight_on_context
from tests.ui.harness import AppUI
from tests.ui.personas import ANONYMOUS_UI_USER, UiPersona, UiTestUser, ui_test_user_from_token
from tests.ui.scenario_doc import ScenarioRecorder
from tests.ui.subdomain_setup import ensure_ui_subdomain_mappings


@pytest_asyncio.fixture
async def scenario(request: pytest.FixtureRequest) -> ScenarioRecorder:
    """Собирает шаги и скриншоты; пишет `docs/scenarios/<service>/<tag>/<slug>/README.md` (см. `@pytest.mark.scenario`)."""
    rec = ScenarioRecorder.from_pytest_node(request.node)
    yield rec
    rec.finalize()


@pytest_asyncio.fixture(scope="session")
async def _browser_session() -> Browser:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ui_e2e_identities_ready(
    auth_token_system: str,
    auth_token_system_user2: str,
    auth_token_company2: str,
    auth_token_company2_user2: str,
) -> None:
    """Один раз на сессию: компании system / company2 и четыре пользователя (см. tests/fixtures/auth.py)."""


@pytest_asyncio.fixture(scope="session")
async def _ui_subdomain_mappings(
    frontend_container,
    auth_token_system: str,
    auth_token_company2: str,
) -> None:
    """Субдомены для Lit-SPA с frontend-контекстом (CRM, RAG на system.localhost)."""
    await ensure_ui_subdomain_mappings(frontend_container)


@pytest_asyncio.fixture
async def page(_browser_session: Browser) -> Page:
    """Браузер без cookie — редирект на логин для защищённых SPA."""
    context: BrowserContext = await _browser_session.new_context()
    await install_click_highlight_on_context(context)
    p = await context.new_page()
    yield p
    await context.close()


@pytest_asyncio.fixture
async def ui_page_anonymous(page: Page) -> Page:
    """Явное имя для неаутентифицированного контекста (то же, что `page`)."""
    return page


async def _authenticated_page(browser: Browser, token: str) -> tuple[Page, BrowserContext]:
    context = await browser.new_context()
    await install_click_highlight_on_context(context)
    await add_auth_token_cookie(context, token)
    page = await context.new_page()
    return page, context


@pytest_asyncio.fixture
async def ui_page_system(_browser_session: Browser, auth_token_system: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_system)
    yield page
    await ctx.close()


@pytest_asyncio.fixture
async def ui_page_system_member(_browser_session: Browser, auth_token_system_user2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_system_user2)
    yield page
    await ctx.close()


@pytest_asyncio.fixture
async def ui_page_company2(_browser_session: Browser, auth_token_company2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_company2)
    yield page
    await ctx.close()


@pytest_asyncio.fixture
async def ui_page_company2_member(_browser_session: Browser, auth_token_company2_user2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_company2_user2)
    yield page
    await ctx.close()


@pytest_asyncio.fixture
async def ui_user_system(auth_token_system: str) -> UiTestUser:
    return ui_test_user_from_token(UiPersona.SYSTEM_OWNER, auth_token_system)


@pytest_asyncio.fixture
async def ui_user_system_member(auth_token_system_user2: str) -> UiTestUser:
    return ui_test_user_from_token(UiPersona.SYSTEM_MEMBER, auth_token_system_user2)


@pytest_asyncio.fixture
async def ui_user_company2(auth_token_company2: str) -> UiTestUser:
    return ui_test_user_from_token(UiPersona.COMPANY2_OWNER, auth_token_company2)


@pytest_asyncio.fixture
async def ui_user_company2_member(auth_token_company2_user2: str) -> UiTestUser:
    return ui_test_user_from_token(UiPersona.COMPANY2_MEMBER, auth_token_company2_user2)


@pytest_asyncio.fixture
async def ui_user_anonymous() -> UiTestUser:
    return ANONYMOUS_UI_USER


@pytest_asyncio.fixture
async def sync_ui(sync_service, sync_worker) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY["sync"])


@pytest_asyncio.fixture
async def crm_ui(crm_service, rag_service, _ui_subdomain_mappings) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY["crm"])


@pytest_asyncio.fixture
async def rag_ui(rag_service, _ui_subdomain_mappings) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY["rag"])


@pytest_asyncio.fixture
async def flows_ui(flows_service) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY["flows"])


@pytest_asyncio.fixture
async def frontend_ui(frontend_service) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY["frontend"])
