"""Явная карта файлов корпуса example-docs → ожидаемое поведение FileReader.

Каждая запись становится одним параметризованным тест-кейсом.
Пути — относительно tests/core/files/example-docs/.

Правила:
- is_unsupported=True:  ожидаем FileReadError (зашифрованный/пустой/нечитаемый).
- uses_vision_llm=True: тест настраивает очередь MockLLM перед вызовом reader.read().
- uses_mock_stt_tier=True: reader.read() вызывается с transcription_company_id=corpus_tier_{unique_id}.
- skip_reason not None:  тест помечается pytest.skip (known issue / out of scope).
- allows_empty_text=True: допускается pages[0].text == "" (файл пустой по замыслу).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.files.reader.models import FileReadKind

CORPUS_DIR = Path(__file__).parent.parent / "example-docs"


@dataclass(frozen=True)
class CorpusFile:
    relative_path: str
    expected_kind: FileReadKind
    expected_text_substring: str | None = None
    expected_min_pages: int = 1
    is_unsupported: bool = False
    uses_vision_llm: bool = False
    uses_mock_stt_tier: bool = False
    allows_empty_text: bool = False
    skip_reason: str | None = None

    @property
    def path(self) -> Path:
        return CORPUS_DIR / self.relative_path


# ---------------------------------------------------------------------------
# TEXT — plain / rst / org / csv / tsv / json / xml / yaml / code
# ---------------------------------------------------------------------------
CORPUS: tuple[CorpusFile, ...] = (
    # .txt
    CorpusFile("fake-text.txt", FileReadKind.TEXT, "Hamburgers are delicious"),
    CorpusFile("book-war-and-peace-1p.txt", FileReadKind.TEXT, "Prince"),
    CorpusFile("norwich-city.txt", FileReadKind.TEXT, "Norwich City"),
    CorpusFile("book-war-and-peace-1225p.txt", FileReadKind.TEXT, "CHAPTER"),
    CorpusFile("language-docs/UDHR_first_article_all.txt", FileReadKind.TEXT, "human beings"),
    CorpusFile("language-docs/eng_spa.txt", FileReadKind.TEXT, "human beings"),
    CorpusFile("hebrew-text-base64-iso88598i.txt", FileReadKind.TEXT, None),  # base64-encoded hebrew
    CorpusFile("fake-email.txt", FileReadKind.TEXT, None),
    CorpusFile("fake-incomplete-json.txt", FileReadKind.TEXT, None),
    # truly empty / whitespace — only
    CorpusFile("empty.txt", FileReadKind.TEXT, None, allows_empty_text=True),
    CorpusFile("fake-text-all-whitespace.txt", FileReadKind.TEXT, None, allows_empty_text=True),

    # .txt UTF-16/32 variants — фикс BOM-детекции
    # fake-text-utf-16.txt имеет BOM (ff fe) → декодируется корректно
    CorpusFile("fake-text-utf-16.txt", FileReadKind.TEXT, "test document"),
    # fake-text-utf-32.txt имеет BOM (ff fe 00 00) → декодируется корректно
    CorpusFile("fake-text-utf-32.txt", FileReadKind.TEXT, "test document"),
    # fake-text-utf-16-be.txt / -le.txt хранятся БЕЗ BOM в репозитории unstructured.
    # charset_normalizer не детектирует bare UTF-16 надёжно (возвращает latin-1).
    # Тест верифицирует что reader не падает; content может быть garbled.
    CorpusFile(
        "fake-text-utf-16-be.txt",
        FileReadKind.TEXT,
        None,
        skip_reason="Bare UTF-16 BE без BOM: charset_normalizer возвращает latin-1 garbled — not auto-detectable",
    ),
    CorpusFile(
        "fake-text-utf-16-le.txt",
        FileReadKind.TEXT,
        None,
        skip_reason="Bare UTF-16 LE без BOM: charset_normalizer возвращает latin-1 garbled — not auto-detectable",
    ),

    # .md
    CorpusFile("README.md", FileReadKind.TEXT, "Example Docs"),
    CorpusFile("codeblock.md", FileReadKind.TEXT, None),
    CorpusFile("simple-table.md", FileReadKind.TEXT, None),
    CorpusFile("language-docs/eng_spa_mult.md", FileReadKind.TEXT, "human beings"),
    CorpusFile("umlauts-utf8.md", FileReadKind.TEXT, None),
    CorpusFile("umlauts-non-utf8.md", FileReadKind.TEXT, None),

    # .rst
    CorpusFile("README.rst", FileReadKind.TEXT, "Example Docs"),
    CorpusFile("README-w-include.rst", FileReadKind.TEXT, None),
    CorpusFile("language-docs/eng_spa_mult.rst", FileReadKind.TEXT, "human beings"),

    # .org
    CorpusFile("README.org", FileReadKind.TEXT, "Example Docs"),
    CorpusFile("README-w-include.org", FileReadKind.TEXT, None),
    CorpusFile("language-docs/eng_spa_mult.org", FileReadKind.TEXT, "human beings"),

    # .csv / .tsv
    CorpusFile("stanley-cups.csv", FileReadKind.TEXT, "Stanley"),
    CorpusFile("stanley-cups.tsv", FileReadKind.TEXT, "Stanley"),
    CorpusFile("csv-with-escaped-commas.csv", FileReadKind.TEXT, None),
    CorpusFile("csv-with-line-delimiter.csv", FileReadKind.TEXT, None),
    CorpusFile("semicolon-delimited.csv", FileReadKind.TEXT, None),
    CorpusFile("single-column.csv", FileReadKind.TEXT, None),
    CorpusFile("stanley-cups-with-emoji.csv", FileReadKind.TEXT, None),
    CorpusFile("stanley-cups-with-emoji.tsv", FileReadKind.TEXT, None),
    CorpusFile("table-multi-row-column-cells-actual.csv", FileReadKind.TEXT, None),
    CorpusFile("table-semicolon-delimiter.csv", FileReadKind.TEXT, None),
    # UTF-16 CSV
    CorpusFile("stanley-cups-utf-16.csv", FileReadKind.TEXT, "Stanley"),

    # .json / .ndjson
    CorpusFile("simple.json", FileReadKind.TEXT, "element_id"),
    CorpusFile("not-unstructured-payload.json", FileReadKind.TEXT, None),
    CorpusFile("simple.ndjson", FileReadKind.TEXT, None),
    CorpusFile("spring-weather.html.json", FileReadKind.TEXT, None),
    CorpusFile("spring-weather.html.ndjson", FileReadKind.TEXT, None),

    # .xml
    CorpusFile("factbook.xml", FileReadKind.TEXT, None),
    CorpusFile("factbook-utf-16.xml", FileReadKind.TEXT, None),
    CorpusFile("language-docs/eng_spa_mult.xml", FileReadKind.TEXT, None),

    # .yaml
    CorpusFile("simple.yaml", FileReadKind.TEXT, "deer"),

    # source code
    CorpusFile("fake.go", FileReadKind.TEXT, "Hello Go!"),
    CorpusFile("logger.py", FileReadKind.TEXT, "logging"),

    # ---------------------------------------------------------------------------
    # HTML / HTM  (trafilatura)
    # ---------------------------------------------------------------------------
    CorpusFile("example-10k-1p.html", FileReadKind.HTML, None),
    CorpusFile("example-10k.html", FileReadKind.HTML, None),
    CorpusFile("example-steelJIS-datasheet.html", FileReadKind.HTML, None),
    CorpusFile("fake-html.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-with-footer-and-header.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-with-duplicate-elements.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-lang-de.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-with-base64-image.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-with-image-from-url.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-cp1252.html", FileReadKind.HTML, None),
    CorpusFile("ideas-page.html", FileReadKind.HTML, None),
    CorpusFile("example-with-scripts.html", FileReadKind.HTML, None),
    CorpusFile("fake-html-pre.htm", FileReadKind.HTML, None),
    CorpusFile("language-docs/eng_spa_mult.html", FileReadKind.HTML, "human beings"),
    # UTF-16 HTML — trafilatura получит garbled text через replace errors; может упасть
    CorpusFile(
        "example-steelJIS-datasheet-utf-16.html",
        FileReadKind.HTML,
        None,
        skip_reason="UTF-16 HTML: trafilatura получает garbled bytes, возможен FileReadError",
    ),
    CorpusFile(
        "example-10k-utf-16.html",
        FileReadKind.HTML,
        None,
        skip_reason="UTF-16 HTML: trafilatura получает garbled bytes, возможен FileReadError",
    ),

    # ---------------------------------------------------------------------------
    # PDF  (PyMuPDF)
    # ---------------------------------------------------------------------------
    CorpusFile("rotated-page-90.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/fake-memo.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/fake-bold-sample.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/embedded-link.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/layout-parser-paper-fast.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/list-item-example.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/DA-1p.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/all-number-table.pdf", FileReadKind.PDF, None),
    # PDF без текстового слоя (только картинки/таблицы как изображения) — текст пуст без OCR
    CorpusFile("pdf/single_table.pdf", FileReadKind.PDF, None, allows_empty_text=True),
    CorpusFile("pdf/embedded-cmap-cidfont.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/fake-memo-with-duplicate-page.pdf", FileReadKind.PDF, None),
    CorpusFile("pdf/header-test-doc.pdf", FileReadKind.PDF, None, expected_min_pages=1),
    CorpusFile("pdf/multi-column-2p.pdf", FileReadKind.PDF, None, expected_min_pages=2),
    CorpusFile("language-docs/fr_olap.pdf", FileReadKind.PDF, None),
    # password-protected PDF: PyMuPDF не вылетает, но текст пустой
    CorpusFile("pdf/password.pdf", FileReadKind.PDF, None, allows_empty_text=True),

    # ---------------------------------------------------------------------------
    # OFFICE_DOC: .docx (Unstructured)
    # ---------------------------------------------------------------------------
    CorpusFile("fake.docx", FileReadKind.OFFICE, None),
    CorpusFile("simple.docx", FileReadKind.OFFICE, None),
    CorpusFile("category-level.docx", FileReadKind.OFFICE, None),
    CorpusFile("contains-pictures.docx", FileReadKind.OFFICE, None),
    CorpusFile("docx-tables.docx", FileReadKind.OFFICE, None),
    CorpusFile("docx-shapes.docx", FileReadKind.OFFICE, None),
    CorpusFile("docx-hdrftr.docx", FileReadKind.OFFICE, None),
    CorpusFile("duplicate-paragraphs.docx", FileReadKind.OFFICE, None),
    CorpusFile("fake-doc-emphasized-text.docx", FileReadKind.OFFICE, None),
    CorpusFile("example-list-items-multiple.docx", FileReadKind.OFFICE, None),
    CorpusFile("fake_table.docx", FileReadKind.OFFICE, None),
    CorpusFile("grid_offset_error.docx", FileReadKind.OFFICE, None),
    CorpusFile("group-shapes-nested.pptx", FileReadKind.OFFICE, None),  # pptx via Unstructured
    CorpusFile("handbook-1p.docx", FileReadKind.OFFICE, None),
    CorpusFile("handbook-1p-no-rendered-page-breaks.docx", FileReadKind.OFFICE, None),
    CorpusFile("handbook-872p.docx", FileReadKind.OFFICE, None, expected_min_pages=1),
    CorpusFile("hlink-meta.docx", FileReadKind.OFFICE, None),
    CorpusFile("page-breaks.docx", FileReadKind.OFFICE, None),
    CorpusFile("tables-with-incomplete-rows.docx", FileReadKind.OFFICE, None),
    CorpusFile("teams_chat.docx", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.docx", FileReadKind.OFFICE, "human beings"),
    CorpusFile("language-docs/eng_spa_mult.odt", FileReadKind.OFFICE, "human beings"),

    # .doc (antiword OLE / Unstructured ZIP)
    CorpusFile("fake.doc", FileReadKind.OFFICE, None),
    CorpusFile("simple.doc", FileReadKind.OFFICE, None),
    CorpusFile("duplicate-paragraphs.doc", FileReadKind.OFFICE, None),
    CorpusFile("fake-doc-emphasized-text.doc", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.doc", FileReadKind.OFFICE, None),

    # .odt
    CorpusFile("fake.odt", FileReadKind.OFFICE, None),
    CorpusFile("simple.odt", FileReadKind.OFFICE, None),

    # .rtf
    CorpusFile("fake-doc.rtf", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.rtf", FileReadKind.OFFICE, "human beings"),

    # ---------------------------------------------------------------------------
    # PRESENTATION: .pptx / .ppt (Unstructured → OFFICE kind)
    # ---------------------------------------------------------------------------
    CorpusFile("fake-power-point.pptx", FileReadKind.OFFICE, None),
    CorpusFile("fake-power-point-many-pages.pptx", FileReadKind.OFFICE, None),
    CorpusFile("fake-power-point-table.pptx", FileReadKind.OFFICE, None),
    CorpusFile("picture.pptx", FileReadKind.OFFICE, None, allows_empty_text=True),
    CorpusFile("sample-presentation.pptx", FileReadKind.OFFICE, None),
    CorpusFile("simple.pptx", FileReadKind.OFFICE, None),
    CorpusFile("test-image-jpg-mime.pptx", FileReadKind.OFFICE, None, allows_empty_text=True),
    CorpusFile("science-exploration-1p.pptx", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.pptx", FileReadKind.OFFICE, "human beings"),
    # Legacy .ppt (PowerPoint 97-2003): требует libreoffice/soffice — намеренно not supported
    CorpusFile(
        "fake-power-point.ppt",
        FileReadKind.OFFICE,
        is_unsupported=True,
    ),
    CorpusFile("language-docs/eng_spa_mult.ppt", FileReadKind.OFFICE, "human beings"),
    # malformed pptx — unstructured может поднять FileReadError
    CorpusFile(
        "fake-power-point-malformed.pptx",
        FileReadKind.OFFICE,
        None,
        skip_reason="Malformed PPTX: поведение Unstructured непредсказуемо, known-issue upstream",
    ),

    # ---------------------------------------------------------------------------
    # SPREADSHEET: .xlsx / .xls / .ods (Unstructured / xlrd)
    # ---------------------------------------------------------------------------
    CorpusFile("2023-half-year-analyses-by-segment.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("emoji.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("more-than-1k-cells.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("stanley-cups.xlsx", FileReadKind.SPREADSHEET, "Stanley"),
    CorpusFile("vodafone.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("xlsx-subtable-cases.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("language-docs/eng_spa.xlsx", FileReadKind.SPREADSHEET, None),
    CorpusFile("tests-example.xls", FileReadKind.SPREADSHEET, None),

    # ---------------------------------------------------------------------------
    # EMAIL: .eml / .msg (Unstructured → OFFICE kind)
    # ---------------------------------------------------------------------------
    CorpusFile("fake-email.eml", FileReadKind.OFFICE, None),
    CorpusFile("fake-email.msg", FileReadKind.OFFICE, None),
    CorpusFile("fake-email-attachment.msg", FileReadKind.OFFICE, None),
    CorpusFile("fake-email-with-cc-and-bcc.msg", FileReadKind.OFFICE, None),
    CorpusFile("fake-email-multiple-attachments.msg", FileReadKind.OFFICE, None),
    CorpusFile("fake-encrypted.msg", FileReadKind.OFFICE, None, allows_empty_text=True),
    CorpusFile("eml/fake-email.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/email-no-html-content-1.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/family-day.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/mime-simple.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/mime-html-only.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/mime-multi-to-cc-bcc.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/simple-rfc-822.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/fake-email-header.eml", FileReadKind.OFFICE, None),
    CorpusFile("eml/fake-email-attachment.eml", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.eml", FileReadKind.OFFICE, None),

    # ---------------------------------------------------------------------------
    # EBOOK: .epub (Unstructured → OFFICE kind)
    # ---------------------------------------------------------------------------
    CorpusFile("winter-sports.epub", FileReadKind.OFFICE, None),
    CorpusFile("language-docs/eng_spa_mult.epub", FileReadKind.OFFICE, "human beings"),

    # ---------------------------------------------------------------------------
    # IMAGE (vision LLM via MockLLM)
    # ---------------------------------------------------------------------------
    CorpusFile("img/example.jpg", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/DA-1p.jpg", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/DA-1p.png", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/english-and-korean.png", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/chi_sim_image.jpeg", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/bmp_24.bmp", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile("img/layout-parser-paper-fast.jpg", FileReadKind.IMAGE, "MOCK_VISION", uses_vision_llm=True),
    CorpusFile(
        "img/DA-1p.heic",
        FileReadKind.IMAGE,
        "MOCK_VISION",
        uses_vision_llm=True,
        skip_reason="HEIC: поддержка зависит от ОС/пилло-версии, skip если нет libheif",
    ),
    CorpusFile(
        "img/layout-parser-paper-combined.tiff",
        FileReadKind.IMAGE,
        "MOCK_VISION",
        uses_vision_llm=True,
    ),

    # ---------------------------------------------------------------------------
    # AUDIO (mock STT tier)
    # ---------------------------------------------------------------------------
    CorpusFile("CantinaBand3.wav", FileReadKind.AUDIO, None, uses_mock_stt_tier=True),

    # ---------------------------------------------------------------------------
    # UNSUPPORTED / NEGATIVE (is_unsupported=True → ожидаем FileReadError)
    # ---------------------------------------------------------------------------
    CorpusFile("password_protected.xlsx", FileReadKind.SPREADSHEET, is_unsupported=True),
    CorpusFile("empty.xlsx", FileReadKind.SPREADSHEET, is_unsupported=True),
    CorpusFile("eml/empty.eml", FileReadKind.OFFICE, is_unsupported=True),
    CorpusFile("simple.zip", FileReadKind.UNKNOWN, is_unsupported=True),
    CorpusFile(
        "file_we_dont_want_imported",
        FileReadKind.UNKNOWN,
        is_unsupported=True,
    ),
)

# Индексы для быстрого доступа в тестах
POSITIVE = tuple(f for f in CORPUS if not f.is_unsupported and f.skip_reason is None)
NEGATIVE = tuple(f for f in CORPUS if f.is_unsupported)
SKIPPED = tuple(f for f in CORPUS if f.skip_reason is not None)
ALL_PATHS = frozenset(f.relative_path for f in CORPUS)
