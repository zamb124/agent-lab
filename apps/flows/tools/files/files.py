"""
Тулы для работы с файлами в flow (вложения state.files).

read_file — names → file_ids → capability files.read (HTTP gateway);
create_file — FileWriter() (процесс настроен через FileWriter.configure_process_upload при старте).
"""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.runners.capability_context import capability_execution_context
from apps.flows.src.services.flow_ui_cards import show_files
from apps.flows.src.state import ExecutionState
from apps.flows.src.state.state_utils import find_file
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.capabilities import CapabilityCallRequest
from core.clients.capability_gateway_client import CapabilityGatewayClient
from core.files.file_ref import FileRef, stored_file_ref
from core.files.image_region import materialize_image_regions
from core.files.reader.models import (
    MAX_NESTED_DEFAULT,
    MAX_READ_BUDGET,
    CompressionMode,
    Continuation,
    FileReadKind,
    FileResult,
    NestedMode,
    PageLayout,
    PageLayoutKind,
    ReadFileArgs,
    ReadFileEnvelope,
    ReadLane,
    StopReason,
)
from core.files.reader.service import FileReader
from core.files.writer import FileWriter
from core.models.base import StrictBaseModel
from core.types import JsonArray, JsonObject, require_json_array, require_json_object

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


def _upsert_nested_refs(state: ExecutionState, files: list[FileResult]) -> None:
    for file_result in files:
        for item in file_result.nested:
            if item.file_id is None or not item.file_id.strip():
                continue
            file_size = 0
            if item.bytes_b64 is not None and item.bytes_b64.strip():
                # приблизительный размер из base64; точный — после persist в FilesService
                file_size = max((len(item.bytes_b64) * 3) // 4, 0)
            upsert_state_file(
                state,
                FileRef(
                    file_id=item.file_id,
                    original_name=item.original_name,
                    content_type=item.content_type,
                    file_size=file_size,
                    checksum=item.checksum,
                ),
            )


def _read_file_capability_kwargs(args: ReadFileArgs, file_ids: list[str]) -> JsonObject:
    dumped = require_json_object(args.model_dump(mode="json"), "ReadFileArgs")
    _ = dumped.pop("names", None)
    dumped["file_ids"] = file_ids
    return dumped


@tool(
    name="read_file",
    description=(
        "Читает вложения из state.files по списку имён names. "
        "Результат страниц — markdown с якорями вложенного content. "
        "nested_mode=refs (default): nested → FileRef в state.files; "
        "nested_mode=parts: markdown + interleaved Image {anchor}: и Part(raw) в tool-result. "
        "page_summarizations=true: LLM-суммаризация страниц (текст + nested images multimodal). "
        "recursive=true (default, только refs): один уровень авто-read nested в окне; "
        "при parts recursive выключается. "
        "Vision/OCR страницы — если текст layout непригоден; nested OCR — recursive/parts. "
        "Исполнение — capability files.read через capability-gateway."
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
    nested_mode: NestedMode = NestedMode.REFS,
    recursive: bool = True,
    max_nested: int = MAX_NESTED_DEFAULT,
    *,
    state: ExecutionState,
) -> JsonObject:
    all_files = state.files
    if not all_files:
        raise ValueError("No files to read")

    resolved_compression = (
        compression if compression is not None else CompressionMode.NEVER
    )
    if names:
        file_refs, errors = _resolve_file_refs_for_read(state, names)
        resolved_names = names
    else:
        file_refs = list(all_files)
        errors = []
        resolved_names = [file_ref.original_name for file_ref in file_refs]

    args = ReadFileArgs(
        names=resolved_names,
        page_start=page_start,
        page_end=page_end,
        page_summarizations=page_summarizations,
        summarization_prompt=summarization_prompt,
        summarization_model=summarization_model,
        vision_prompt=vision_prompt,
        vision_model=vision_model,
        compression=resolved_compression,
        transcription_company_id=transcription_company_id,
        forced_lane=forced_lane,
        persist_assets_namespace=persist_assets_namespace,
        budget=budget,
        nested_mode=nested_mode,
        recursive=recursive,
        max_nested=max_nested,
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

    file_ids: list[str] = []
    for file_ref in file_refs:
        file_id = file_ref.file_id
        if file_id is None or not file_id.strip():
            raise ValueError(
                f"File {file_ref.original_name!r} has no file_id; "
                + "read_file requires persisted FileRef"
            )
        file_ids.append(file_id.strip())

    timeout = float(get_flows_settings().node_execution_wall_time_cap_seconds)
    execution_context = capability_execution_context(
        state,
        allowed_capabilities=["files.read"],
    )
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="files.read",
            kwargs=_read_file_capability_kwargs(args, file_ids),
        ),
        timeout=timeout,
    )
    if response.result is None:
        raise RuntimeError("files.read returned empty result")
    envelope = ReadFileEnvelope.model_validate(response.result)
    if errors:
        envelope = envelope.model_copy(
            update={
                "files": errors + envelope.files,
                "files_processed": envelope.files_processed + len(errors),
            }
        )

    _upsert_nested_refs(state, envelope.files)
    # bytes nested остаются в envelope для llm_runner → Part(raw); activity JSON strip'ится там.
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


class MaterializeImageRegionsArgs(StrictBaseModel):
    sections: JsonArray = Field(
        description=(
            "Список секций с photo-регионами: у каждой секции photo — "
            "{file_id, page, x0, y0, x1, y1} в нормализованных долях кадра, либо null."
        ),
    )
    attachment_file_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Разрешённые file_id вложений-источников. Crop только из этого списка; "
            "пустой список — ни один регион не материализуется."
        ),
    )


@tool(
    name="files_materialize_image_regions",
    description=(
        "Crop photo regions from attachments by normalized bbox "
        "(file_id, page, x0,y0,x1,y1 fractions) into separate ephemeral JPEG files. "
        "Returns sections with photo={file_id}; failed crops become photo=null."
    ),
    tags=["files"],
    parameters_model=MaterializeImageRegionsArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
    effects=["write"],
)
async def files_materialize_image_regions(
    *,
    state: ExecutionState,
    sections: JsonArray,
    attachment_file_ids: list[str] | None = None,
) -> JsonObject:
    _ = state
    _ = require_json_array(sections, "files_materialize_image_regions.sections")
    files_service = FileReader.require_files_service()
    ids = attachment_file_ids if attachment_file_ids is not None else []
    materialized = await materialize_image_regions(
        files_service,
        sections=sections,
        attachment_file_ids=list(ids),
    )
    return {"sections": materialized}
