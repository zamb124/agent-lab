"""Матрица кодировок для _read_plain_text_sync.

Проверяет что BOM-детекция и charset_normalizer fallback корректно работают
для UTF-8, UTF-8 BOM, UTF-16 BE/LE/BOM, UTF-32 BE/LE.
Дополнительно тестируются реальные файлы корпуса с UTF-16.
"""

from __future__ import annotations

import pytest

from core.files.reader import FileReader, FileReadError
from core.files.reader.models import FileReadKind
from tests.core.files.corpus.manifest import CORPUS_DIR

_MARKER = "Маркер-Кодировка-XYZ"

# (pytest_id, encoding, bom_prefix)
_ENCODING_CASES: list[tuple[str, str, bytes]] = [
    ("utf-8", "utf-8", b""),
    ("utf-8-bom", "utf-8-sig", b""),          # кодек сам вставит BOM
    ("utf-16-le-bom", "utf-16-le", b"\xff\xfe"),
    ("utf-16-be-bom", "utf-16-be", b"\xfe\xff"),
    ("utf-16-bom", "utf-16", b""),             # кодек utf-16 сам вставит BOM
    ("utf-32-le-bom", "utf-32-le", b"\xff\xfe\x00\x00"),
    ("utf-32-be-bom", "utf-32-be", b"\x00\x00\xfe\xff"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id, codec, extra_bom",
    _ENCODING_CASES,
    ids=[c[0] for c in _ENCODING_CASES],
)
async def test_text_decoded_correctly_for_encoding(
    case_id: str,
    codec: str,
    extra_bom: bytes,
) -> None:
    """Маркерная строка должна точно присутствовать в pages[0].text после декодирования.

    extra_bom: байты BOM, которые нужно явно предварить контенту.
    Кодеки utf-16-le/be и utf-32-le/be НЕ добавляют BOM автоматически,
    поэтому extra_bom должен содержать нужный BOM-префикс.
    Кодеки utf-16, utf-8-sig и utf-32 добавляют BOM сами.
    """
    raw = extra_bom + _MARKER.encode(codec)
    reader = FileReader()
    result = await reader.read(raw, file_name="test_encoding.txt")
    assert result.detected_kind == FileReadKind.TEXT
    assert result.page_count == 1
    assert _MARKER in result.pages[0].text, (
        f"Кодировка {codec!r}: маркер не найден. "
        f"Первые байты: {raw[:10].hex()!r}. "
        f"Получено: {result.pages[0].text[:100]!r}"
    )


# ---------------------------------------------------------------------------
# Реальные файлы корпуса с UTF-16
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_corpus_utf16_txt_readable() -> None:
    """fake-text-utf-16.txt (UTF-16 LE BOM) читается правильно."""
    path = CORPUS_DIR / "fake-text-utf-16.txt"
    if not path.exists():
        pytest.skip("Файл отсутствует в корпусе")
    reader = FileReader()
    result = await reader.read(path)
    assert result.detected_kind == FileReadKind.TEXT
    assert "test document" in result.pages[0].text


@pytest.mark.asyncio
async def test_real_corpus_utf16_be_txt_no_bom_does_not_crash() -> None:
    """fake-text-utf-16-be.txt хранится БЕЗ BOM в unstructured/example-docs.

    charset_normalizer не детектирует bare UTF-16 BE надёжно — возвращает latin-1.
    Важно: reader.read() НЕ должен падать; detected_kind=TEXT.
    Содержимое может быть garbled (это documented limitation).
    """
    path = CORPUS_DIR / "fake-text-utf-16-be.txt"
    if not path.exists():
        pytest.skip("Файл отсутствует в корпусе")
    reader = FileReader()
    result = await reader.read(path)
    assert result.detected_kind == FileReadKind.TEXT
    assert result.page_count == 1


@pytest.mark.asyncio
async def test_real_corpus_utf16_le_txt_no_bom_does_not_crash() -> None:
    """fake-text-utf-16-le.txt хранится БЕЗ BOM в unstructured/example-docs.

    charset_normalizer не детектирует bare UTF-16 LE надёжно — возвращает latin-1.
    Важно: reader.read() НЕ должен падать; detected_kind=TEXT.
    Содержимое может быть garbled (это documented limitation).
    """
    path = CORPUS_DIR / "fake-text-utf-16-le.txt"
    if not path.exists():
        pytest.skip("Файл отсутствует в корпусе")
    reader = FileReader()
    result = await reader.read(path)
    assert result.detected_kind == FileReadKind.TEXT
    assert result.page_count == 1


@pytest.mark.asyncio
async def test_real_corpus_utf32_txt_readable() -> None:
    """fake-text-utf-32.txt (UTF-32 BOM) читается правильно."""
    path = CORPUS_DIR / "fake-text-utf-32.txt"
    if not path.exists():
        pytest.skip("Файл отсутствует в корпусе")
    reader = FileReader()
    result = await reader.read(path)
    assert result.detected_kind == FileReadKind.TEXT
    assert "test document" in result.pages[0].text


@pytest.mark.asyncio
async def test_real_corpus_utf16_csv_readable() -> None:
    """stanley-cups-utf-16.csv (UTF-16 BE BOM) декодируется, текст содержит 'Stanley'."""
    path = CORPUS_DIR / "stanley-cups-utf-16.csv"
    if not path.exists():
        pytest.skip("Файл отсутствует в корпусе")
    reader = FileReader()
    result = await reader.read(path)
    assert result.detected_kind == FileReadKind.TEXT
    assert "Stanley" in result.pages[0].text
