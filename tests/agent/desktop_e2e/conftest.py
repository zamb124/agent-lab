"""HumanitecAgent desktop E2E: real release app + prod stack."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio

from tests.agent.desktop_e2e.desktop_app import (
    HumanitecDesktopInstall,
    ensure_humanitec_desktop_release_artifact,
    install_humanitec_desktop_release,
)
from tests.agent.desktop_e2e.electron_launcher import (
    HumanitecDesktopLaunchConfig,
    HumanitecDesktopProcess,
)

def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.timeout(900))


@pytest.fixture(scope="session", autouse=True)
def agent_desktop_lvh_me_profile() -> None:
    os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")
    os.environ.setdefault(
        "AGENT_DESKTOP_E2E_BASE_URL",
        "http://system.lvh.me:9004",
    )
    os.environ.setdefault("AGENT_ARTIFACT_MODE", "release")


@pytest.fixture(scope="session")
def agent_desktop_base_url() -> str:
    configured = os.environ.get("AGENT_DESKTOP_E2E_BASE_URL")
    if not configured:
        raise ValueError("AGENT_DESKTOP_E2E_BASE_URL is required")
    return configured.rstrip("/")


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


@pytest.fixture
def humanitec_desktop_process_factory(
    humanitec_desktop_install: HumanitecDesktopInstall,
    agent_desktop_base_url: str,
) -> Callable[[], HumanitecDesktopProcess]:
    def _factory() -> HumanitecDesktopProcess:
        return HumanitecDesktopProcess(
            HumanitecDesktopLaunchConfig(
                frontend_base_url=agent_desktop_base_url,
                install=humanitec_desktop_install,
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
