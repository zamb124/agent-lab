"""Тесты FileWriter: классификация, markdown, таблицы, вставка картинок по URL.

Артефакты: см. tests/core/files/file_writer_output/ (каталог очищается в начале сессии).
"""

from __future__ import annotations

import base64
import zipfile
from io import BytesIO
from unittest.mock import patch

import pytest

from core.files.writer import FileWriteError, FileWriter, classify_content
from core.files.writer.models import ContentKind
from tests.core.files.file_writer_artifacts import overwrite_artifact

MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_classify_markdown_header() -> None:
    assert classify_content("# Title\n\nbody") == ContentKind.MARKDOWN


def test_classify_image_only_markdown() -> None:
    assert classify_content("![](https://example.com/a.png)") == ContentKind.MARKDOWN


def test_build_markdown_md_file() -> None:
    w = FileWriter()
    r = w.build_bytes("# x", "note.md", content_mode="markdown")
    overwrite_artifact("unit_note.md", r.data)
    assert r.conversion_applied is True
    assert b"# x" in r.data


def test_build_raw_bytes() -> None:
    w = FileWriter()
    r = w.build_bytes(b"\xff\xfe", "f.bin", content_mode="raw")
    overwrite_artifact("unit_raw.bin", r.data)
    assert r.conversion_applied is False
    assert r.data == b"\xff\xfe"


def test_unsupported_markdown_target() -> None:
    w = FileWriter()
    with pytest.raises(FileWriteError, match="не поддерживается"):
        w.build_bytes("# x", "z.png", content_mode="markdown")


def test_docx_with_patched_image_fetch() -> None:
    w = FileWriter()

    def fake_fetch(url: str, *, max_bytes: int, timeout_seconds: float):
        assert url.startswith("https://")
        return MIN_PNG, "image/png"

    md = "Hello\n\n![](https://example.com/x.png)\n\nBye"
    with patch("core.files.writer.service.fetch_url_bytes", side_effect=fake_fetch):
        r = w.build_bytes(md, "out.docx", content_mode="markdown")
    overwrite_artifact("unit_patched_image.docx", r.data)
    assert r.content_type.startswith("application/vnd.openxmlformats")
    zf = zipfile.ZipFile(BytesIO(r.data))
    names = zf.namelist()
    assert "word/document.xml" in names
    xml = zf.read("word/document.xml").decode("utf-8")
    assert "Hello" in xml and "Bye" in xml


def test_xlsx_table_and_image() -> None:
    w = FileWriter()

    def fake_fetch(url: str, *, max_bytes: int, timeout_seconds: float):
        return MIN_PNG, "image/png"

    md = (
        "Intro line\n\n"
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n\n"
        "![](https://cdn.example.com/i.png)"
    )
    with patch("core.files.writer.service.fetch_url_bytes", side_effect=fake_fetch):
        r = w.build_bytes(md, "sheet.xlsx", content_mode="markdown")
    overwrite_artifact("unit_table_image.xlsx", r.data)
    assert "spreadsheetml" in r.content_type
    zf = zipfile.ZipFile(BytesIO(r.data))
    assert any(n.startswith("xl/media/") for n in zf.namelist())


def test_html_embeds_http_images() -> None:
    w = FileWriter()

    def fake_fetch(url: str, *, max_bytes: int, timeout_seconds: float):
        return MIN_PNG, "image/png"

    md = "![](https://img.example/z.png)"
    with patch("core.files.writer.service.fetch_url_bytes", side_effect=fake_fetch):
        r = w.build_bytes(md, "p.html", content_mode="markdown")
    overwrite_artifact("unit_http_images.html", r.data)
    html = r.data.decode("utf-8")
    assert "data:image/png;base64," in html


def test_pdf_builds() -> None:
    w = FileWriter()
    r = w.build_bytes("# H\n\npara", "a.pdf", content_mode="markdown")
    overwrite_artifact("unit_simple.pdf", r.data)
    assert r.data[:5] == b"%PDF-"
