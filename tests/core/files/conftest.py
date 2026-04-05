"""Очистка каталога артефактов FileWriter в начале сессии (только для тестов под этой папкой)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.core.files.file_writer_artifacts import OUTPUT_DIR


def pytest_sessionstart(session: pytest.Session) -> None:
    if OUTPUT_DIR.is_dir():
        shutil.rmtree(OUTPUT_DIR)
