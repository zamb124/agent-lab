"""
Тулы для работы с файлами в flow (вложения state.files).

read_file — чтение вложений; create_file — FileWriter() + create_file (процесс настроен через FileWriter.configure_process_upload при старте).
"""

import re
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.files.state_file_refs import upsert_state_file, with_document_capability
from apps.flows.src.runtime_helpers.state_utils import find_file, push_ui_event
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient, ServiceClientError
from core.context import get_context
from core.files.file_ref import FileRef
from core.files.models import FileResponse
from core.files.reader import FileReader, FileReadError
from core.files.reader.models import FileReadKind, FileReadResult, ReadPage
from core.files.writer import FileWriteError, FileWriter
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

JsonDict = JsonObject
OFFICE_EXT_RE = r"\.(docx?|odt|rtf|txt|pdf|xlsx?|ods|csv|pptx?|odp)$"
OFFICE_MIME_RE = r"(pdf|word|excel|spreadsheet|presentation|powerpoint|officedocument|opendocument|text/csv|text/plain)"


def _context_namespace() -> str:
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    ns = (ctx.active_namespace or "default").strip()
    return ns or "default"


def _is_office_file(item: FileRef) -> bool:
    original_name = item.original_name.lower()
    content_type = item.content_type.lower()
    return re.search(OFFICE_EXT_RE, original_name) is not None or re.search(OFFICE_MIME_RE, content_type) is not None


async def _sync_office_file_before_read(state: ExecutionState, item: FileRef) -> tuple[FileRef, str | None]:
    if item.file_id is None or not _is_office_file(item):
        return item, None

    namespace = _context_namespace()
    document = item.capabilities.document

    if document is not None:
        raw = require_json_object(
            document.model_dump(mode="json", exclude_none=True),
            "FileRef.capabilities.document",
        )
    else:
        try:
            candidate = await ServiceClient().post(
                "office",
                "/documents/api/v1/documents/from-file",
                json={"file_id": item.file_id, "title": item.original_name},
                headers={NAMESPACE_HEADER: namespace},
            )
        except ServiceClientError:
            return item, None
        raw = require_json_object(candidate, "office.documents.from_file")

    binding_id_value = raw["binding_id"]
    if not isinstance(binding_id_value, str) or not binding_id_value.strip():
        raise ValueError("office.documents.binding_id must be a non-empty string")
    binding_id = binding_id_value
    try:
        synced = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{quote(binding_id, safe='')}/sync",
            headers={NAMESPACE_HEADER: namespace},
            timeout=30.0,
        )
    except ServiceClientError as exc:
        return item, f"Не удалось синхронизировать открытый редактор documents перед чтением: {exc}"
    synced_payload = require_json_object(synced, "office.documents.sync")
    raw = {**raw, **synced_payload}

    enriched = with_document_capability(item, raw, namespace)
    upsert_state_file(state, enriched)
    _ = push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched.to_json_object()]},
        source="documents",
        correlation_id=binding_id,
    )
    return enriched, None

