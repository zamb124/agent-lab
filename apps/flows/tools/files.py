"""
Тулы для работы с файлами в flow (вложения state.files).

read_file — чтение вложений; create_file — FileWriter() + create_file (процесс настроен через FileWriter.configure_process_upload при старте).
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.files.models import FileResponse
from core.files.reader import FileReader, FileReadError
from core.files.reader.models import FileReadKind, FileReadResult, ReadPage
from core.files.writer import FileWriteError, FileWriter
from core.state import ExecutionState

JsonDict = dict[str, Any]

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


def _read_file_mock(args: JsonDict, state: Any = None) -> JsonDict:
    def _pick(entries: list[JsonDict], name: Any) -> JsonDict | None:
        if not entries:
            return None
        if not name:
            return entries[-1]
        for f in entries:
            if f.get("name") == name:
                return f
        nl = name.lower()
        for f in entries:
            if nl in (f.get("name") or "").lower():
                return f
        return None

    file_name_arg = args.get("file_name")
    if state is not None:
        files = getattr(state, "files", None)
        if files is None and isinstance(state, dict):
            files = state.get("files", [])
        files = files or []
        if not files:
            return {"success": False, "error": "Нет файлов для чтения"}
        finfo = _pick(files, file_name_arg)
        if finfo is None:
            return {
                "success": False,
                "error": f"Файл не найден. Доступные: {[f.get('name') for f in files]}",
            }
        path = finfo.get("path")
        if path and not Path(path).exists():
            return {"success": False, "error": f"Файл не найден: {path}"}
        res = FileReadResult(
            file_name=finfo.get("name", "file"),
            mime_type=finfo.get("mime_type"),
            detected_kind=FileReadKind.TEXT,
            page_count=1,
            pages=[ReadPage(index=0, text="Mock read_file content", assets=[], label=None)],
            warnings=[],
            source_file_id=finfo.get("file_id"),
        )
        return {"success": True, **res.model_dump(mode="json")}
    res = FileReadResult(
        file_name=file_name_arg or "mock",
        mime_type="text/plain",
        detected_kind=FileReadKind.TEXT,
        page_count=1,
        pages=[ReadPage(index=0, text="Mock read_file without state", assets=[], label=None)],
        warnings=[],
    )
    return {"success": True, **res.model_dump(mode="json")}


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_name: str | None = Field(
        None,
        description="Имя вложения как в state.files[].name; не передавай — будет взято последнее вложение в списке (обычно последняя загрузка пользователя).",
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
        "Читает вложение из state.files. Передаёшь file_name (как в записи name) — tool сам находит объект файла в state "
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
    def _pick_file(files_list: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
        if not files_list:
            return None
        if not name:
            return files_list[-1]
        for f in files_list:
            if f.get("name") == name:
                return f
        name_lower = name.lower()
        for f in files_list:
            if name_lower in (f.get("name") or "").lower():
                return f
        return None

    files = state.files
    if not files:
        return {"success": False, "error": "Нет файлов для чтения"}

    finfo = _pick_file(files, file_name)
    if finfo is None:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[f.get('name') for f in files]}",
        }

    reader = FileReader()
    try:
        result = await reader.read(
            finfo,
            include_asset_bytes=include_asset_bytes,
            vision_prompt=vision_prompt,
        )
    except FileReadError as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, **result.model_dump(mode="json")}


def _create_file_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {
        "success": True,
        "file_id": "file_mockcreate01",
        "original_name": args.get("original_name") or "out.md",
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
    return {"success": True, **response.model_dump(mode="json")}
