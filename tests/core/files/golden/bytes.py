"""Golden-байты для контрактных E2E FileReader: маркеры unique_id внутри файла."""

from __future__ import annotations

import tempfile
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path

import pymupdf
import xlwt
from docx import Document
from docx.shared import Inches
from ebooklib import epub
from odf.opendocument import OpenDocumentText
from odf.text import P
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Emu

from core.data_tables.models import DataTableColumnSpec
from core.data_tables.sqlite_format import (
    create_user_table,
    initialize_platform_schema,
    insert_rows,
    open_sqlite,
)
from core.types import JsonObject
from tests.core.files.corpus.manifest import CORPUS_DIR

_MSG_BODY_NEEDLE = b"This is a test email to use for unit tests."
_WAV_RELATIVE_PATH = "CantinaBand3.wav"


def marker(prefix: str, unique_id: str) -> str:
    return f"{prefix}_{unique_id}"


def png_with_text(text: str, *, width: int = 640, height: int = 240) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, height // 2 - 10), text, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png_printed_marker(unique_id: str) -> bytes:
    return png_with_text(marker("GOLDEN_PNG", unique_id))


def jpg_with_text(text: str) -> bytes:
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 110), text, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def jpg_printed_marker(unique_id: str) -> bytes:
    return jpg_with_text(marker("GOLDEN_JPG", unique_id))


def txt_bytes(unique_id: str) -> bytes:
    return f"{marker('GOLDEN_TXT', unique_id)}\nplain paragraph\n".encode("utf-8")


def csv_bytes(unique_id: str) -> bytes:
    token = marker("GOLDEN_CSV", unique_id)
    return f"name,value\nmarker,{token}\n".encode("utf-8")


def html_bytes(unique_id: str) -> bytes:
    token = marker("GOLDEN_HTML", unique_id)
    return (
        "<html><body><p>Golden html paragraph "
        + token
        + "</p></body></html>"
    ).encode("utf-8")


def docx_heading_table_list_png(unique_id: str) -> bytes:
    token = marker("GOLDEN_DOCX", unique_id)
    document = Document()
    document.add_heading(f"Heading {token}", level=0)
    document.add_paragraph(f"Paragraph {token}")
    document.add_paragraph(f"List {token}", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "col_a"
    table.rows[0].cells[1].text = "col_b"
    table.rows[1].cells[0].text = token
    table.rows[1].cells[1].text = "row"
    document.add_picture(BytesIO(png_with_text(token)), width=Inches(1.5))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def pptx_two_slides_table_png(unique_id: str) -> bytes:
    token = marker("GOLDEN_PPTX", unique_id)
    presentation = Presentation()
    blank = presentation.slide_layouts[6]
    first = presentation.slides.add_slide(blank)
    box = first.shapes.add_textbox(Emu(457200), Emu(457200), Emu(5486400), Emu(914400))
    box.text_frame.text = f"Slide one {token} extra readable text for the page"
    table_shape = first.shapes.add_table(
        2, 2, Emu(457200), Emu(1828800), Emu(4572000), Emu(914400)
    )
    table = table_shape.table
    table.cell(0, 0).text = "h1"
    table.cell(0, 1).text = "h2"
    table.cell(1, 0).text = token
    table.cell(1, 1).text = "v"
    second = presentation.slides.add_slide(blank)
    second_box = second.shapes.add_textbox(
        Emu(457200), Emu(457200), Emu(5486400), Emu(914400)
    )
    second_box.text_frame.text = f"Slide two {token} extra readable text for the page"
    png = png_with_text(token)
    second.shapes.add_picture(BytesIO(png), Emu(457200), Emu(1828800), width=Emu(1828800))
    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def xlsx_two_sheets(unique_id: str) -> bytes:
    token = marker("GOLDEN_XLSX", unique_id)
    workbook = Workbook()
    first = workbook.active
    if first is None:
        raise ValueError("openpyxl workbook.active пуст")
    first.title = "alpha"
    first["A1"] = token
    first["B1"] = "sheet-alpha"
    second = workbook.create_sheet("beta")
    second["A1"] = token
    second["B1"] = "sheet-beta"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def xls_table(unique_id: str) -> bytes:
    token = marker("GOLDEN_XLS", unique_id)
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    sheet.write(0, 0, token)
    sheet.write(0, 1, "xls-row")
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def epub_two_chapters(unique_id: str) -> bytes:
    token = marker("GOLDEN_EPUB", unique_id)
    book = epub.EpubBook()
    book.set_identifier(f"golden-{unique_id}")
    book.set_title(f"Golden {token}")
    book.set_language("en")
    chapter_one = epub.EpubHtml(title="One", file_name="one.xhtml", lang="en")
    chapter_one.content = f"<h1>Chapter one</h1><p>{token} one</p>"
    chapter_two = epub.EpubHtml(title="Two", file_name="two.xhtml", lang="en")
    chapter_two.content = f"<h1>Chapter two</h1><p>{token} two</p>"
    book.add_item(chapter_one)
    book.add_item(chapter_two)
    book.toc = (chapter_one, chapter_two)
    book.spine = ["nav", chapter_one, chapter_two]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "golden.epub"
        epub.write_epub(str(path), book)
        return path.read_bytes()


def eml_message(unique_id: str) -> bytes:
    token = marker("GOLDEN_EML", unique_id)
    message = EmailMessage()
    message["Subject"] = f"Subject {token}"
    message["From"] = "golden@example.com"
    message["To"] = "reader@example.com"
    message.set_content(f"Body {token}")
    return message.as_bytes()


def msg_with_marker(unique_id: str) -> bytes:
    token = marker("GOLDEN_MSG", unique_id).encode("ascii")
    if len(token) > len(_MSG_BODY_NEEDLE):
        raise ValueError("unique_id слишком длинный для MSG needle")
    padded = token + b" " * (len(_MSG_BODY_NEEDLE) - len(token))
    source = (CORPUS_DIR / "fake-email.msg").read_bytes()
    if _MSG_BODY_NEEDLE not in source:
        raise ValueError("в fake-email.msg нет ASCII needle для маркера")
    needle_utf16le = _MSG_BODY_NEEDLE.decode("ascii").encode("utf-16le")
    needle_utf16be = _MSG_BODY_NEEDLE.decode("ascii").encode("utf-16be")
    padded_le = padded.decode("ascii").encode("utf-16le")
    padded_be = padded.decode("ascii").encode("utf-16be")
    if needle_utf16le not in source:
        raise ValueError("в fake-email.msg нет UTF-16LE needle для маркера")
    replaced = (
        source.replace(_MSG_BODY_NEEDLE, padded)
        .replace(needle_utf16le, padded_le)
        .replace(needle_utf16be, padded_be)
    )
    return replaced


def rtf_bytes(unique_id: str) -> bytes:
    token = marker("GOLDEN_RTF", unique_id)
    return (
        r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Times New Roman;}}\f0\fs24 "
        + token
        + r"\par}"
    ).encode("ascii")


