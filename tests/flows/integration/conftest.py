"""Общие фикстуры flows integration.

Любой flows-integration тест исполняет флоу, а ноды и тулы с кодом идут через
RemoteCodeRunner -> capability_gateway + code-runner-*. Без явной зависимости от
sandbox-контура тест проходил только когда сосед по xdist-воркеру уже стартовал
сайдкары: отсюда воркер/порядок-зависимая флакость, таймауты под -n auto и
ConnectError при изолированном запуске. Autouse-зависимость на session-scoped
sandbox_services делает контур детерминированно поднятым для всего пакета.
"""

from __future__ import annotations

import pytest

from tests.flows.integration.notification_server import (  # noqa: F401
    NotificationServer,
    notification_server,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """pytestmark в conftest не наследуется модулями — маркируем integration явно."""
    for item in items:
        if item.nodeid.startswith("tests/flows/integration/"):
            if item.get_closest_marker("integration") is None:
                item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _ensure_sandbox_contour(sandbox_services: dict[str, str]) -> None:
    _ = sandbox_services
