"""
Tool: заполнение DOCX-шаблона через DocxTemplater (поиск file_info как у read_file).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools import tool
from core.files import DocxTemplateError, DocxTemplater
from core.files.models import FileResponse
from core.files.writer import FileWriteError

_FILL_DOCX_DESCRIPTION = """
Заполняет шаблон Word (.docx) с плейсхолдерами Jinja2 (docxtpl: {{ var }}, вложенные {{ a.b }}, {% if %}…{% else %}…{% endif %}, {% for x in items %}…{% endfor %}, фильтры {{ name|upper }} и т.д.).

Образец шаблона со всеми конструкциями в открытом виде (скачайте, откройте в Word — в тексте видны все теги):
- HTTP (тот же хост и порт, что у API сервиса flows; путь от корня HTTP-приложения flows, без /flows/api):
  http://localhost:8001/static/examples/docx_templater_reference.docx
  (локально при make app порт flows по умолчанию 8001; в проде подставьте свой origin, например из server.flows_service_url в конфиге.)
- Относительный путь: /static/examples/docx_templater_reference.docx
- В репозитории платформы: apps/flows/static/examples/docx_templater_reference.docx
Внутри файла есть готовая строка JSON для variables (раздел «Пример variables») и пояснение про strict.

Рабочий шаблон для вызова tool — одна запись из state.files (как у read_file): загрузите свой .docx во вложение или прикрепите к ноде.

Параметры:
- variables (объект): данные для подстановки. Строки, числа, bool, null, вложенные объекты и массивы;
  даты как строки в ISO; в inline-коде допускаются date/datetime/Decimal (см. DocxTemplater, date_iso).
- output_original_name: имя результата с расширением .docx (обязательно).
- file_name: имя шаблона как в state.files[].name (как у read_file); если не указано — первый файл .docx в state.files.
- strict: если true — в variables должны быть ровно все переменные верхнего уровня из шаблона, без лишних ключей.

Успех: success=true, file_id, url, original_name, content_type, file_size, checksum (если есть), is_public.
Ошибка: success=false, error (текст), при сбое шаблона также code из платформы.
""".strip()


def _fill_docx_mock(args: dict, state: Any = None) -> dict:
    return {
        "success": True,
        "file_id": "file_mockdocx01",
        "original_name": args.get("output_original_name") or "out.docx",
        "content_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "file_size": 100,
        "url": "/flows/api/v1/files/download/file_mockdocx01",
        "checksum": None,
        "is_public": True,
    }


class FillDocxTemplateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variables: Dict[str, Any] = Field(
        ...,
        description="Данные для Jinja2 в шаблоне: строки, числа, bool, вложенные объекты и массивы; даты — ISO-строки.",
    )
    output_original_name: str = Field(
        ...,
        min_length=1,
        description="Имя итогового файла с расширением .docx.",
    )
    file_name: Optional[str] = Field(
        None,
        description="Имя шаблона в state.files; не указано — первый .docx из вложений.",
    )
    strict: bool = Field(
        False,
        description="Если true — в variables ровно набор переменных шаблона верхнего уровня, без лишних ключей.",
    )


@tool(
    name="fill_docx_template",
    description=_FILL_DOCX_DESCRIPTION,
    tags=["files", "docx", "template"],
    mock_response=_fill_docx_mock,
    args_schema=FillDocxTemplateArgs,
)
async def fill_docx_template(
    variables: Dict[str, Any],
    output_original_name: str,
    file_name: Optional[str] = None,
    strict: bool = False,
    state: Optional[dict] = None,
) -> dict:
    def _pick_file(entries, name):
        if not entries:
            return None
        if not name:
            return entries[0]
        for f in entries:
            if f.get("name") == name:
                return f
        name_lower = name.lower()
        for f in entries:
            if name_lower in (f.get("name") or "").lower():
                return f
        return None

    state = state or {}
    files = state.get("files", [])
    if not files:
        return {"success": False, "error": "Нет файлов для чтения"}

    docx_entries = [
        f
        for f in files
        if isinstance(f, dict)
        and (f.get("name") or "").lower().endswith(".docx")
    ]
    if file_name:
        finfo = _pick_file(files, file_name)
    else:
        finfo = docx_entries[0] if docx_entries else None

    if finfo is None:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[f.get('name') for f in files]}",
        }

    n = finfo.get("name") or ""
    if not n.lower().endswith(".docx"):
        return {
            "success": False,
            "error": f"Шаблон должен быть .docx, получено: {n!r}",
        }

    try:
        record = await DocxTemplater().fill_and_create(
            file_ref=finfo,
            context=variables,
            output_original_name=output_original_name,
            strict=strict,
        )
    except DocxTemplateError as exc:
        return {
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "payload": exc.payload,
        }
    except FileWriteError as exc:
        return {"success": False, "error": str(exc)}

    response = FileResponse.from_record(record)
    return {"success": True, **response.model_dump(mode="json")}


__all__ = ["fill_docx_template"]
