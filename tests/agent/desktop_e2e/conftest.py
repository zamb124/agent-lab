"""HumanitecAgent desktop E2E: real release app + prod stack."""

from __future__ import annotations

import atexit
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, Timeout
from playwright.async_api import Browser, Page, async_playwright

from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.agent._helpers import AGENT_TEST_PUBLIC_ORIGIN
from tests.agent.desktop_e2e.desktop_app import (
    HumanitecDesktopInstall,
    ensure_humanitec_desktop_release_artifact,
    install_humanitec_desktop_release,
)
from tests.agent.desktop_e2e.electron_launcher import (
    HumanitecDesktopLaunchConfig,
    HumanitecDesktopProcess,
    _available_debug_port,
)
from tests.agent.desktop_e2e.goosed_helpers import (
    prepare_goosed_developer_session,
    prepare_goosed_session_with_extensions,
    wait_for_goosed_tools,
)
from tests.agent.desktop_e2e.helpers import (
    connect_desktop_browser,
    ensure_humanitec_paired_and_llm_ready,
    find_main_app_page,
    open_ready_main_page,
    pair_desktop_via_deep_link,
)
from tests.fixtures.e2e_scope import bind_static_e2e_scope
from tests.ui.browser_auth import add_auth_token_cookie
from tests.ui.click_highlight import install_click_highlight_on_context

_FORCE_LIGHT_THEME_INIT_SCRIPT = """
(() => {
    try {
        window.localStorage.setItem('platform_theme', 'light');
        window.localStorage.removeItem('platform:frontend:landing.agent_download_card.dismissed');
    } catch (_) {}
    const root = document.documentElement;
    if (root) {
        root.removeAttribute('data-platform-theme-lock');
        root.setAttribute('data-theme', 'light');
    }
})();
"""

# Все живые desktop-процессы сессии — чтобы не оставлять окна после timeout/fail.
_live_desktop_processes: list[HumanitecDesktopProcess] = []


def _stop_all_live_desktops() -> None:
    while _live_desktop_processes:
        process = _live_desktop_processes.pop()
        process.stop()


atexit.register(_stop_all_live_desktops)


@pytest.fixture(autouse=True)
def platform_test_scope():
    """Статический scope фазы desktop E2E: запросы Electron не несут X-Test-Scope."""
    with bind_static_e2e_scope() as scope:
        yield scope


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Fail-fast: desktop E2E не должны висеть минутами на сломанном pairing/окне.
    for item in items:
        item.add_marker(pytest.mark.timeout(15, func_only=True))

    if not os.environ.get("AGENT_DESKTOP_E2E_RUN"):
        # Явный opt-in: desktop E2E не должны стартовать из широкого `pytest tests/` (xdist, без Electron).
        # Make-цели phase 4 / test-agent-desktop-e2e выставляют AGENT_DESKTOP_E2E_RUN=1.
        skip_desktop = pytest.mark.skip(reason="AGENT_DESKTOP_E2E_RUN not set")
        for item in items:
            path = str(item.fspath) if hasattr(item, "fspath") else ""
            if "/desktop_e2e/" in path:
                item.add_marker(skip_desktop)


@pytest.fixture(scope="session", autouse=True)
def agent_desktop_lvh_me_profile() -> None:
    os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")
    os.environ.setdefault("AGENT_ARTIFACT_MODE", "release")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_live_desktop_processes() -> Iterator[None]:
    yield
    _stop_all_live_desktops()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _ = session
    _ = exitstatus
    _stop_all_live_desktops()


