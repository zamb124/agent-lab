"""
Tool: заполнение DOCX-шаблона через DocxTemplater (поиск file_info как у read_file).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.runtime_helpers.state_utils import find_file, normalize_file_lookup_name
from apps.flows.src.tools.decorator import tool
from core.files.docx_template import DocxTemplateError, DocxTemplater
from core.files.models import FileResponse
from core.files.writer import FileWriteError
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

JsonDict = JsonObject

_FILL_DOCX_DESCRIPTION = """
Заполняет шаблон Word (.docx) с плейсхолдерами Jinja2 (docxtpl: {{ var }}, вложенные {{ a.b }}, {% if %}…{% else %}…{% endif %}, {% for x in items %}…{% endfor %}, фильтры {{ name|upper }} и т.д.).

Образец шаблона со всеми конструкциями в открытом виде (скачайте, откройте в Word — в тексте видны все теги):
- Относительный путь от корня сервиса flows (с тем же origin, что у пользователя): `/static/examples/docx_templater_reference.docx`
- Полный `https?://...` — только если известен публичный origin (конфиг `server.flows_service_url` / прокси); в ответах пользователю отдавай **каноничный** результат инструмента: поле `url` (путь вида `/frontend/api/v1/files/download/{file_id}`) без выдуманного `localhost`.
- В репозитории платформы: apps/flows/static/examples/docx_templater_reference.docx
Внутри файла есть готовая строка JSON для variables (раздел «Пример variables») и пояснение про strict.

Рабочий шаблон для вызова tool — одна запись из state.files (как у read_file): загрузите свой .docx во вложение или прикрепите к ноде.

Параметры:
- variables (объект): данные для подстановки. Строки, числа, bool, null, вложенные объекты и массивы;
  даты как строки в ISO; в inline-коде допускаются date/datetime/Decimal (см. DocxTemplater, date_iso).
- output_original_name: имя результата с расширением .docx (обязательно).
  Ключ должен быть СТРОГО `output_original_name` (snake_case, через `_`, без пробелов).
- file_name: имя шаблона как в state.files[].original_name (как у read_file); если не указано — последний файл .docx в state.files.
- strict: если true — в variables должны быть ровно все переменные верхнего уровня из шаблона, без лишних ключей.

Ожидается JSON-объект аргументов только с ключами:
`variables`, `output_original_name`, `file_name`, `strict`.
Передача любых других ключей недопустима.

Успех: success=true, file_id, url, original_name, content_type, file_size, checksum (если есть), is_public.
Ошибка: success=false, error (текст), при сбое шаблона также code из платформы.
""".strip()


class FillDocxTemplateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
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

    variables: JsonObject = Field(
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
    parameters_model=FillDocxTemplateArgs,
)
async def fill_docx_template(
    variables: JsonObject,
    output_original_name: str,
    file_name: str | None = None,
    strict: bool = False,
    *,
    state: ExecutionState,
) -> JsonDict:
    def _normalize_file_name(value: str | None) -> str | None:
        normalized = normalize_file_lookup_name(value)
        if not normalized:
            return None
        return normalized

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
        file_ref
        for file_ref in files
        if file_ref.original_name.lower().endswith(".docx")
    ]
    normalized_file_name = _normalize_file_name(file_name)
    if normalized_file_name:
        finfo = find_file(files, normalized_file_name)
    else:
        finfo = docx_entries[-1] if docx_entries else None

    if finfo is None:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}",
        }

    if not finfo.original_name.lower().endswith(".docx"):
        return {
            "success": False,
            "error": f"Шаблон должен быть .docx, получено: {finfo.original_name!r}",
        }

    try:
        record = await DocxTemplater().fill_and_create(
            file_ref=finfo,
            context=variables,
            output_original_name=output_original_name,
            strict=strict,
        )
    except FileWriteError as exc:
        return {"success": False, "error": str(exc)}
    except DocxTemplateError as exc:
        return {
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "payload": exc.payload,
        }

    response = FileResponse.from_record(record)
    return {
        "success": True,
        **require_json_object(response.model_dump(mode="json"), "fill_docx_template.response"),
    }


__all__ = ["fill_docx_template"]