_CREATE_FILE_TOOL_DESCRIPTION = """
Создаёт файл в хранилище платформы и возвращает ссылку на скачивание.

Ответ при успехе: success=true, file_id, url (путь для скачивания), original_name, content_type,
file_size, checksum (если есть), is_public.
Ответ при ошибке: success=false, error (текст причины: нет компании в контексте, неверный base64, нет расширения в имени и т.д.).

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


def _read_file_mock(args: JsonDict, state: ExecutionState | None = None) -> JsonDict:
    file_name_arg = args.get("file_name")
    if file_name_arg is not None and not isinstance(file_name_arg, str):
        raise ValueError("read_file.file_name must be a string")
    if state is not None:
        files = state.files
        if not files:
            return {"success": False, "error": "Нет файлов для чтения"}
        finfo = find_file(files, file_name_arg)
        if finfo is None:
            return {
                "success": False,
                "error": f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}",
            }
        url = finfo.url
        if url is not None and not url.startswith(("http://", "https://")) and not Path(url).exists():
            return {"success": False, "error": f"Файл не найден: {url}"}
        res = FileReadResult(
            file_name=finfo.original_name,
            content_type=finfo.content_type,
            detected_kind=FileReadKind.TEXT,
            page_count=1,
            pages=[ReadPage(index=0, text="Mock read_file content", assets=[], label=None)],
            warnings=[],
            source_file_id=finfo.file_id,
        )
        return {
            "success": True,
            **require_json_object(res.model_dump(mode="json"), "read_file.mock_result"),
        }
    res = FileReadResult(
        file_name=file_name_arg if file_name_arg is not None else "mock",
        content_type="text/plain",
        detected_kind=FileReadKind.TEXT,
        page_count=1,
        pages=[ReadPage(index=0, text="Mock read_file without state", assets=[], label=None)],
        warnings=[],
    )
    return {
        "success": True,
        **require_json_object(res.model_dump(mode="json"), "read_file.mock_result"),
    }


class ReadFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_name: str | None = Field(
        None,
        description="Имя вложения как в state.files[].original_name; не передавай — будет взято последнее вложение в списке (обычно последняя загрузка пользователя).",
    )
    include_asset_bytes: bool = Field(
        False,
        description="Включать ли картинки/вложения из PDF в ответ как base64 (увеличивает размер ответа).",
    )
    vision_prompt: str | None = Field(
        None,
        description="Для изображений: инструкция для vision-анализа содержимого.",
    )


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


@tool(
    name="read_file",
    description=(
        "Читает вложение из state.files. Передаёшь file_name (как в записи original_name) — tool сам находит объект файла в state "
        "и вызывает FileReader.read. Если file_name не указан, берётся последний файл в state.files (порядок: файлы нод графа, затем вложения по мере добавления в диалоге). "
        "include_asset_bytes — base64 вложений в ответе PDF (тяжело). "
        "vision_prompt — для картинок: инструкция vision-модели."
    ),
    tags=["files", "ocr", "document"],
    mock_response=_read_file_mock,
    args_schema=ReadFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def read_file(
    file_name: str | None = None,
    include_asset_bytes: bool = False,
    vision_prompt: str | None = None,
    *,
    state: ExecutionState,
) -> JsonDict:
    files = state.files
    if not files:
        return {"success": False, "error": "Нет файлов для чтения"}

    finfo = find_file(files, file_name)
    if finfo is None:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}",
        }

    finfo, sync_error = await _sync_office_file_before_read(state, finfo)
    if sync_error is not None:
        return {"success": False, "error": sync_error}

    reader = FileReader()
    try:
        result = await reader.read(
            finfo,
            include_asset_bytes=include_asset_bytes,
            vision_prompt=vision_prompt,
        )
    except FileReadError as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        **require_json_object(result.model_dump(mode="json"), "read_file.result"),
    }


def _create_file_mock(args: JsonDict, state: ExecutionState | None = None) -> JsonDict:
    _ = state
    original_name = args["original_name"]
    if not isinstance(original_name, str) or not original_name.strip():
        raise ValueError("create_file.original_name must be a non-empty string")
    return {
        "success": True,
        "file_id": "file_mockcreate01",
        "original_name": original_name,
        "content_type": "text/plain",
        "file_size": 1,
        "url": "/flows/api/v1/files/download/file_mockcreate01",
        "checksum": None,
        "is_public": True,
    }


@tool(
    name="create_file",
    description=_CREATE_FILE_TOOL_DESCRIPTION,
    tags=["files", "storage"],
    mock_response=_create_file_mock,
    args_schema=CreateFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def create_file(
    content: str,
    original_name: str,
    content_mode: Literal["auto", "markdown", "base64", "raw"] = "auto",
    *,
    state: ExecutionState,
) -> JsonDict:
    """Создаёт файл в хранилище. Подробное описание и примеры JSON — в description tool (см. _CREATE_FILE_TOOL_DESCRIPTION)."""
    writer = FileWriter()
    try:
        record = await writer.write(
            content=content,
            original_name=original_name,
            content_mode=content_mode,
            public=True,
        )
    except FileWriteError as exc:
        return {"success": False, "error": str(exc)}

    response = FileResponse.from_record(record)
    payload = require_json_object(response.model_dump(mode="json"), "create_file.response")
    file_item = FileRef.from_response(response)
    upsert_state_file(state, file_item)
    _ = push_ui_event(
        state,
        event_type="files.added",
        payload={"files": [file_item.to_json_object()]},
        source="files",
        correlation_id=response.file_id,
    )
    return {"success": True, **payload}
