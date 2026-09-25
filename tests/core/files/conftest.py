"""Локальные фикстуры для tests/core/files/.

Очистка каталога артефактов FileWriter и инициализация BillingService для vision-тестов.
"""

from __future__ import annotations

import shutil

import pytest

from tests.core.files.file_writer_artifacts import OUTPUT_DIR


def pytest_sessionstart(session: pytest.Session) -> None:
    if OUTPUT_DIR.is_dir():
        shutil.rmtree(OUTPUT_DIR)


@pytest.fixture(scope="session")
async def file_reader_billing_service(setup_database_before_tests, di):
    """Регистрирует глобальный BillingService из FlowsDi.

    Нужен FileReader._read_image_impl для проверки баланса.
    Применяется явно через @pytest.mark.usefixtures("file_reader_billing_service")
    в тестах, которым нужен vision (один раз на session).
    """
    _ = setup_database_before_tests
    from core.billing import set_billing_service

    set_billing_service(di.billing_service)
    yield
