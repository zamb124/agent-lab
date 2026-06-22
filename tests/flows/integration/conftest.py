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


@pytest.fixture(autouse=True)
def _ensure_sandbox_contour(sandbox_services: dict[str, str]) -> None:
    _ = sandbox_services
