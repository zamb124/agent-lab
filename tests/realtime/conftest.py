"""Realtime E2E: живой Centrifugo :19000 + Granian bus :9025, без ASGI-патча."""

from __future__ import annotations

import pytest

from apps.realtime.services.bus_service import RealtimeBusService


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    no_doubles = pytest.mark.no_test_doubles
    no_asgi = pytest.mark.no_service_client_patch
    timeout_20 = pytest.mark.timeout(20)
    for item in items:
        if not item.nodeid.startswith("tests/realtime/"):
            continue
        item.add_marker(no_doubles)
        item.add_marker(no_asgi)
        if item.get_closest_marker("timeout") is None:
            item.add_marker(timeout_20)


@pytest.fixture
def realtime_event_log(realtime_service: None) -> RealtimeBusService:
    """Строки лога пишет pytest в ту же БД, которую читает sweeper процесса granian."""
    _ = realtime_service
    return RealtimeBusService()
