"""`register_sync_ws_commands` регистрирует все sync-операции в core registry.

Тест уровня unit, без БД и WS-сокета: вызываем регистратор и проверяем,
что для каждого канонического WS-имени из `SYNC_OPERATIONS` есть handler.
"""

from __future__ import annotations

import pytest

from apps.sync.realtime.command_router import SYNC_OPERATIONS, register_sync_ws_commands
from core.websocket import has_ws_command_handler, list_ws_command_types


@pytest.fixture(autouse=True)
def _ensure_no_partial_sync_registry():
    registered = set(list_ws_command_types())
    expected = set(SYNC_OPERATIONS)
    if registered.intersection(expected) and not expected.issubset(registered):
        missing = sorted(expected - registered)
        raise AssertionError(f"Частичная регистрация sync WS handlers: отсутствуют {missing}")
    yield


def _ensure_sync_handlers_registered() -> None:
    expected = set(SYNC_OPERATIONS)
    registered = set(list_ws_command_types())
    if expected.issubset(registered):
        return
    register_sync_ws_commands()


def test_register_sync_ws_commands_registers_all_canonical_names() -> None:
    _ensure_sync_handlers_registered()

    for canonical in SYNC_OPERATIONS:
        assert has_ws_command_handler(canonical), f"Нет handler для {canonical}"

    registered = set(list_ws_command_types())
    expected = set(SYNC_OPERATIONS.keys())
    assert expected.issubset(registered)


def test_register_sync_ws_commands_command_count_is_stable() -> None:
    _ensure_sync_handlers_registered()
    sync_handlers = [t for t in list_ws_command_types() if t.startswith("sync/")]
    assert len(sync_handlers) == len(SYNC_OPERATIONS)


def test_each_operation_canonical_type_matches_key() -> None:
    """SYNC_OPERATIONS ключ должен совпадать с Operation.canonical_type."""
    for canonical, op in SYNC_OPERATIONS.items():
        assert canonical == op.canonical_type
        assert canonical.endswith("_requested")
