"""Локальные фикстуры для tests/core/files/.

Очистка каталога артефактов FileWriter и инициализация BillingService для vision-тестов.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.core.files.file_writer_artifacts import OUTPUT_DIR


def pytest_sessionstart(session: pytest.Session) -> None:
    if OUTPUT_DIR.is_dir():
        shutil.rmtree(OUTPUT_DIR)


@pytest.fixture(scope="session")
def file_reader_billing_service(setup_database_before_tests):
    """Регистрирует глобальный BillingService через flows container.

    Нужен FileReader._read_image_impl для проверки баланса.
    Применяется явно через @pytest.mark.usefixtures("file_reader_billing_service")
    в тестах, которым нужен vision (один раз на session).
    """
    from apps.flows.src.container import get_container as get_flows_container
    from core.billing import set_billing_service

    container = get_flows_container()
    set_billing_service(container.billing_service)
    yield
