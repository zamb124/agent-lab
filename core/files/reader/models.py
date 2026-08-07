"""Единая схема результата чтения файла (FileReadResult)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.files.file_ref import FileRef, file_id_from_download_url
from core.types import JsonArray, parse_json_value, require_json_array

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

MAX_READ_BUDGET: int = 100_000
"""Максимальный бюджет символов на один read-вызов (100K chars)."""

TRUNCATION_MARKER: str = "\n…[truncated]"
"""Маркер, добавляемый при обрезании текста по бюджету."""

DEFAULT_VIRTUAL_PAGE_SIZE: int = 4_000
"""Размер виртуальной страницы для сплошных форматов (txt/csv/json/html/docx без нативных страниц)."""

VISION_FULL_READ_MAX_PAGES: int = 20
"""Порог страниц PDF, выше которого vision применяется лениво только к запрошенным страницам."""

# ---------------------------------------------------------------------------
# Enums: режимы контента, layout, лейн чтения, причина остановки, сжатие
# ---------------------------------------------------------------------------


class ContentMode(StrEnum):
    """Режим отображения контента в результате чтения."""

    FULL = "full"
    SUMMARY = "summary"
    VISION = "vision"
    STT = "stt"
    HYBRID = "hybrid"


class PageLayoutKind(StrEnum):
    """Тип разбиения на страницы."""

    NATIVE = "native"
    VIRTUAL = "virtual"


class ReadLane(StrEnum):
    """Канал чтения: текст / vision / STT / гибрид."""

    TEXT = "text"
    VISION = "vision"
    STT = "stt"
    HYBRID = "hybrid"


class StopReason(StrEnum):
    """Причина остановки итеративного чтения."""

    COMPLETE = "complete"
    PAGE_END_REACHED = "page_end_reached"
    BUDGET_EXHAUSTED = "budget_exhausted"
    OUT_OF_RANGE = "out_of_range"
    ERROR = "error"


class CompressionMode(StrEnum):
    """Режим сжатия изображений перед отправкой в vision-модель."""

    NEVER = "never"
    BEFORE_LLM = "before_llm"
    ON_ERROR = "on_error"


# ---------------------------------------------------------------------------
# Вспомогательные модели render-слоя
# ---------------------------------------------------------------------------


class PageLayout(BaseModel):
    """Метаданные разбиения на страницы."""

    kind: PageLayoutKind
    pages_total: int = Field(ge=0)
    page_size: int = Field(ge=0, description="Размер виртуальной страницы; 0 для нативных.")


class UniversalPage(BaseModel):
    """Единая страница после нормализации (native или virtual)."""

    index: int = Field(ge=0)
    label: str = ""
    text: str = ""
    content_mode: ContentMode


class PageResult(BaseModel):
    """Одна страница в финальном FileResult (с учётом бюджета и суммаризации)."""

    page: int = Field(ge=0)
    label: str
    content_mode: ContentMode
    span_chars: int = Field(ge=0)
    truncated: bool = False
    result: str


class Continuation(BaseModel):
    """Инструкция продолжения чтения для следующего вызова."""

    file_id: str | None = None
    next_page_start: int = Field(default=0, ge=0)
    has_more: bool = False
    next_actions: list[str] = Field(default_factory=list)


class ReadFileArgs(BaseModel):
    """Единые аргументы канонического FileReader.read (extract + render)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page_start: int = Field(default=0, ge=0)
    page_end: int = Field(default=-1, description="-1 = до конца.")
    page_summarizations: bool = False
    summarization_prompt: str = ""
    summarization_model: str = ""
    vision_prompt: str = ""
    vision_model: str | None = None
    compression: CompressionMode = CompressionMode.NEVER
    transcription_company_id: str | None = None
    forced_lane: ReadLane | None = None
    names: list[str] = Field(
        default_factory=list,
        description=(
            "Список original_name из state.files. "
            "Передавай JSON-массив строк, например [\"report.pdf\"], не строку с JSON внутри."
        ),
    )
    budget: int = Field(default=MAX_READ_BUDGET, ge=0)

    @field_validator("names", mode="before")
    @classmethod
    def coerce_names_from_llm_wire(cls, value: object) -> list[str]:
        """LLM tool wire: names иногда приходит строкой '["a.jpg"]' вместо массива."""
        if value is None:
            return []
        items: JsonArray
        if isinstance(value, list):
            items = require_json_array(cast(object, value), "ReadFileArgs.names")
        elif isinstance(value, str):
            text = value.strip()
            if text == "":
                return []
            if text.startswith("["):
                items = require_json_array(
                    parse_json_value(text, "ReadFileArgs.names"),
                    "ReadFileArgs.names",
                )
            else:
                return [text]
        else:
            raise ValueError("names must be a list of strings")
        names: list[str] = []
        for item in items:
            if not isinstance(item, str) or item.strip() == "":
                raise ValueError("names array items must be non-empty strings")
            names.append(item.strip())
        return names


