"""Подсказки и диагностика для UI E2E (общая папка ``tests/ui/e2e``)."""

from __future__ import annotations

import pytest

from core.logging import get_logger
from tests.fixtures.e2e_scope import bind_static_e2e_scope

_AGENT_SETTINGS_EMPTY_STATE_TESTS = frozenset({
    "test_f3_settings_agent_devices_empty",
    "test_f4_settings_agent_audit_empty",
})
_AGENT_SETTINGS_MUTATING_TESTS = frozenset({
    "test_f9_settings_agent_devices_after_pair",
    "test_f10_settings_agent_revoke_device",
    "test_f11_settings_agent_policy_shell_toggle",
    "test_f12_settings_agent_audit_after_register",
})
_AGENT_SETTINGS_MODULE_SUFFIX = "test_frontend_settings_agent.py"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Пустые сценарии f3/f4 до тестов, мутирующих devices/audit (f9–f12)."""
    _ = config
    positions = [
        (index, item)
        for index, item in enumerate(items)
        if item.nodeid.endswith(_AGENT_SETTINGS_MODULE_SUFFIX)
    ]
    if not positions:
        return

    agent_items = [item for _, item in positions]
    early = [item for item in agent_items if item.name in _AGENT_SETTINGS_EMPTY_STATE_TESTS]
    late = [item for item in agent_items if item.name in _AGENT_SETTINGS_MUTATING_TESTS]
    middle = [
        item
        for item in agent_items
        if item.name not in _AGENT_SETTINGS_EMPTY_STATE_TESTS
        and item.name not in _AGENT_SETTINGS_MUTATING_TESTS
    ]
    reordered = early + middle + late
    for position, new_item in zip((index for index, _ in positions), reordered):
        items[position] = new_item


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
