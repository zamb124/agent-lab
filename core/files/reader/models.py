"""Единая схема результата чтения файла (FileReadResult)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.files.file_ref import FileRef, file_id_from_download_url
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_array,
    require_json_object,
)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

MAX_READ_BUDGET: int = 100_000
"""Максимальный бюджет символов на один read-вызов (100K chars)."""

TRUNCATION_MARKER: str = "\n…[truncated]"
"""Маркер, добавляемый при обрезании текста по бюджету."""

DEFAULT_VIRTUAL_PAGE_SIZE: int = 4_000
"""Размер виртуальной страницы для сплошных форматов (txt/csv/json/html/docx без нативных страниц)."""

MAX_NESTED_DEFAULT: int = 32
"""Максимум вложенных content на один read-вызов (Parts / recursive)."""

NESTED_OMITTED_STUB: str = "(omitted:budget)"
"""Заглушка якоря nested, не влезшего в budget / max_nested."""


def default_page_label(index: int) -> str:
    """Стабильный label страницы, когда reader не дал свой (VIRTUAL / unstructured без page_number)."""
    if index < 0:
        raise ValueError("page index must be >= 0")
    return f"page_{index + 1}"


def resolved_page_label(index: int, label: str | None) -> str:
    """Непустой label страницы: свой, иначе ``page_{index+1}``."""
    if label is not None:
        stripped = label.strip()
        if stripped:
            return stripped
    return default_page_label(index)

VISION_FULL_READ_MAX_PAGES: int = 20
"""Порог native-единиц, выше которого vision применяется только к запрошенному окну."""

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


class NestedMode(StrEnum):
    """Как read_file отдаёт вложенный content другого content_type."""

    REFS = "refs"
    PARTS = "parts"


# ---------------------------------------------------------------------------
# Вспомогательные модели render-слоя
# ---------------------------------------------------------------------------


class PageLayout(BaseModel):
    """Метаданные разбиения на страницы."""

    kind: PageLayoutKind
    pages_total: int = Field(ge=0)
    page_size: int = Field(ge=0, description="Размер виртуальной страницы; 0 для нативных.")


class ExtractBlockKind(StrEnum):
    """Логический блок страницы FileExtract."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CODE = "code"
    FIGURE = "figure"


class ExtractBlock(BaseModel):
    """Блок страницы: текст и связанные FileRef (для figure)."""

    kind: ExtractBlockKind
    text: str = ""
    level: int | None = Field(default=None, ge=1)
    files: list[FileRef] = Field(default_factory=list)