# ---------------------------------------------------------------------------
# Основные модели extract и result
# ---------------------------------------------------------------------------


class FileExtract(BaseModel):
    """Нормализованный экстракт файла перед рендерингом в FileResult."""

    file_id: str | None = None
    file_name: str
    kind: FileReadKind
    mime_type: str = "application/octet-stream"
    read_lane: ReadLane
    page_layout: PageLayout
    pages: list[UniversalPage] = Field(default_factory=list)
    content_chars_total: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    source_checksum: str | None = None


class FileResult(BaseModel):
    """Финальный результат чтения — то, что получает LLM."""

    file_name: str
    file_id: str | None = None
    success: bool
    error: str = ""
    warnings: list[str] = Field(default_factory=list)
    kind: FileReadKind
    mime_type: str = "application/octet-stream"
    read_lane: ReadLane
    page_layout: PageLayout
    pages_total: int = Field(default=0, ge=0)
    content_chars_total: int = Field(default=0, ge=0)
    page_start: int = Field(default=0, ge=0)
    pages_processed: int = Field(default=0, ge=0)
    complete: bool = False
    truncated: bool = False
    stop_reason: StopReason
    page_summarizations_used: bool = False
    results: list[PageResult] = Field(default_factory=list)
    continuation: Continuation


class ReadFileEnvelope(BaseModel):
    """Конверт для единого ответа read_file: несколько файлов за один вызов."""

    success: bool
    tool: str
    files_processed: int = Field(ge=0)
    names: list[str] = Field(default_factory=list)
    budget: int = Field(ge=0)
    result_chars_returned: int = Field(ge=0)
    files: list[FileResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Существующие модели (ниже без изменений)
# ---------------------------------------------------------------------------


class FileReadKind(StrEnum):
    TEXT = "text"
    HTML = "html"
    PDF = "pdf"
    OFFICE = "office"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ReadAssetKind(StrEnum):
    EMBEDDED_IMAGE = "embedded_image"
    PAGE_RASTER = "page_raster"
    ATTACHMENT = "attachment"


class ReadAsset(BaseModel):
    kind: ReadAssetKind
    content_type: str | None = None
    checksum: str = Field(description="SHA-256 hex сырых байт фрагмента")
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    bytes_b64: str | None = Field(
        default=None,
        description="Base64 только при ReadOptions.include_asset_bytes=True",
    )


class ReadPage(BaseModel):
    index: int = Field(ge=0)
    label: str | None = None
    text: str = ""
    assets: list[ReadAsset] = Field(default_factory=list)


class FileReadResult(BaseModel):
    file_name: str
    content_type: str | None = None
    detected_kind: FileReadKind
    page_count: int = Field(ge=0)
    pages: list[ReadPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_file_id: str | None = None
    source_checksum: str | None = Field(
        default=None,
        description="SHA-256 hex всего исходного файла",
    )


class ReadOptions(BaseModel):
    include_asset_bytes: bool = False
    source_file_id: str | None = None
    source_checksum: str | None = None
    vision_model: str | None = None
    vision_prompt: str | None = Field(
        default=None,
        description="Текст инструкции для vision-модели при разборе изображений; иначе встроенный промпт извлечения текста.",
    )
    transcription_company_id: str | None = Field(
        default=None,
        description=(
            "company_id для tier-резолва STT при чтении audio/video; "
            "если None — из активного платформенного контекста."
        ),
    )


def merge_file_ref_read_options(
    file_ref: FileRef,
    opts: ReadOptions,
) -> ReadOptions:
    if isinstance(opts.source_file_id, str) and opts.source_file_id.strip():
        return opts
    if file_ref.file_id is not None:
        return opts.model_copy(update={"source_file_id": file_ref.file_id})
    if file_ref.url is not None:
        parsed = file_id_from_download_url(file_ref.url)
        if parsed:
            return opts.model_copy(update={"source_file_id": parsed})
    return opts


class FileTypeInfo(BaseModel):
    detected_kind: FileReadKind
    content_type: str | None = None
    extension: str = ""
