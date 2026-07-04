"""Подсказки и диагностика для UI E2E (общая папка ``tests/ui/e2e``)."""

from __future__ import annotations

import pytest

from core.logging import get_logger
from tests.fixtures.e2e_scope import bind_static_e2e_scope


@pytest.fixture(autouse=True)
def platform_test_scope():
    """Статический scope фазы UI E2E: запросы браузера не несут X-Test-Scope."""
    with bind_static_e2e_scope() as scope:
        yield scope


@pytest.fixture
def embed_browser_http_stack_ready(
    flows_service,
    frontend_service,
    secrets_service,
    taskiq_worker,
):
    """Сразу после неё начинается тело теста — до этого живёт большая часть ожидания."""
    _ = secrets_service
    log = get_logger(__name__)
    log.info(
        "embed_browser_e2e: HTTP flows (9001) + frontend (9004) и taskiq готовы; "
        "первый холодный старт flows может занимать до startup_wait см. "
        "tests/fixtures/services.py"
    )
    yield
