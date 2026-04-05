"""
Тулы для работы с файлами в flow (вложения state.files).

Сейчас: read_file. Сюда же добавляются создание файлов и прочие file-операции.
"""

from typing import Any, Dict, List, Optional

from apps.flows.src.tools import tool
from core.files.reader import FileReadError, FileReader, ReadOptions
from core.files.reader.models import FileReadKind, FileReadResult, ReadPage


def _find_file(files: List[Dict[str, Any]], name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not files:
        return None
    if not name:
        return files[0]
    for f in files:
        if f.get("name") == name:
            return f
    name_lower = name.lower()
    for f in files:
        if name_lower in (f.get("name") or "").lower():
            return f
    return None


def _read_file_mock(args: dict, state: Any = None) -> dict:
    from pathlib import Path

    file_name_arg = args.get("file_name")
    if state is not None:
        files = getattr(state, "files", None)
        if files is None and isinstance(state, dict):
            files = state.get("files", [])
        files = files or []
        if not files:
            return {"success": False, "error": "Нет файлов для чтения"}
        finfo = _find_file(files, file_name_arg)
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


@tool(
    name="read_file",
    description=(
        "Читает прикреплённый файл и возвращает структурированный результат (страницы, текст, checksum). "
        "file_name — имя файла из state.files; если не указано, берётся первый файл. "
        "include_asset_bytes — включать base64 вложений (тяжёлый ответ, по умолчанию false)."
    ),
    tags=["files", "ocr", "document"],
    mock_response=_read_file_mock,
)
async def read_file(
    file_name: Optional[str] = None,
    include_asset_bytes: bool = False,
    state: Optional[dict] = None,
) -> dict:
    state = state or {}
    files = state.get("files", [])
    if not files:
        return {"success": False, "error": "Нет файлов для чтения"}

    finfo = _find_file(files, file_name)
    if finfo is None:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[f.get('name') for f in files]}",
        }

    path = finfo.get("path")
    if not path:
        return {"success": False, "error": "У файла нет path"}

    opts = ReadOptions(
        include_asset_bytes=include_asset_bytes,
        source_file_id=finfo.get("file_id"),
    )
    reader = FileReader()
    try:
        result = await reader.read(
            source=path,
            file_name=finfo.get("name"),
            options=opts,
        )
    except FileReadError as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, **result.model_dump(mode="json")}
