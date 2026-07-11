"""Worktracker integration: cross-service HTTP/WS/hooks без моков."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.nodeid.startswith("tests/worktracker/integration/"):
            if item.get_closest_marker("integration") is None:
                item.add_marker(pytest.mark.integration)
