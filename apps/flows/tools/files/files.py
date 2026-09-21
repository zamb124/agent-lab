"""
Тулы для работы с файлами в flow (вложения state.files).

read_file — чтение вложений; create_file — FileWriter() + create_file (процесс настроен через FileWriter.configure_process_upload при старте).
"""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.services.flow_ui_cards import show_files
from apps.flows.src.state.state_utils import find_file
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.files.file_ref import FileRef, stored_file_ref
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.models import (
    MAX_READ_BUDGET,
    CompressionMode,
    Continuation,
    FileReadKind,
    FileResult,
    PageLayout,
    PageLayoutKind,
    ReadFileArgs,
    ReadLane,
    StopReason,
)
from core.files.writer import FileWriter
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

_CREATE_FILE_TOOL_DESCRIPTION = """
Создаёт файл в хранилище платформы и возвращает ссылку на скачивание.

Ответ: file_id, url (путь для скачивания), original_name, content_type,
file_size, checksum (если есть), is_public.
Ошибки (нет компании в контексте, неверный base64, нет расширения в имени и т.д.) — исключение.

Параметры вызова:
- content (строка): всегда передаётся как текст в JSON. Содержимое зависит от content_mode.
- original_name (строка): имя файла с расширением, например report.docx или data.xlsx.
  Расширение обязательно — по нему выбирается формат результата. Без точки и расширения вызов завершится ошибкой.
- content_mode (строка, по умолчанию auto): как интерпретировать content.
  • auto — для строки платформа сама определяет: markdown, base64 или обычный текст.
    Бинарник через этот tool: закодируй в base64 в content и поставь content_mode=base64.
  • markdown — content трактуется как Markdown (GFM): заголовки, списки, **жирный**, ссылки, таблицы с |.
  • base64 — content — одна строка base64 (без переносов); декодируется в байты и кладётся в файл как есть (тип по расширению).
  • raw — content кодируется в UTF-8 и записывается в файл как есть (для .md/.txt и т.п.).

Формат результата по расширению original_name (режим markdown или auto с распознанным markdown):
- .md — текст Markdown как файл.
- .txt — обычный текст.
- .html — HTML с разметкой из Markdown; встроенные по URL изображения (синтаксис картинки в Markdown с https-ссылкой) подтягиваются и вставляются.
- .pdf — PDF-документ из Markdown (таблицы |...|, абзацы, встроенные по URL картинки).
- .docx — Word из Markdown (таблицы и картинки по URL).
- .xlsx — таблица Excel: GFM-таблицы из Markdown становятся листами/ячейками; картинки по возможности вставляются.

Картинки в Markdown: стандартный синтаксис «восклицательный знак, квадратные скобки с alt, круглые скобки с https- или http-URL».
Пример заполнения круглых скобок: публичный URL вида `https://хост/путь/к файлу.png`. По такой ссылке файл скачивается и вставляется в html/pdf/docx/xlsx. Локальные пути без URL не подставляются.

Примеры JSON-аргументов для вызова tool:
1) Отчёт в Word из Markdown:
   {"content": "# Итог\\n\\n- пункт 1\\n- пункт 2\\n\\n| Кол1 | Кол2 |\\n| --- | --- |\\n| a | b |", "original_name": "otchet.docx", "content_mode": "markdown"}
2) Простой текстовый файл:
   {"content": "Строка1\\nСтрока2", "original_name": "notes.txt", "content_mode": "raw"}
3) То же через auto (если текст не похож на base64):
   {"content": "# Заголовок\\n\\nТекст", "original_name": "page.html", "content_mode": "auto"}
4) Положить уже закодированные байты (например готовый маленький бинарник в base64):
   {"content": "UEsDBBQAAAAIA...", "original_name": "dump.bin", "content_mode": "base64"}

Когда выбирать этот tool: пользователь просит сформировать файл (отчёт, таблицу, PDF, HTML, docx) и получить ссылку.
После успеха сообщи пользователю url или file_id из ответа.
""".strip()


class CreateFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(
        ...,
        description="Содержимое файла в зависимости от content_mode; подробности — в описании тула create_file.",
    )
    original_name: str = Field(
        ...,
        min_length=1,
        description="Имя файла с расширением (например report.docx); расширение обязательно.",
    )
    content_mode: Literal["auto", "markdown", "base64", "raw"] = Field(
        "auto",
        description="auto — автоопределение; markdown — GFM; base64 — бинарные байты строкой; raw — UTF-8 текст.",
    )


