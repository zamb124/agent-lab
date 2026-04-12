"""Тесты чтения устаревших форматов .xls и .doc через FileReader."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from core.files.reader import FileReader, FileReadError
from core.files.reader.models import FileReadKind


def _make_xls_bytes(sheet_name: str, rows: list[list[str]]) -> bytes:
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet(sheet_name)
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            ws.write(row_idx, col_idx, value)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_docx_bytes(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────── XLS ────────────────────────────


@pytest.mark.asyncio
async def test_read_xls_single_sheet(tmp_path: Path) -> None:
    rows = [
        ["Товар", "Количество", "Цена"],
        ["Яблоки", "100", "50.5"],
        ["Груши", "200", "75.0"],
    ]
    raw = _make_xls_bytes("Склад", rows)

    reader = FileReader()
    result = await reader.read(raw, file_name="report.xls")

    assert result.detected_kind == FileReadKind.SPREADSHEET
    assert result.page_count == 1
    assert result.pages[0].label == "Склад"

    text = result.pages[0].text
    assert "Товар" in text
    assert "Яблоки" in text
    assert "Груши" in text
    assert "100" in text


@pytest.mark.asyncio
async def test_read_xls_multiple_sheets(tmp_path: Path) -> None:
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook(encoding="utf-8")

    ws1 = wb.add_sheet("Январь")
    ws1.write(0, 0, "Строка-Январь-Маркер")

    ws2 = wb.add_sheet("Февраль")
    ws2.write(0, 0, "Строка-Февраль-Маркер")

    buf = BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    reader = FileReader()
    result = await reader.read(raw, file_name="months.xls")

    assert result.detected_kind == FileReadKind.SPREADSHEET
    assert result.page_count == 2

    labels = [p.label for p in result.pages]
    assert "Январь" in labels
    assert "Февраль" in labels

    all_text = "\n".join(p.text for p in result.pages)
    assert "Строка-Январь-Маркер" in all_text
    assert "Строка-Февраль-Маркер" in all_text


@pytest.mark.asyncio
async def test_read_xls_numeric_values(tmp_path: Path) -> None:
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Data")
    ws.write(0, 0, 42)
    ws.write(0, 1, 3.14)
    ws.write(1, 0, "текст")
    buf = BytesIO()
    wb.save(buf)

    reader = FileReader()
    result = await reader.read(buf.getvalue(), file_name="nums.xls")

    assert result.detected_kind == FileReadKind.SPREADSHEET
    text = result.pages[0].text
    assert "42" in text
    assert "текст" in text


@pytest.mark.asyncio
async def test_read_xls_empty_raises() -> None:
    """Пустой XLS без данных поднимает FileReadError."""
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    wb.add_sheet("Empty")
    buf = BytesIO()
    wb.save(buf)

    reader = FileReader()
    with pytest.raises(FileReadError):
        await reader.read(buf.getvalue(), file_name="empty.xls")


# ─────────────────────────────────────────── DOC ────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("libreoffice") is None,
    reason="LibreOffice не установлен — пропускаем тест чтения .doc",
)
async def test_read_doc_via_libreoffice(tmp_path: Path) -> None:
    marker = "DocMarkerTextXYZ123"
    docx_bytes = _make_docx_bytes(marker)

    docx_path = tmp_path / "source.docx"
    docx_path.write_bytes(docx_bytes)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "doc", "--outdir", str(tmp_path), str(docx_path)],
        capture_output=True,
        check=True,
        timeout=60,
    )

    doc_path = tmp_path / "source.doc"
    assert doc_path.exists(), "soffice не создал .doc файл"

    reader = FileReader()
    result = await reader.read(doc_path)

    assert result.detected_kind == FileReadKind.OFFICE
    assert result.page_count >= 1
    all_text = "\n".join(p.text for p in result.pages)
    assert marker in all_text


@pytest.mark.asyncio
async def test_read_doc_without_libreoffice_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Если soffice не найден — FileReadError с понятным сообщением."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    docx_bytes = _make_docx_bytes("какой-то текст")
    docx_path = tmp_path / "source.docx"
    docx_path.write_bytes(docx_bytes)

    # Создадим .doc файл как копию .docx — содержимое не важно,
    # ошибка должна возникнуть до парсинга (при поиске soffice)
    doc_path = tmp_path / "source.doc"
    doc_path.write_bytes(docx_bytes)

    reader = FileReader()
    with pytest.raises(FileReadError, match="LibreOffice"):
        await reader.read(doc_path)
