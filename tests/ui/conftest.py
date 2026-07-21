"""Фикстуры `*_ui`, персоны браузера и async Playwright (совместимо с pytest-asyncio)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.auth_worker_fixtures import (
    create_ui_e2e_company2_member_token,
    create_ui_e2e_company2_owner_token,
    create_ui_e2e_member_token,
    create_ui_e2e_owner_token,
)
from tests.ui.browser_auth import add_auth_token_cookie
from tests.ui.click_highlight import install_click_highlight_on_context
from tests.ui.e2e_worker import publish_ui_e2e_worker_env, ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.perf.collector import get_current_collector
from tests.ui.personas import ANONYMOUS_UI_USER, UiPersona, UiTestUser, ui_test_user_from_token
from tests.ui.scenario_doc import ScenarioRecorder
from tests.ui.subdomain_setup import ensure_ui_subdomain_mappings

_FORCE_LIGHT_THEME_INIT_SCRIPT = """
(() => {
    try {
        window.localStorage.setItem('platform_theme', 'light');
        window.localStorage.setItem('pwa-banner-dismissed', 'true');
        window.localStorage.removeItem('platform:frontend:landing.agent_download_card.dismissed');
    } catch (_) {}
    const root = document.documentElement;
    if (root) {
        root.removeAttribute('data-platform-theme-lock');
        root.setAttribute('data-theme', 'light');
    }
    // E2E: баннер живёт в shadow DOM PlatformApp — document CSS его не скрывает.
    const dismissPwaInTree = (root) => {
        if (!root || typeof root.querySelectorAll !== 'function') return;
        for (const banner of root.querySelectorAll('pwa-install-banner')) {
            banner._dismissed = true;
            banner.removeAttribute('visible');
            banner.style.setProperty('display', 'none', 'important');
            banner.style.setProperty('pointer-events', 'none', 'important');
            if (typeof banner.requestUpdate === 'function') banner.requestUpdate();
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) dismissPwaInTree(el.shadowRoot);
        }
    };
    const sweepPwa = () => dismissPwaInTree(document);
    const startObserver = () => {
        const root = document.documentElement;
        if (!root) return;
        sweepPwa();
        const mo = new MutationObserver(sweepPwa);
        mo.observe(root, { childList: true, subtree: true });
    };
    sweepPwa();
    if (document.documentElement) {
        startObserver();
    } else if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startObserver, { once: true });
    }
})();
"""


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ui_e2e_worker_env() -> None:
    """Публикует UI_E2E_* env до AppUI.origin / cookie domains."""
    publish_ui_e2e_worker_env()


@pytest_asyncio.fixture(scope="session")
async def auth_token_system(frontend_container) -> str:
    """Owner worker-компании (имя фикстуры сохранено для совместимости с E2E)."""
    return await create_ui_e2e_owner_token(frontend_container)


@pytest_asyncio.fixture(scope="session")
async def auth_token_system_user2(frontend_container, auth_token_system: str) -> str:
    _ = auth_token_system
    return await create_ui_e2e_member_token(frontend_container)


@pytest_asyncio.fixture(scope="session")
async def auth_token_company2(frontend_container) -> str:
    return await create_ui_e2e_company2_owner_token(frontend_container)


@pytest_asyncio.fixture(scope="session")
async def auth_token_company2_user2(frontend_container, auth_token_company2: str) -> str:
    _ = auth_token_company2
    return await create_ui_e2e_company2_member_token(frontend_container)


@pytest_asyncio.fixture
async def scenario(request: pytest.FixtureRequest) -> ScenarioRecorder:
    """Пишет README RU/EN и именованные PNG рядом: docs/scenarios/<service>/<tag>/<slug>/."""
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
    """Один раз на worker: компании ui_e2e_gwN / _c2 и четыре пользователя."""


@pytest_asyncio.fixture(scope="session")
async def _ui_subdomain_mappings(
    frontend_container,
    auth_token_system: str,
    auth_token_company2: str,
) -> None:
    """Субдомены worker-компаний для Lit-SPA с frontend-контекстом."""
    _ = auth_token_system, auth_token_company2
    await ensure_ui_subdomain_mappings(frontend_container)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ui_e2e_company_resources(
    _ui_e2e_identities_ready: None,
    _ui_subdomain_mappings: None,
    flows_service,
    taskiq_worker,
    crm_service,
) -> None:
    """Public flows/tools/Lara + CRM types для worker-компаний (не shared system)."""
    _ = flows_service, taskiq_worker, crm_service
    from apps.crm.container import get_crm_container
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from tests.ui.e2e_worker import (
        ui_e2e_company2_id,
        ui_e2e_company_id,
        ui_e2e_subdomain,
        ui_e2e_subdomain_company2,
    )

    from tests.sync.api._helpers import _temporary_company_context

    for company_id, subdomain in (
        (ui_e2e_company_id(), ui_e2e_subdomain()),
        (ui_e2e_company2_id(), ui_e2e_subdomain_company2()),
    ):
        init_result = await init_company_resources(
            company_id=company_id,
            company_name=f"UI E2E {company_id}",
            subdomain=subdomain,
        )
        if init_result.get("status") != "completed":
            raise AssertionError(
                f"init_company_resources failed for {company_id}: {init_result}"
            )
        with _temporary_company_context(company_id, subdomain=subdomain):
            await get_crm_container().company_init_service.initialize_company(company_id)


async def _new_browser_context(
    browser: Browser,
    *,
    with_test_scope: bool = True,
) -> BrowserContext:
    context_kwargs: dict[str, object] = {"color_scheme": "light"}
    if with_test_scope:
        # Authenticated SPA + MockLLM. Anonymous/embed (внешний origin) — без
        # X-Test-Scope: иначе CORS preflight на embed API падает до Allow-Headers.
        context_kwargs["extra_http_headers"] = ui_e2e_scope_headers()
    context = await browser.new_context(**context_kwargs)
    await context.add_init_script(_FORCE_LIGHT_THEME_INIT_SCRIPT)
    # Office share / copy link; без grant headless clipboard.writeText падает.
    await context.grant_permissions(["clipboard-read", "clipboard-write"])
    await install_click_highlight_on_context(context)
    collector = get_current_collector()
    if collector is not None:
        await collector.attach_to_context(context)
    return context


async def _close_browser_context(context: BrowserContext) -> None:
    collector = get_current_collector()
    if collector is not None:
        await collector.capture_context(context)
    await context.close()


@pytest_asyncio.fixture
async def page(_browser_session: Browser) -> Page:
    """Браузер без cookie — редирект на логин / embed host без X-Test-Scope."""
    context = await _new_browser_context(_browser_session, with_test_scope=False)
    p = await context.new_page()
    yield p
    await _close_browser_context(context)


@pytest_asyncio.fixture
async def ui_page_anonymous(page: Page) -> Page:
    """Явное имя для неаутентифицированного контекста (то же, что `page`)."""
    return page


async def _authenticated_page(browser: Browser, token: str) -> tuple[Page, BrowserContext]:
    context = await _new_browser_context(browser)
    await add_auth_token_cookie(context, token)
    page = await context.new_page()
    return page, context


@pytest_asyncio.fixture
async def ui_page_system(_browser_session: Browser, auth_token_system: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_system)
    yield page
    await _close_browser_context(ctx)


@pytest_asyncio.fixture
async def ui_page_system_member(_browser_session: Browser, auth_token_system_user2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_system_user2)
    yield page
    await _close_browser_context(ctx)


@pytest_asyncio.fixture
async def ui_page_company2(_browser_session: Browser, auth_token_company2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_company2)
    yield page
    await _close_browser_context(ctx)


@pytest_asyncio.fixture
async def ui_page_company2_member(_browser_session: Browser, auth_token_company2_user2: str) -> Page:
    page, ctx = await _authenticated_page(_browser_session, auth_token_company2_user2)
    yield page
    await _close_browser_context(ctx)


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
async def sync_ui(
    sync_service,
    sync_worker,
    _ui_subdomain_mappings,
    _ui_e2e_company_resources,
) -> AppUI:
    _ = sync_service, sync_worker, _ui_subdomain_mappings, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["sync"])


@pytest_asyncio.fixture
async def crm_ui(
    crm_service,
    rag_service,
    _ui_subdomain_mappings,
    _ui_e2e_company_resources,
) -> AppUI:
    _ = crm_service, rag_service, _ui_subdomain_mappings, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["crm"])


@pytest_asyncio.fixture
async def rag_ui(rag_service, _ui_subdomain_mappings, _ui_e2e_company_resources) -> AppUI:
    _ = rag_service, _ui_subdomain_mappings, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["rag"])


@pytest_asyncio.fixture
async def flows_ui(flows_service, _ui_e2e_company_resources) -> AppUI:
    _ = flows_service, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["flows"])


@pytest_asyncio.fixture
async def frontend_ui(frontend_service, _ui_e2e_company_resources) -> AppUI:
    _ = frontend_service, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["frontend"])


@pytest_asyncio.fixture
async def office_ui(
    office_service,
    _ui_subdomain_mappings,
    _ui_e2e_company_resources,
) -> AppUI:
    _ = office_service, _ui_subdomain_mappings, _ui_e2e_company_resources
    return AppUI(SERVICE_UI_REGISTRY["office"])


@pytest_asyncio.fixture
async def worktracker_ui(
    worktracker_http_service,
    flows_service,
    _ui_subdomain_mappings,
) -> AppUI:
    _ = worktracker_http_service, flows_service, _ui_subdomain_mappings
    return AppUI(SERVICE_UI_REGISTRY["worktracker"])


@pytest_asyncio.fixture
async def litserve_ui(provider_litserve_service) -> AppUI:
    _ = provider_litserve_service
    return AppUI(SERVICE_UI_REGISTRY["litserve"])


@pytest_asyncio.fixture
async def hitl_demo_ready(
    flows_service,
    worktracker_http_service,
    flows_ui: AppUI,
    auth_token_system: str,
    system_user_id: str,
    _ui_e2e_company_resources: None,
) -> str:
    """Демо-очередь example_hitl и участник owner worker-компании для HITL E2E."""
    _ = flows_service, worktracker_http_service, _ui_e2e_company_resources
    from tests.ui.e2e.hitl_e2e_bridge import hitl_ensure_demo_queue_member

    return await hitl_ensure_demo_queue_member(
        flows_ui.origin,
        auth_token_system,
        system_user_id,
    )
