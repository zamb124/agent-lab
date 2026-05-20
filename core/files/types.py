"""Единый реестр типов файлов платформы.

Источник правды для бэкенда и UI: расширения, MIME-типы, категории.
UI получает данные через GET /api/platform/file-types (core/app/file_types_route.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FileCategory(StrEnum):
    TEXT = "text"
    PDF = "pdf"
    OFFICE_DOC = "office_doc"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    EMAIL = "email"
    EBOOK = "ebook"


@dataclass(frozen=True)
class FileTypeEntry:
    extension: str
    mime_types: tuple[str, ...]
    category: FileCategory


FILE_TYPE_REGISTRY: tuple[FileTypeEntry, ...] = (
    # --- TEXT ---
    FileTypeEntry(".txt", ("text/plain",), FileCategory.TEXT),
    FileTypeEntry(".md", ("text/markdown", "text/x-markdown"), FileCategory.TEXT),
    FileTypeEntry(".rst", ("text/x-rst",), FileCategory.TEXT),
    FileTypeEntry(".csv", ("text/csv",), FileCategory.TEXT),
    FileTypeEntry(".tsv", ("text/tab-separated-values",), FileCategory.TEXT),
    FileTypeEntry(".json", ("application/json",), FileCategory.TEXT),
    FileTypeEntry(".xml", ("application/xml", "text/xml"), FileCategory.TEXT),
    FileTypeEntry(".html", ("text/html",), FileCategory.TEXT),
    FileTypeEntry(".htm", ("text/html",), FileCategory.TEXT),
    FileTypeEntry(".css", ("text/css",), FileCategory.TEXT),
    FileTypeEntry(".log", ("text/plain",), FileCategory.TEXT),
    FileTypeEntry(".ini", ("text/plain",), FileCategory.TEXT),
    FileTypeEntry(".yaml", ("application/x-yaml", "text/yaml"), FileCategory.TEXT),
    FileTypeEntry(".yml", ("application/x-yaml", "text/yaml"), FileCategory.TEXT),
    FileTypeEntry(".toml", ("application/toml",), FileCategory.TEXT),
    # Emacs Org mode
    FileTypeEntry(".org", ("text/x-org",), FileCategory.TEXT),
    # JSON с разделением по строкам
    FileTypeEntry(".ndjson", ("application/x-ndjson",), FileCategory.TEXT),
    # Исходный код — MIME text/plain (как GitHub/git)
    FileTypeEntry(".py", ("text/x-python", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".go", ("text/x-go", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".ts", ("text/typescript", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".tsx", ("text/typescript", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".js", ("text/javascript", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".jsx", ("text/javascript", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".java", ("text/x-java-source", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".c", ("text/x-c", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".cpp", ("text/x-c++", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".h", ("text/x-c", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".hpp", ("text/x-c++", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".rs", ("text/x-rustsrc", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".rb", ("text/x-ruby", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".sh", ("text/x-sh", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".bash", ("text/x-sh", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".zsh", ("text/x-sh", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".kt", ("text/x-kotlin", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".swift", ("text/x-swift", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".scala", ("text/x-scala", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".php", ("text/x-php", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".sql", ("text/x-sql", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".lua", ("text/x-lua", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".pl", ("text/x-perl", "text/plain"), FileCategory.TEXT),
    FileTypeEntry(".r", ("text/x-r", "text/plain"), FileCategory.TEXT),
    # --- PDF ---
    FileTypeEntry(".pdf", ("application/pdf",), FileCategory.PDF),
    # --- OFFICE_DOC ---
    FileTypeEntry(".doc", ("application/msword",), FileCategory.OFFICE_DOC),
    FileTypeEntry(
        ".docx",
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
        FileCategory.OFFICE_DOC,
    ),
    FileTypeEntry(
        ".odt",
        ("application/vnd.oasis.opendocument.text",),
        FileCategory.OFFICE_DOC,
    ),
    FileTypeEntry(".rtf", ("application/rtf", "text/rtf"), FileCategory.OFFICE_DOC),
    # --- SPREADSHEET ---
    FileTypeEntry(".xls", ("application/vnd.ms-excel",), FileCategory.SPREADSHEET),
    FileTypeEntry(
        ".xlsx",
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
        FileCategory.SPREADSHEET,
    ),
    FileTypeEntry(
        ".ods",
        ("application/vnd.oasis.opendocument.spreadsheet",),
        FileCategory.SPREADSHEET,
    ),
    # --- PRESENTATION ---
    FileTypeEntry(
        ".ppt", ("application/vnd.ms-powerpoint",), FileCategory.PRESENTATION
    ),
    FileTypeEntry(
        ".pptx",
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
        FileCategory.PRESENTATION,
    ),
    FileTypeEntry(
        ".odp",
        ("application/vnd.oasis.opendocument.presentation",),
        FileCategory.PRESENTATION,
    ),
    # --- IMAGE ---
    FileTypeEntry(".jpg", ("image/jpeg",), FileCategory.IMAGE),
    FileTypeEntry(".jpeg", ("image/jpeg",), FileCategory.IMAGE),
    FileTypeEntry(".png", ("image/png",), FileCategory.IMAGE),
    FileTypeEntry(".gif", ("image/gif",), FileCategory.IMAGE),
    FileTypeEntry(".webp", ("image/webp",), FileCategory.IMAGE),
    FileTypeEntry(".svg", ("image/svg+xml",), FileCategory.IMAGE),
    FileTypeEntry(".bmp", ("image/bmp",), FileCategory.IMAGE),
    FileTypeEntry(".tiff", ("image/tiff",), FileCategory.IMAGE),
    FileTypeEntry(".tif", ("image/tiff",), FileCategory.IMAGE),
    FileTypeEntry(".heic", ("image/heic",), FileCategory.IMAGE),
    FileTypeEntry(".heif", ("image/heif",), FileCategory.IMAGE),
    # --- AUDIO ---
    FileTypeEntry(".mp3", ("audio/mpeg",), FileCategory.AUDIO),
    FileTypeEntry(".wav", ("audio/wav", "audio/wave", "audio/x-wav"), FileCategory.AUDIO),
    FileTypeEntry(".ogg", ("audio/ogg",), FileCategory.AUDIO),
    FileTypeEntry(".m4a", ("audio/mp4", "audio/x-m4a"), FileCategory.AUDIO),
    FileTypeEntry(".flac", ("audio/flac", "audio/x-flac"), FileCategory.AUDIO),
    FileTypeEntry(".aac", ("audio/aac",), FileCategory.AUDIO),
    FileTypeEntry(".wma", ("audio/x-ms-wma",), FileCategory.AUDIO),
    FileTypeEntry(".opus", ("audio/opus",), FileCategory.AUDIO),
    FileTypeEntry(".amr", ("audio/amr",), FileCategory.AUDIO),
    # --- VIDEO ---
    FileTypeEntry(".mp4", ("video/mp4",), FileCategory.VIDEO),
    FileTypeEntry(".mkv", ("video/x-matroska",), FileCategory.VIDEO),
    FileTypeEntry(".avi", ("video/x-msvideo",), FileCategory.VIDEO),
    FileTypeEntry(".mov", ("video/quicktime",), FileCategory.VIDEO),
    FileTypeEntry(".wmv", ("video/x-ms-wmv",), FileCategory.VIDEO),
    FileTypeEntry(".flv", ("video/x-flv",), FileCategory.VIDEO),
    FileTypeEntry(".m4v", ("video/x-m4v",), FileCategory.VIDEO),
    FileTypeEntry(".webm", ("video/webm",), FileCategory.VIDEO),
    FileTypeEntry(".3gp", ("video/3gpp",), FileCategory.VIDEO),
    # --- ARCHIVE ---
    FileTypeEntry(".zip", ("application/zip", "application/x-zip-compressed"), FileCategory.ARCHIVE),
    FileTypeEntry(".rar", ("application/x-rar-compressed",), FileCategory.ARCHIVE),
    FileTypeEntry(".7z", ("application/x-7z-compressed",), FileCategory.ARCHIVE),
    FileTypeEntry(".tar", ("application/x-tar",), FileCategory.ARCHIVE),
    FileTypeEntry(".gz", ("application/gzip",), FileCategory.ARCHIVE),
    # --- EMAIL ---
    FileTypeEntry(".eml", ("message/rfc822",), FileCategory.EMAIL),
    FileTypeEntry(".msg", ("application/vnd.ms-outlook",), FileCategory.EMAIL),
    # --- EBOOK ---
    FileTypeEntry(".epub", ("application/epub+zip",), FileCategory.EBOOK),
)


def _build_ext_index() -> dict[str, FileTypeEntry]:
    idx: dict[str, FileTypeEntry] = {}
    for entry in FILE_TYPE_REGISTRY:
        idx[entry.extension] = entry
    return idx


def _build_mime_index() -> dict[str, FileCategory]:
    idx: dict[str, FileCategory] = {}
    for entry in FILE_TYPE_REGISTRY:
        for mime in entry.mime_types:
            if mime not in idx:
                idx[mime] = entry.category
    return idx


_EXT_INDEX: dict[str, FileTypeEntry] = _build_ext_index()
_MIME_INDEX: dict[str, FileCategory] = _build_mime_index()


def extensions_for(*categories: FileCategory) -> frozenset[str]:
    """Все расширения (с точкой) для указанных категорий."""
    cats = set(categories)
    return frozenset(e.extension for e in FILE_TYPE_REGISTRY if e.category in cats)


def mimes_for(*categories: FileCategory) -> frozenset[str]:
    """Все MIME-типы для указанных категорий."""
    cats = set(categories)
    result: set[str] = set()
    for entry in FILE_TYPE_REGISTRY:
        if entry.category in cats:
            result.update(entry.mime_types)
    return frozenset(result)


def ext_to_mime(ext: str) -> str:
    """Основной MIME-тип по расширению (с точкой). Если неизвестно — application/octet-stream."""
    entry = _EXT_INDEX.get(ext.lower())
    if entry is None:
        return "application/octet-stream"
    return entry.mime_types[0]


def ext_to_category(ext: str) -> FileCategory | None:
    """Категория по расширению (с точкой). None если расширение не в реестре."""
    entry = _EXT_INDEX.get(ext.lower())
    if entry is None:
        return None
    return entry.category


def mime_to_category(mime: str) -> FileCategory | None:
    """Категория по MIME-типу. None если MIME не в реестре."""
    normalized = mime.split(";", 1)[0].strip().lower()
    return _MIME_INDEX.get(normalized)


def accept_string_for(*categories: FileCategory) -> str:
    """HTML accept-строка для <input type="file"> по указанным категориям.

    Формирует список расширений (.pdf,.docx,...) + wildcard MIME (image/*,audio/*,video/*),
    чтобы браузер допускал файлы с нестандартными расширениями для медиатипов.
    """
    cats = set(categories)
    exts = sorted(extensions_for(*categories))
    wildcards: list[str] = []
    if FileCategory.IMAGE in cats:
        wildcards.append("image/*")
    if FileCategory.AUDIO in cats:
        wildcards.append("audio/*")
    if FileCategory.VIDEO in cats:
        wildcards.append("video/*")
    parts = wildcards + exts
    return ",".join(parts)


ALL_CATEGORIES: tuple[FileCategory, ...] = tuple(FileCategory)
