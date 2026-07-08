"""Негативные тесты FileReader: зашифрованные / пустые / нечитаемые файлы из корпуса.

Каждый вызов FileReader.read() должен поднимать FileReadError — движок сообщает об ошибке явно,
не возвращает пустой результат.
"""

from __future__ import annotations

import pytest

from core.files.reader import FileReader, FileReadError
from core.files.reader.models import ReadFileArgs
from tests.core.files.corpus.manifest import NEGATIVE, CorpusFile


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    NEGATIVE,
    ids=lambda entry: entry.relative_path,
)
@pytest.mark.timeout(60)
async def test_unsupported_file_raises_file_read_error(entry: CorpusFile) -> None:
    """Нечитаемые файлы должны поднимать FileReadError через канонический read()."""
    if not entry.path.exists():
        pytest.skip(f"Файл отсутствует в корпусе: {entry.relative_path}")

    raw = entry.path.read_bytes()
    reader = FileReader()
    read_args = ReadFileArgs(page_end=-1, vision_prompt="")

    with pytest.raises(FileReadError):
        await reader.read(raw, read_args, file_name=entry.path.name)