class UniversalPage(BaseModel):
    """Единая страница после нормализации (native или virtual)."""

    index: int = Field(ge=0)
    label: str = ""
    text: str = ""
    content_mode: ContentMode
    blocks: list[ExtractBlock] = Field(default_factory=list)
    files: list[FileRef] = Field(default_factory=list)
    nested: list["NestedContent"] = Field(default_factory=list)


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

    page_start: int = Field(default=0, ge=0, description="Индекс первой страницы (0-based).")
    page_end: int = Field(default=-1, description="-1 = до конца.")
    page_summarizations: bool = Field(
        default=False,
        description=(
            "True — вместо полного текста страницы отдавать LLM-суммаризацию: "
            "текст страницы + nested images (multimodal), если bytes доступны."
        ),
    )
    summarization_prompt: str = Field(
        default="",
        description=(
            "Доп. фокус суммаризации страниц (поверх сегментной инструкции); "
            "пустое — только дефолт. При nested images модель видит и картинки."
        ),
    )
    summarization_model: str = Field(
        default="",
        description="Модель LLM для суммаризации; пустое — дефолт платформы.",
    )
    vision_prompt: str = Field(
        default="",
        description="Промпт vision-линии (OCR/описание страницы); пустое — дефолтный.",
    )
    vision_model: str | None = Field(
        default=None,
        description="Модель для vision-линии; None — дефолт платформы.",
    )
    compression: CompressionMode = Field(
        default=CompressionMode.NEVER,
        description="Режим сжатия текста перед отдачей: never | before_llm | on_error.",
    )
    transcription_company_id: str | None = Field(
        default=None,
        description="company_id для транскрипции audio/video; None — компания из контекста.",
    )
    forced_lane: ReadLane | None = Field(
        default=None,
        description="Принудительная линия чтения text | vision | stt | hybrid; None — авто.",
    )
    persist_assets_namespace: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Namespace RAG: сохранить ассеты страниц как FileRecord "
            "(FileSourceKind.RAG_DOCUMENT). Без значения ассеты в extract не persist'ятся."
        ),
    )
    names: list[str] = Field(
        default_factory=list,
        description=(
            "Список original_name из state.files. "
            "Передавай JSON-массив строк, например [\"report.pdf\"], не строку с JSON внутри."
        ),
    )
    budget: int = Field(
        default=MAX_READ_BUDGET,
        ge=0,
        description="Общий бюджет символов на чтение всех файлов вызова.",
    )
    nested_mode: NestedMode = Field(
        default=NestedMode.REFS,
        description=(
            "refs — якоря + FileRef в state.files; "
            "parts — якоря + A2A Part(raw) в tool-result."
        ),
    )
    recursive: bool = Field(
        default=True,
        description=(
            "True (default) — один уровень авто-read вложенного content в окне страниц "
            "(только с nested_mode=refs; при parts принудительно false)."
        ),
    )
    max_nested: int = Field(
        default=MAX_NESTED_DEFAULT,
        ge=0,
        description="Лимит вложенных content на вызов (Parts и recursive).",
    )

    @model_validator(mode="before")
    @classmethod
    def parts_disables_recursive(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict):
            return data
        payload = require_json_object(data, "ReadFileArgs")
        mode = payload.get("nested_mode", NestedMode.REFS.value)
        if isinstance(mode, NestedMode):
            mode_value = mode.value
        elif isinstance(mode, str):
            mode_value = mode
        else:
            return payload
        if mode_value == NestedMode.PARTS.value:
            patched: JsonObject = {**payload, "recursive": False}
            return patched
        return payload

    @field_validator(
        "summarization_prompt",
        "summarization_model",
        "vision_prompt",
        mode="before",
    )
    @classmethod
    def coerce_optional_prompt_strings(cls, value: JsonValue) -> str:
        """LLM wire часто шлёт null вместо пустой строки для optional prompt/model."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        raise ValueError("must be a string or null")

    @field_validator("names", mode="before")
    @classmethod
    def coerce_names_from_llm_wire(cls, value: JsonValue) -> list[str]:
        """LLM tool wire: names иногда приходит строкой '["a.jpg"]' вместо массива."""
        if value is None:
            return []
        items: JsonArray
        if isinstance(value, list):
            items = require_json_array(value, "ReadFileArgs.names")
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

    def canonical_text(self) -> str:
        parts = [page.text.strip() for page in self.pages if page.text.strip()]
        return "\n\n".join(parts)


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
    nested_mode: NestedMode = NestedMode.REFS
    recursive: bool = False
    nested: list["NestedContent"] = Field(default_factory=list)


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
    DATA_TABLE = "data_table"


class ReadAssetKind(StrEnum):
    EMBEDDED_IMAGE = "embedded_image"
    PAGE_RASTER = "page_raster"
    ATTACHMENT = "attachment"
    OFFICE_MEDIA = "office_media"


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


class NestedContent(BaseModel):
    """Вложенный content внутри контейнера (image/*, вложения, будущие бинари)."""

    anchor: str = Field(min_length=1)
    original_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    kind: ReadAssetKind
    checksum: str = Field(description="SHA-256 hex сырых байт")
    page_index: int = Field(ge=0)
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    bytes_b64: str | None = Field(
        default=None,
        description="Ephemeral base64; strip перед Redis extract-cache",
    )


class ReadPage(BaseModel):
    index: int = Field(ge=0)
    label: str | None = None
    text: str = ""
    assets: list[ReadAsset] = Field(default_factory=list)
    blocks: list[ExtractBlock] = Field(default_factory=list)


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
