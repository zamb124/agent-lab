"""Подсказки и диагностика для UI E2E (общая папка ``tests/ui/e2e``)."""

from __future__ import annotations

import pytest

from core.logging import get_logger
from tests.ui.e2e_worker import bind_ui_e2e_worker_scope

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
# Жёсткий бюджет UI E2E: сломанный locator/ожидание не должны жечь минуты.
# Дольше — opt-in `scenario(timeout_seconds=N)` и/или `@pytest.mark.timeout(N)` (15..360).
_UI_E2E_TIMEOUT_SECONDS = 15
_UI_E2E_MAX_TIMEOUT_SECONDS = 360


def _is_ui_e2e_item(item: pytest.Item) -> bool:
    path = str(getattr(item, "path", "") or getattr(item, "fspath", ""))
    return "/tests/ui/e2e/" in path.replace("\\", "/")


def _resolve_ui_e2e_timeout_seconds(item: pytest.Item) -> int:
    """Берём max(scenario.timeout_seconds, @timeout), если оба в диапазоне 15..300."""
    candidates: list[int] = []
    scenario = item.get_closest_marker("scenario")
    requested = None if scenario is None else scenario.kwargs.get("timeout_seconds")
    if (
        isinstance(requested, int)
        and not isinstance(requested, bool)
        and _UI_E2E_TIMEOUT_SECONDS <= requested <= _UI_E2E_MAX_TIMEOUT_SECONDS
    ):
        candidates.append(requested)
    timeout_marker = item.get_closest_marker("timeout")
    if timeout_marker is not None and timeout_marker.args:
        mark_timeout = timeout_marker.args[0]
        if (
            isinstance(mark_timeout, int)
            and not isinstance(mark_timeout, bool)
            and _UI_E2E_TIMEOUT_SECONDS <= mark_timeout <= _UI_E2E_MAX_TIMEOUT_SECONDS
        ):
            candidates.append(mark_timeout)
    if candidates:
        return max(candidates)
    return _UI_E2E_TIMEOUT_SECONDS


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Политика UI E2E: дефолт 15s; scenario(timeout_seconds) или @timeout(N) для длинных."""
    _ = config
    for item in items:
        if not _is_ui_e2e_item(item):
            continue
        item.add_marker(
            pytest.mark.timeout(_resolve_ui_e2e_timeout_seconds(item), func_only=True),
            append=False,
        )

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
    """Per-worker MockLLM scope (`test_e2e_gwN`); браузер шлёт тот же X-Test-Scope."""
    with bind_ui_e2e_worker_scope() as scope:
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