def odt_bytes(unique_id: str) -> bytes:
    token = marker("GOLDEN_ODT", unique_id)
    document = OpenDocumentText()
    document.text.addElement(P(text=token))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "golden.odt"
        document.save(str(path))
        return path.read_bytes()


def sqlite_schema(unique_id: str) -> bytes:
    table_name = f"golden_{unique_id}"
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
        path = Path(tmp.name)
        connection = open_sqlite(path)
        try:
            initialize_platform_schema(
                connection,
                scope="office_document",
                flow_id=None,
                session_id=None,
            )
            create_user_table(
                connection,
                table_name=table_name,
                columns=[DataTableColumnSpec(name="marker", column_type="text")],
            )
            row: JsonObject = {"marker": marker("GOLDEN_SQLITE", unique_id)}
            insert_rows(
                connection,
                table_name=table_name,
                rows=[row],
            )
        finally:
            connection.close()
        return path.read_bytes()


def pdf_long_text_with_image(unique_id: str) -> bytes:
    token = marker("GOLDEN_PDF_TEXT", unique_id)
    body = ("Readable PDF paragraph " + token + ". ") * 8
    document = pymupdf.open()
    page = document.new_page()
    _ = page.insert_text((72, 72), body, fontsize=11)
    png = png_with_text(token)
    _ = page.insert_image(pymupdf.Rect(72, 420, 220, 520), stream=png)
    out = document.tobytes()
    document.close()
    return out


def pdf_printed_page(text: str, *, width: int = 640, height: int = 480) -> bytes:
    png = png_with_text(text, width=width, height=height)
    document = pymupdf.open()
    page = document.new_page()
    _ = page.insert_image(page.rect, stream=png)
    out = document.tobytes()
    document.close()
    return out


def pdf_scanned_raster(unique_id: str) -> bytes:
    return pdf_printed_page(marker("GOLDEN_PDF_SCAN", unique_id))


def pdf_short_text_with_image(unique_id: str) -> bytes:
    token = marker("GOLDEN_PDF_SHORT", unique_id)
    document = pymupdf.open()
    page = document.new_page()
    _ = page.insert_text((72, 72), f"Hi {token}", fontsize=11)
    png = png_with_text(token)
    _ = page.insert_image(pymupdf.Rect(72, 140, 220, 240), stream=png)
    out = document.tobytes()
    document.close()
    return out


def wav_corpus_bytes(unique_id: str) -> bytes:
    del unique_id
    path = CORPUS_DIR / _WAV_RELATIVE_PATH
    if not path.exists():
        raise FileNotFoundError(f"нет корпуса wav: {_WAV_RELATIVE_PATH}")
    return path.read_bytes()
