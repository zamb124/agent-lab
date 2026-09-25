"""CRM-специфичные фикстуры.

DI: `crm_di` (корневой conftest) — `CrmDi` приложения crm; `crm_worker_di` — DI процесса crm_worker.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio

from apps.crm_worker.di import CrmWorkerDi
from core.config.models import OpenFGAConfig
from tests.fixtures.service_processes import ServiceProcesses


@pytest.fixture(autouse=True)
def _crm_requires_openfga(openfga_settings: OpenFGAConfig) -> Iterator[None]:
    """CRM CrmEntityAccessService — только OpenFGA; без test store тесты не гоняются."""
    _ = openfga_settings
    yield




@pytest_asyncio.fixture
async def crm_worker_di(service_processes: ServiceProcesses) -> CrmWorkerDi:
    """DI процесса crm_worker: анализ заметок, импорт знаний, интеграции."""
    return await service_processes.di(CrmWorkerDi)
