"""Локальные фикстуры для tests/core/files/.

Очистка каталога артефактов FileWriter и TextTransformService для vision/summarize.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from core.files.reader.service import FileReader
from core.text_transforms import TextTransformService
from tests.core.files.file_writer_artifacts import OUTPUT_DIR


def pytest_sessionstart(session: pytest.Session) -> None:
    if OUTPUT_DIR.is_dir():
        shutil.rmtree(OUTPUT_DIR)


@pytest_asyncio.fixture(scope="session")
async def file_reader_billing_service(setup_database_before_tests, di) -> AsyncIterator[None]:
    """Конфигурирует FileReader.configure_text_transform для vision/summarize тестов.

    Применяется явно через @pytest.mark.usefixtures("file_reader_billing_service").
    """
    _ = setup_database_before_tests
    FileReader.configure_text_transform(TextTransformService(di.billing_service))
    yield
