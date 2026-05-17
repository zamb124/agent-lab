"""
Tool: заполнение DOCX-шаблона через DocxTemplater (поиск file_info как у read_file).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from core.files.docx_template import DocxTemplater
from core.files.models import FileResponse
from core.state import ExecutionState

JsonDict = dict[str, Any]

_FILL_DOCX_DESCRIPTION = """
Заполняет шаблон Word (.docx) с плейсхолдерами Jinja2 (docxtpl: {{ var }}, вложенные {{ a.b }}, {% if %}…{% else %}…{% endif %}, {% for x in items %}…{% endfor %}, фильтры {{ name|upper }} и т.д.).

Образец шаблона со всеми конструкциями в открытом виде (скачайте, откройте в Word — в тексте видны все теги):
- Относительный путь от корня сервиса flows (с тем же origin, что у пользователя): `/static/examples/docx_templater_reference.docx`
- Полный `https?://...` — только если известен публичный origin (конфиг `server.flows_service_url` / прокси); в ответах пользователю отдавай **каноничный** результат инструмента: поле `url` (путь вида `/flows/api/v1/files/download/{file_id}`) без выдуманного `localhost`.
- В репозитории платформы: apps/flows/static/examples/docx_templater_reference.docx
Внутри файла есть готовая строка JSON для variables (раздел «Пример variables») и пояснение про strict.

Рабочий шаблон для вызова tool — одна запись из state.files (как у read_file): загрузите свой .docx во вложение или прикрепите к ноде.

Параметры:
- variables (объект): данные для подстановки. Строки, числа, bool, null, вложенные объекты и массивы;
  даты как строки в ISO; в inline-коде допускаются date/datetime/Decimal (см. DocxTemplater, date_iso).
- output_original_name: имя результата с расширением .docx (обязательно).
  Ключ должен быть СТРОГО `output_original_name` (snake_case, через `_`, без пробелов).
- file_name: имя шаблона как в state.files[].name (как у read_file); если не указано — последний файл .docx в state.files.
- strict: если true — в variables должны быть ровно все переменные верхнего уровня из шаблона, без лишних ключей.

Ожидается JSON-объект аргументов только с ключами:
`variables`, `output_original_name`, `file_name`, `strict`.
Передача любых других ключей недопустима.

Успех: success=true, file_id, url, original_name, content_type, file_size, checksum (если есть), is_public.
Ошибка: success=false, error (текст), при сбое шаблона также code из платформы.
""".strip()


def _fill_docx_mock(args: JsonDict, state: Any = None) -> JsonDict:
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
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "variables": {"full_name": "Иванов Иван Иванович"},
                    "output_original_name": "Договор_стажировки.docx",
                    "file_name": "internship_contract_ru.docx",
                    "strict": False,
                }
            ]
        },
    )

    variables: dict[str, Any] = Field(
        ...,
        description=(
            "Данные для Jinja2 в шаблоне: строки, числа, bool, null, вложенные объекты и массивы; "
            "даты — ISO-строки."
        ),
    )
    output_original_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Имя итогового файла с расширением .docx. "
            "Имя ключа аргумента должно быть строго output_original_name "
            "(snake_case, без пробелов)."
        ),
    )
    file_name: str | None = Field(
        None,
        description="Имя шаблона в state.files; не указано — последний .docx из вложений.",
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
    variables: dict[str, Any],
    output_original_name: str,
    file_name: str | None = None,
    strict: bool = False,
    *,
    state: ExecutionState,
) -> JsonDict:
    def _normalize_file_name(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.strip("`'\"")

    def _pick_file(entries: list[JsonDict], name: str | None) -> JsonDict | None:
        if not entries:
            return None
        normalized_name = _normalize_file_name(name)
        if not normalized_name:
            return entries[-1]
        for f in entries:
            if f.get("name") == normalized_name:
                return f
        name_lower = normalized_name.lower()
        for f in entries:
            if name_lower in (f.get("name") or "").lower():
                return f
        return None

    files = state.files
    if not files:
        if file_name:
            return {
                "success": False,
                "error": (
                    f"state.files пуст: вложение {file_name!r} недоступно. "
                    "Сначала пользователь должен прикрепить .docx к сообщению в канале."
                ),
            }
        return {
            "success": False,
            "error": "state.files пуст: прикрепите шаблон .docx к сообщению, затем вызовите fill_docx_template.",
        }

    docx_entries = [
        f
        for f in files
        if isinstance(f, dict)
        and (f.get("name") or "").lower().endswith(".docx")
    ]
    normalized_file_name = _normalize_file_name(file_name)
    if normalized_file_name:
        finfo = _pick_file(files, normalized_file_name)
    else:
        finfo = docx_entries[-1] if docx_entries else None

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
    except Exception as exc:
        exc_type_name = getattr(type(exc), "__name__", "")
        if exc_type_name == "FileWriteError":
            return {"success": False, "error": str(exc)}
        if exc_type_name.startswith("DocxTemplate") and exc_type_name.endswith("Error"):
            return {
                "success": False,
                "error": getattr(exc, "message", str(exc)),
                "code": getattr(exc, "code", "DOCX_TEMPLATE_ERROR"),
                "payload": getattr(exc, "payload", None) or {},
            }
        raise

    response = FileResponse.from_record(record)
    return {"success": True, **response.model_dump(mode="json")}


__all__ = ["fill_docx_template"]
