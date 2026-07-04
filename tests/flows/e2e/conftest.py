"""Общие фикстуры flows e2e.

E2E-тесты исполняют flow с code-нодами и tools через RemoteCodeRunner ->
capability_gateway + code-runner-*. Без sandbox-контура тесты падают с ConnectError
при изолированном запуске. Autouse-зависимость на session-scoped sandbox_services
делает контур детерминированно поднятым для всего пакета.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ensure_sandbox_contour_e2e(sandbox_services: dict[str, str]) -> None:
    _ = sandbox_services