@pytest.fixture(scope="session")
def agent_desktop_base_url() -> str:
    """System-company frontend origin для сценариев с ui_page_system (pairing в settings)."""
    configured = os.environ.get("AGENT_DESKTOP_E2E_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return AGENT_TEST_PUBLIC_ORIGIN.rstrip("/")


@pytest_asyncio.fixture(scope="session")
async def _desktop_browser_session() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest_asyncio.fixture
async def ui_page_system(
    _desktop_browser_session: Browser,
    auth_token_system: str,
) -> AsyncIterator[Page]:
    context = await _desktop_browser_session.new_context(color_scheme="light")
    await context.add_init_script(_FORCE_LIGHT_THEME_INIT_SCRIPT)
    await install_click_highlight_on_context(context)
    await add_auth_token_cookie(context, auth_token_system)
    page = await context.new_page()
    try:
        yield page
    finally:
        await context.close()


@pytest.fixture(scope="session")
def humanitec_desktop_release_artifact() -> str:
    artifact = ensure_humanitec_desktop_release_artifact()
    return str(artifact)


@pytest.fixture(scope="session")
def humanitec_desktop_install(
    humanitec_desktop_release_artifact: str,
) -> Iterator[HumanitecDesktopInstall]:
    artifact_path = __import__("pathlib").Path(humanitec_desktop_release_artifact)
    install = install_humanitec_desktop_release(artifact_path)
    yield install
    _stop_all_live_desktops()
    install.cleanup()


@pytest.fixture
def humanitec_desktop_system_process_factory(
    humanitec_desktop_install: HumanitecDesktopInstall,
) -> Iterator[Callable[[], HumanitecDesktopProcess]]:
    """Desktop на system.lvh.me — только для pairing через ui_page_system."""

    system_base_url = AGENT_TEST_PUBLIC_ORIGIN.rstrip("/")
    created: list[HumanitecDesktopProcess] = []

    def _factory() -> HumanitecDesktopProcess:
        process = HumanitecDesktopProcess(
            HumanitecDesktopLaunchConfig(
                frontend_base_url=system_base_url,
                install=humanitec_desktop_install,
                remote_debugging_port=_available_debug_port(),
            )
        )
        created.append(process)
        _live_desktop_processes.append(process)
        return process

    yield _factory
    for process in created:
        process.stop()
        if process in _live_desktop_processes:
            _live_desktop_processes.remove(process)


@pytest.fixture
def humanitec_desktop_process_factory(
    humanitec_desktop_install: HumanitecDesktopInstall,
    agent_base_url: str,
) -> Iterator[Callable[[], HumanitecDesktopProcess]]:
    """Новый Electron на каждый вызов; stop() всегда убивает process group.

    Shared-by-base_url нельзя: у каждого теста свой company Host, а no-op stop
    оставлял десятки LinnexAgent после timeout.
    """
    created: list[HumanitecDesktopProcess] = []

    def _factory() -> HumanitecDesktopProcess:
        process = HumanitecDesktopProcess(
            HumanitecDesktopLaunchConfig(
                frontend_base_url=agent_base_url,
                install=humanitec_desktop_install,
                remote_debugging_port=_available_debug_port(),
            )
        )
        created.append(process)
        _live_desktop_processes.append(process)
        return process

    yield _factory
    for process in created:
        process.stop()
        if process in _live_desktop_processes:
            _live_desktop_processes.remove(process)


@pytest.fixture(autouse=True)
def agent_desktop_requires_frontend_service(frontend_service: None) -> None:
    _ = frontend_service


@dataclass(frozen=True)
class GooseDeveloperRuntime:
    desktop: HumanitecDesktopProcess
    page: Page
    session_id: str
    workspace: Path


@dataclass(frozen=True)
class _GooseDeveloperAuth:
    auth_token: str
    base_url: str


@pytest_asyncio.fixture(scope="module")
async def goose_developer_auth(
    frontend_container,
    test_company_subdomains_initialized,
) -> _GooseDeveloperAuth:
    """Один company Host на модуль developer-тестов — без pairing storm на каждый тест."""
    _ = test_company_subdomains_initialized
    user_id = f"goose_dev_user_{uuid.uuid4().hex[:8]}"
    company_id = f"goose_dev_company_{uuid.uuid4().hex[:8]}"
    company_subdomain = f"goose-dev-{uuid.uuid4().hex[:8]}"
    company = Company(
        company_id=company_id,
        name="Goose Developer E2E",
        subdomain=company_subdomain,
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
    )
    await frontend_container.company_repository.set(company)
    await frontend_container.subdomain_repository.set_mapping(company_subdomain, company_id)
    user = User(
        user_id=user_id,
        name="Goose Developer User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["owner", "admin"], "system": ["admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    system_company = await frontend_container.company_repository.get("system")
    if system_company is None:
        raise RuntimeError("system company missing for goose developer auth")
    if user_id not in system_company.members:
        system_company.members[user_id] = ["admin"]
        await frontend_container.company_repository.set(system_company)
    token = get_token_service().create_token(user_id, company_id=company_id)
    return _GooseDeveloperAuth(
        auth_token=token,
        base_url=f"http://{company_subdomain}.lvh.me:9004",
    )


@pytest_asyncio.fixture(scope="module")
async def goose_developer_runtime(
    goose_developer_auth: _GooseDeveloperAuth,
    humanitec_desktop_install: HumanitecDesktopInstall,
    frontend_service: None,
) -> AsyncIterator[GooseDeveloperRuntime]:
    """Один Electron + pairing + goosed session на весь модуль developer-тестов.

    Setup вне func_only timeout; без повторного pairing на каждый test_* —
    иначе single-worker frontend даёт ConnectTimeout.
    """
    _ = frontend_service
    desktop = HumanitecDesktopProcess(
        HumanitecDesktopLaunchConfig(
            frontend_base_url=goose_developer_auth.base_url,
            install=humanitec_desktop_install,
            remote_debugging_port=_available_debug_port(),
        )
    )
    _live_desktop_processes.append(desktop)
    workspace = desktop.user_data_dir / "goose" / "workspace"
    playwright = await async_playwright().start()
    try:
        desktop.start()
        browser = await connect_desktop_browser(playwright, desktop)
        page = await find_main_app_page(browser)
        workspace.mkdir(parents=True, exist_ok=True)
        async with AsyncClient(
            base_url=goose_developer_auth.base_url,
            follow_redirects=False,
            cookies={"auth_token": goose_developer_auth.auth_token},
            timeout=Timeout(30.0, connect=10.0),
        ) as agent_frontend_http_client:
            session_id = await prepare_goosed_developer_session(
                page,
                workspace,
                desktop=desktop,
                agent_frontend_http_client=agent_frontend_http_client,
                auth_token=goose_developer_auth.auth_token,
            )
        yield GooseDeveloperRuntime(
            desktop=desktop,
            page=page,
            session_id=session_id,
            workspace=workspace,
        )
    finally:
        desktop.stop()
        if desktop in _live_desktop_processes:
            _live_desktop_processes.remove(desktop)
        await playwright.stop()


@dataclass(frozen=True)
class GoosedExtensionSessionSpec:
    """Параметр `goosed_extension_session` (indirect parametrize).

    `wait_tool_suffix` — если задан, fixture дожидается появления тула в
    goosed до yield, вне func_only timeout теста.
    """

    extension_display_names: list[str]
    workspace_suffix: str
    wait_tool_suffix: str | None = None


@dataclass(frozen=True)
class GoosedExtensionSession:
    desktop: HumanitecDesktopProcess
    page: Page
    session_id: str
    workspace: Path


@pytest_asyncio.fixture
async def goosed_extension_session(
    request: pytest.FixtureRequest,
    humanitec_desktop_process_factory: Callable[[], HumanitecDesktopProcess],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> AsyncIterator[GoosedExtensionSession]:
    """Electron start + pairing + LLM ready + extension enable + goosed session.

    Bootstrap живёт в fixture setup, вне `pytest.mark.timeout(15, func_only=True)`
    (`pytest_collection_modifyitems`) — тело теста делает только tool call(s)
    и assert, укладываясь в 15s без ложных таймаутов на реальном bootstrap.
    """
    spec: GoosedExtensionSessionSpec = request.param
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / f"goose-workspace-{spec.workspace_suffix}"
    desktop.start()
    playwright = await async_playwright().start()
    try:
        browser = await connect_desktop_browser(playwright, desktop)
        page = await find_main_app_page(browser)
        session_id = await prepare_goosed_session_with_extensions(
            page,
            workspace,
            desktop=desktop,
            agent_frontend_http_client=agent_frontend_http_client,
            auth_token=auth_token,
            enabled_extensions=spec.extension_display_names,
        )
        if spec.wait_tool_suffix is not None:
            await wait_for_goosed_tools(page, session_id, name_suffix=spec.wait_tool_suffix)
        yield GoosedExtensionSession(
            desktop=desktop,
            page=page,
            session_id=session_id,
            workspace=workspace,
        )
    finally:
        await playwright.stop()
        desktop.stop()


@dataclass(frozen=True)
class PairedDesktopSession:
    desktop: HumanitecDesktopProcess
    page: Page


@pytest_asyncio.fixture
async def paired_desktop_session(
    humanitec_desktop_process_factory: Callable[[], HumanitecDesktopProcess],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> AsyncIterator[PairedDesktopSession]:
    """Electron start + pairing + LLM ready, без goosed session/extensions.

    Bootstrap живёт в fixture setup, вне func_only(15s) теста — см.
    `goosed_extension_session`.
    """
    desktop = humanitec_desktop_process_factory()
    desktop.start()
    playwright = await async_playwright().start()
    try:
        browser = await connect_desktop_browser(playwright, desktop)
        page = await find_main_app_page(browser)
        await ensure_humanitec_paired_and_llm_ready(
            desktop,
            page,
            agent_frontend_http_client,
            auth_token,
        )
        yield PairedDesktopSession(desktop=desktop, page=page)
    finally:
        await playwright.stop()
        desktop.stop()


@dataclass(frozen=True)
class GoosedDeveloperOnlySession:
    desktop: HumanitecDesktopProcess
    page: Page
    session_id: str
    workspace: Path


@pytest_asyncio.fixture
async def goosed_developer_only_session(
    request: pytest.FixtureRequest,
    humanitec_desktop_process_factory: Callable[[], HumanitecDesktopProcess],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> AsyncIterator[GoosedDeveloperOnlySession]:
    """Electron start + pairing + Developer goosed session (без индирект-параметра — extensions не меняются).

    `request.param` — суффикс имени workspace-директории (`str`).
    """
    workspace_suffix: str = request.param
    desktop = humanitec_desktop_process_factory()
    workspace = desktop.user_data_dir / f"goose-workspace-{workspace_suffix}"
    desktop.start()
    playwright = await async_playwright().start()
    try:
        browser = await connect_desktop_browser(playwright, desktop)
        page = await find_main_app_page(browser)
        session_id = await prepare_goosed_developer_session(
            page,
            workspace,
            desktop=desktop,
            agent_frontend_http_client=agent_frontend_http_client,
            auth_token=auth_token,
        )
        yield GoosedDeveloperOnlySession(
            desktop=desktop,
            page=page,
            session_id=session_id,
            workspace=workspace,
        )
    finally:
        await playwright.stop()
        desktop.stop()


@dataclass(frozen=True)
class PairedDesktopDeepLink:
    desktop: HumanitecDesktopProcess
    device_id: str
    credentials: dict[str, str]


@pytest_asyncio.fixture
async def paired_desktop_deep_link(
    humanitec_desktop_process_factory: Callable[[], HumanitecDesktopProcess],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> AsyncIterator[PairedDesktopDeepLink]:
    """Electron start + pairing через deep link, без UI страницы.

    Для тестов, которым нужны только credentials/device_id (MCP-вызовы,
    revoke), а не открытая страница чата/настроек.
    """
    desktop = humanitec_desktop_process_factory()
    desktop.start()
    device_id, credentials = await pair_desktop_via_deep_link(
        desktop,
        agent_frontend_http_client,
        auth_token,
    )
    try:
        yield PairedDesktopDeepLink(desktop=desktop, device_id=device_id, credentials=credentials)
    finally:
        desktop.stop()


@dataclass(frozen=True)
class PairedDesktopUiSession:
    desktop: HumanitecDesktopProcess
    page: Page
    device_id: str
    credentials: dict[str, str]


@pytest_asyncio.fixture
async def paired_desktop_ui_session(
    humanitec_desktop_process_factory: Callable[[], HumanitecDesktopProcess],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> AsyncIterator[PairedDesktopUiSession]:
    """Electron start + pairing + chat-ready main page.

    Bootstrap живёт в fixture setup, вне func_only(15s) теста — тело теста
    делает только MCP tool call(s) и/или проверку конкретного UI-элемента.
    """
    desktop = humanitec_desktop_process_factory()
    desktop.start()
    device_id, credentials = await pair_desktop_via_deep_link(
        desktop,
        agent_frontend_http_client,
        auth_token,
    )
    playwright = await async_playwright().start()
    try:
        browser = await connect_desktop_browser(playwright, desktop)
        page = await open_ready_main_page(browser)
        yield PairedDesktopUiSession(
            desktop=desktop,
            page=page,
            device_id=device_id,
            credentials=credentials,
        )
    finally:
        await playwright.stop()
        desktop.stop()


@pytest.fixture
def flows_worker(taskiq_worker):
    return taskiq_worker


@pytest.fixture
def flows_container(container):
    return container


@pytest_asyncio.fixture
async def mock_llm_with_queue(
    mock_llm_redis: Callable[[list[Any]], Awaitable[None]],
) -> Callable[[list[Any]], Awaitable[None]]:
    async def _factory(responses: list[Any]) -> None:
        await mock_llm_redis(responses)

    return _factory
