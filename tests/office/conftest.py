"""
Office-специфичные фикстуры.

OpenFGA обязателен для Office PDP (нет SQL fallback).
"""

from collections.abc import Iterator

import pytest

from core.config.models import OpenFGAConfig


@pytest.fixture(autouse=True)
def _office_requires_openfga(openfga_settings: OpenFGAConfig) -> Iterator[None]:
    from apps.office.container import reset_office_container

    reset_office_container()
    _ = openfga_settings
    try:
        yield
    finally:
        reset_office_container()
