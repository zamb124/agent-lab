"""Негативные тесты FileReader: зашифрованные / пустые / нечитаемые файлы из корпуса.

Каждый вызов должен поднимать FileReadError — движок сообщает об ошибке явно,
не возвращает пустой результат.
"""

from __future__ import annotations

import pytest

from core.files.reader import FileReader, FileReadError
from tests.core.files.corpus.manifest import NEGATIVE, CorpusFile


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    NEGATIVE,
    ids=lambda e: e.relative_path,
)
@pytest.mark.timeout(60)
async def test_unsupported_file_raises_file_read_error(entry: CorpusFile) -> None:
    """Нечитаемые файлы должны поднимать FileReadError, не возвращать пустой результат."""
    if not entry.path.exists():
        pytest.skip(f"Файл отсутствует в корпусе: {entry.relative_path}")

    raw = entry.path.read_bytes()
    reader = FileReader()

    with pytest.raises(FileReadError):
        await reader.read(raw, file_name=entry.path.name)
