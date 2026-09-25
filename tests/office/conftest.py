"""
Office-специфичные фикстуры.

OpenFGA обязателен для Office PDP (нет SQL fallback).
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI

from apps.office.di import OfficeDi
from core.config.models import OpenFGAConfig
from core.di import require_di


@pytest.fixture(autouse=True)
def _office_requires_openfga(openfga_settings: OpenFGAConfig) -> Iterator[None]:
    _ = openfga_settings
    yield


@pytest_asyncio.fixture
async def office_di(office_app: FastAPI) -> AsyncIterator[OfficeDi]:
    """Тот же ``OfficeDi``, что собирает lifespan ``office_app``."""
    yield require_di(office_app, OfficeDi)
