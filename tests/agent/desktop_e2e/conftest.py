"""HumanitecAgent desktop E2E: real release app + prod stack."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio

from tests.agent._helpers import AGENT_TEST_PUBLIC_ORIGIN
from tests.agent.desktop_e2e.desktop_app import (
    HumanitecDesktopInstall,
    ensure_humanitec_desktop_release_artifact,
    install_humanitec_desktop_release,
)
from tests.agent.desktop_e2e.electron_launcher import (
    DEFAULT_DEBUG_PORT,
    HumanitecDesktopLaunchConfig,
    HumanitecDesktopProcess,
)
from tests.fixtures.e2e_scope import bind_static_e2e_scope

_next_desktop_debug_port = DEFAULT_DEBUG_PORT + 1
_shared_desktops_by_base_url: dict[str, HumanitecDesktopProcess] = {}


class _SharedHumanitecDesktopProcess:
    """Один Electron на base_url за pytest-сессию: start/stop в тестах — no-op."""

    def __init__(self, process: HumanitecDesktopProcess) -> None:
        self._process = process

    def start(self) -> None:
        if self._process._process is None:
            self._process.start()

    def stop(self) -> None:
        return

    def __getattr__(self, name: str) -> object:
        return getattr(self._process, name)


def _needs_fresh_desktop_process(request: pytest.FixtureRequest) -> bool:
    if request.node.get_closest_marker("desktop_fresh_process") is not None:
        return True
    nodeid = request.node.nodeid
    return (
        "test_agent_desktop_auth_pairing.py" in nodeid
        or "test_agent_desktop_electron.py" in nodeid
    )


@pytest.fixture(autouse=True)
def platform_test_scope():
    """Статический scope фазы desktop E2E: запросы Electron не несут X-Test-Scope."""
    with bind_static_e2e_scope() as scope:
        yield scope


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.timeout(900))

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
def _cleanup_shared_desktop_processes() -> None:
    yield
    for process in _shared_desktops_by_base_url.values():
        process.stop()
    _shared_desktops_by_base_url.clear()


@pytest.fixture(scope="session")
def agent_desktop_base_url() -> str:
    """System-company frontend origin для сценариев с ui_page_system (pairing в settings)."""
    configured = os.environ.get("AGENT_DESKTOP_E2E_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return AGENT_TEST_PUBLIC_ORIGIN.rstrip("/")


@pytest.fixture(scope="session")
def humanitec_desktop_release_artifact() -> str:
    artifact = ensure_humanitec_desktop_release_artifact()
    return str(artifact)


@pytest.fixture(scope="session")
def humanitec_desktop_install(
    humanitec_desktop_release_artifact: str,
) -> HumanitecDesktopInstall:
    artifact_path = __import__("pathlib").Path(humanitec_desktop_release_artifact)
    install = install_humanitec_desktop_release(artifact_path)
    yield install
    install.cleanup()


@pytest_asyncio.fixture
async def humanitec_desktop_process_factory(
    request: pytest.FixtureRequest,
    humanitec_desktop_install: HumanitecDesktopInstall,
    agent_base_url: str,
) -> Callable[[], HumanitecDesktopProcess | _SharedHumanitecDesktopProcess]:
    """Desktop на Host той же test-компании, что auth_token и agent_frontend_http_client."""

    def _factory() -> HumanitecDesktopProcess | _SharedHumanitecDesktopProcess:
        if _needs_fresh_desktop_process(request):
            global _next_desktop_debug_port
            debug_port = _next_desktop_debug_port
            _next_desktop_debug_port += 1
            return HumanitecDesktopProcess(
                HumanitecDesktopLaunchConfig(
                    frontend_base_url=agent_base_url,
                    install=humanitec_desktop_install,
                    remote_debugging_port=debug_port,
                )
            )
        shared = _shared_desktops_by_base_url.get(agent_base_url)
        if shared is None:
            shared = HumanitecDesktopProcess(
                HumanitecDesktopLaunchConfig(
                    frontend_base_url=agent_base_url,
                    install=humanitec_desktop_install,
                    remote_debugging_port=DEFAULT_DEBUG_PORT,
                )
            )
            _shared_desktops_by_base_url[agent_base_url] = shared
        return _SharedHumanitecDesktopProcess(shared)

    return _factory


@pytest.fixture
def humanitec_desktop_system_process_factory(
    humanitec_desktop_install: HumanitecDesktopInstall,
) -> Callable[[], HumanitecDesktopProcess]:
    """Desktop на system.lvh.me — только для pairing через ui_page_system."""

    system_base_url = AGENT_TEST_PUBLIC_ORIGIN.rstrip("/")

    def _factory() -> HumanitecDesktopProcess:
        global _next_desktop_debug_port
        debug_port = _next_desktop_debug_port
        _next_desktop_debug_port += 1
        return HumanitecDesktopProcess(
            HumanitecDesktopLaunchConfig(
                frontend_base_url=system_base_url,
                install=humanitec_desktop_install,
                remote_debugging_port=debug_port,
            )
        )

    return _factory


@pytest.fixture(autouse=True)
def agent_desktop_requires_frontend_service(frontend_service: None) -> None:
    _ = frontend_service


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
