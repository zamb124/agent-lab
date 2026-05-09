"""Гарантия: каждое расширение в FILE_TYPE_REGISTRY распознаётся в правильный FileReadKind.

Тест не читает файл целиком — только recognize_file_type(file_name=...).
Это статический инвариант: добавил расширение в реестр → обязан появиться
соответствующий маппинг в _kind_from_extension или через MIME-fallback.
"""

from __future__ import annotations

import pytest

from core.files.reader import FileReader
from core.files.reader.models import FileReadKind
from core.files.types import FILE_TYPE_REGISTRY, FileCategory, FileTypeEntry

# Маппинг категории → ожидаемый FileReadKind
_CATEGORY_TO_KIND: dict[FileCategory, FileReadKind] = {
    FileCategory.TEXT: FileReadKind.TEXT,
    FileCategory.PDF: FileReadKind.PDF,
    FileCategory.OFFICE_DOC: FileReadKind.OFFICE,
    FileCategory.SPREADSHEET: FileReadKind.SPREADSHEET,
    FileCategory.PRESENTATION: FileReadKind.OFFICE,  # Unstructured обрабатывает как OFFICE
    FileCategory.IMAGE: FileReadKind.IMAGE,
    FileCategory.AUDIO: FileReadKind.AUDIO,
    FileCategory.VIDEO: FileReadKind.VIDEO,
    # ARCHIVE и EMAIL: в _kind_from_extension нет прямой ветки → UNKNOWN,
    # но OFFICE ветка Unstructured переопределит при фактическом чтении.
    # recognize_file_type по одному имени файла без head вернёт UNKNOWN для ARCHIVE.
    FileCategory.ARCHIVE: FileReadKind.UNKNOWN,
    FileCategory.EMAIL: FileReadKind.OFFICE,
    FileCategory.EBOOK: FileReadKind.OFFICE,
}

# HTML/HTM — категория TEXT в реестре, но reader читает как HTML
_HTML_EXTENSIONS = frozenset({".html", ".htm"})


@pytest.mark.parametrize(
    "entry",
    list(FILE_TYPE_REGISTRY),
    ids=lambda e: e.extension,
)
def test_every_registry_extension_recognizes_to_correct_kind(entry: FileTypeEntry) -> None:
    """recognize_file_type(file_name=...) → ожидаемый FileReadKind."""
    reader = FileReader()
    info = reader.recognize_file_type(file_name=f"sample{entry.extension}")

    if entry.extension in _HTML_EXTENSIONS:
        expected_kind = FileReadKind.HTML
    else:
        expected_kind = _CATEGORY_TO_KIND[entry.category]

    assert info.detected_kind == expected_kind, (
        f"Расширение {entry.extension!r} (категория {entry.category!r}): "
        f"recognize_file_type вернул {info.detected_kind!r}, "
        f"ожидали {expected_kind!r}"
    )
