"""Wiki test constants и OpenFGA fixture.

Fixtures live in `tests.fixtures.wiki` (root `pytest_plugins`).

OpenFGA обязателен для Wiki PDP (нет SQL fallback).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from core.config.models import OpenFGAConfig
from tests.fixtures.wiki import API_PREFIX, NAMESPACE_HEADER, PAGES_URL

__all__ = ["API_PREFIX", "NAMESPACE_HEADER", "PAGES_URL"]


@pytest.fixture(autouse=True)
def _wiki_requires_openfga(openfga_settings: OpenFGAConfig) -> Iterator[None]:
    from apps.wiki.container import reset_wiki_container

    reset_wiki_container()
    _ = openfga_settings
    try:
        yield
    finally:
        reset_wiki_container()
