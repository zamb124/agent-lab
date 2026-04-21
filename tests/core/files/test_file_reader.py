"""Тесты FileReader на реальных байтах/файлах."""

from __future__ import annotations

import base64

import fitz
import pytest
import unstructured  # noqa: F401

from core.files.checksum import compute_content_checksum_sha256
from core.files.reader import FileReader, FileReadError
from core.files.reader.models import FileReadKind


@pytest.mark.asyncio
async def test_read_bytes_text(tmp_path) -> None:
    raw = "строка utf-8".encode("utf-8")
    reader = FileReader()
    res = await reader.read(raw, file_name="x.txt")
    assert res.detected_kind == FileReadKind.TEXT
    assert res.page_count == 1
    assert len(res.pages) == 1
    assert res.pages[0].text == "строка utf-8"
    assert res.source_checksum == compute_content_checksum_sha256(raw)


@pytest.mark.asyncio
async def test_read_path_text_stable_checksum(tmp_path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("alpha\nbeta", encoding="utf-8")
    data = path.read_bytes()
    reader = FileReader()
    res = await reader.read(path)
    assert res.source_checksum == compute_content_checksum_sha256(data)
    assert res.page_count == len(res.pages)


@pytest.mark.asyncio
async def test_read_pdf_with_fitz(tmp_path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "MarkerPDF123")
    out = tmp_path / "t.pdf"
    doc.save(out)
    doc.close()

    reader = FileReader()
    res = await reader.read(out)
    assert res.detected_kind == FileReadKind.PDF
    assert res.page_count >= 1
    joined = "\n".join(p.text for p in res.pages)
    assert "MarkerPDF123" in joined


@pytest.mark.asyncio
async def test_read_bytes_requires_name() -> None:
    reader = FileReader()
    with pytest.raises(ValueError, match="file_name"):
        await reader.read(b"x")


@pytest.mark.asyncio
async def test_unknown_empty_raises() -> None:
    reader = FileReader()
    with pytest.raises(FileReadError):
        await reader.read(
            b"\x00\x01\x02\xff",
            file_name="blob.xyzunknownext123",
        )


@pytest.mark.asyncio
async def test_read_csv_as_text(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")
    reader = FileReader()
    res = await reader.read(path)
    assert res.detected_kind == FileReadKind.TEXT
    assert "a,b" in res.pages[0].text


@pytest.mark.asyncio
async def test_read_eml_via_unstructured_office_path() -> None:
    raw = (
        b"From: a@b.c\r\nTo: d@e.f\r\nSubject: X\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"LineOneUnstructured\r\nLineTwo\r\n"
    )
    reader = FileReader()
    res = await reader.read(raw, file_name="mail.eml")
    assert res.detected_kind == FileReadKind.OFFICE
    joined = "\n".join(p.text for p in res.pages)
    assert "LineOneUnstructured" in joined


def test_recognize_file_type_pdf_sniff_overrides_extension() -> None:
    reader = FileReader()
    pdf_head = b"%PDF-1.4\n%..."
    info = reader.recognize_file_type(file_name="wrong.txt", head=pdf_head)
    assert info.detected_kind == FileReadKind.PDF


@pytest.mark.asyncio
async def test_read_image_empty_vision_prompt_raises(tmp_path) -> None:
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    path = tmp_path / "x.png"
    path.write_bytes(png)
    reader = FileReader()
    with pytest.raises(ValueError, match="vision_prompt"):
        await reader.read(path, vision_prompt="")


@pytest.mark.asyncio
async def test_read_accepts_file_entry_dict(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    reader = FileReader()
    res = await reader.read({"name": "a.txt", "path": str(path)})
    assert "hello" in res.pages[0].text
