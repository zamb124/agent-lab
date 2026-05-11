"""Подсказки и диагностика для UI E2E (общая папка ``tests/ui/e2e``)."""

from __future__ import annotations

import pytest

from core.logging import get_logger


@pytest.fixture
def embed_browser_http_stack_ready(
    flows_service,
    frontend_service,
    taskiq_worker,
):
    """Сразу после неё начинается тело теста — до этого живёт большая часть ожидания."""
    log = get_logger(__name__)
    log.info(
        "embed_browser_e2e: HTTP flows (9001) + frontend (9004) и taskiq готовы; "
        "первый холодный старт flows может занимать до startup_wait см. "
        "tests/fixtures/services.py"
    )
    yield