def _resolve_file_refs_for_read(
    state: ExecutionState,
    names: list[str],
) -> tuple[list[FileRef], list[FileResult]]:
    """Разрешает имена в FileRefs. Возвращает (найденные, ошибки для ненайденных)."""
    all_files = state.files
    file_refs: list[FileRef] = []
    errors: list[FileResult] = []
    for name in names:
        finfo = find_file(all_files, name)
        if finfo is None:
            errors.append(
                FileResult(
                    file_name=name,
                    success=False,
                    error=f"Файл '{name}' не найден. Доступные: {[file_ref.original_name for file_ref in all_files]}",
                    kind=FileReadKind.UNKNOWN,
                    read_lane=ReadLane.TEXT,
                    page_layout=PageLayout(kind=PageLayoutKind.VIRTUAL, page_size=0, pages_total=0),
                    pages_total=0,
                    stop_reason=StopReason.ERROR,
                    continuation=Continuation(),
                )
            )
        else:
            file_refs.append(finfo)
    return file_refs, errors


@tool(
    name="read_file",
    description=(
        "Читает вложения из state.files по списку имён names. "
        "Передаёшь список original_name — tool находит объекты файлов в state "
        "и вызывает движок чтения. Если names не указан, берутся все файлы в state.files. "
        "Vision/OCR — только если текст единицы layout непригоден."
    ),
    tags=["files"],
    parameters_model=ReadFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def read_file(
    names: list[str] | None = None,
    page_start: int = 0,
    page_end: int = -1,
    page_summarizations: bool = False,
    summarization_prompt: str = "",
    summarization_model: str = "",
    vision_prompt: str = "",
    vision_model: str | None = None,
    compression: CompressionMode | None = None,
    transcription_company_id: str | None = None,
    forced_lane: ReadLane | None = None,
    persist_assets_namespace: str | None = None,
    budget: int = MAX_READ_BUDGET,
    *,
    state: ExecutionState,
) -> JsonObject:
    all_files = state.files
    if not all_files:
        raise ValueError("No files to read")

    if names:
        file_refs, errors = _resolve_file_refs_for_read(state, names)
        args = ReadFileArgs(
            names=names,
            page_start=page_start,
            page_end=page_end,
            page_summarizations=page_summarizations,
            summarization_prompt=summarization_prompt,
            summarization_model=summarization_model,
            vision_prompt=vision_prompt,
            vision_model=vision_model,
            compression=compression if compression is not None else CompressionMode.NEVER,
            transcription_company_id=transcription_company_id,
            forced_lane=forced_lane,
            persist_assets_namespace=persist_assets_namespace,
            budget=budget,
        )
    else:
        file_refs = list(all_files)
        errors = []
        taken_names = [file_ref.original_name for file_ref in file_refs]
        args = ReadFileArgs(
            names=taken_names,
            page_start=page_start,
            page_end=page_end,
            page_summarizations=page_summarizations,
            summarization_prompt=summarization_prompt,
            summarization_model=summarization_model,
            vision_prompt=vision_prompt,
            vision_model=vision_model,
            compression=compression if compression is not None else CompressionMode.NEVER,
            transcription_company_id=transcription_company_id,
            forced_lane=forced_lane,
            persist_assets_namespace=persist_assets_namespace,
            budget=budget,
        )

    if not file_refs and errors:
        raise ValueError(
            "; ".join(
                err.error if err.error else f"File '{err.file_name}' not found"
                for err in errors
            )
        )
    if not file_refs:
        raise ValueError("No files to read")

    envelope = await read_files_to_envelope(file_refs, args, tool_name="read_file")
    if errors:
        envelope = envelope.model_copy(
            update={
                "files": errors + envelope.files,
                "files_processed": envelope.files_processed + len(errors),
            }
        )

    return require_json_object(envelope.model_dump(mode="json"), "read_file.result")


@tool(
    name="create_file",
    description=_CREATE_FILE_TOOL_DESCRIPTION,
    tags=["files"],
    parameters_model=CreateFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def create_file(
    content: str,
    original_name: str,
    content_mode: Literal["auto", "markdown", "base64", "raw"] = "auto",
    *,
    state: ExecutionState,
) -> JsonObject:
    """Создаёт файл в хранилище. Подробное описание и примеры JSON — в description tool (см. _CREATE_FILE_TOOL_DESCRIPTION)."""
    writer = FileWriter()
    record = await writer.write(
        content=content,
        original_name=original_name,
        content_mode=content_mode,
        public=True,
    )

    file_item = stored_file_ref(record)
    payload = require_json_object(file_item.model_dump(mode="json"), "create_file.response")
    upsert_state_file(state, file_item)
    _ = show_files(state, [file_item])
    return payload
