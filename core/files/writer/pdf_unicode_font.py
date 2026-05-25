"""TTF для ReportLab PDF: кириллица и прочий Unicode (Noto Sans, SIL OFL)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from core.files.writer.exceptions import FileWriteError

_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "NotoSans-Regular.ttf"
_REGISTERED_NAME = "NotoSansWriter"


@lru_cache(maxsize=1)
def register_pdf_unicode_font() -> str:
    if not _FONT_PATH.is_file():
        raise FileWriteError(f"PDF: не найден файл шрифта {_FONT_PATH}")
    font = TTFont(_REGISTERED_NAME, str(_FONT_PATH))
    pdfmetrics.registerFont(font)
    return _REGISTERED_NAME
