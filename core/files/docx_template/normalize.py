"""
Нормализация контекста для Jinja2/docxtpl: только данные, без вызываемых объектов.
"""

from __future__ import annotations

import datetime
import decimal
from collections.abc import Mapping

from core.files.docx_template.exceptions import DocxTemplateContextError
from core.types import DocxTemplateContext, DocxTemplateContextValue, JsonObject, JsonValue


def _fail(path: str, msg: str) -> None:
    raise DocxTemplateContextError(
        f"Контекст шаблона: {msg} (путь: {path})",
    )


def normalize_template_context(
    context: DocxTemplateContext,
    *,
    date_iso: bool = True,
    _path: str = "$",
    _seen: set[int] | None = None,
) -> JsonObject:
    """
    Рекурсивно приводит значения к JSON-подобному виду для Jinja.
    """
    if _seen is None:
        _seen = set()

    result: JsonObject = {}
    for key, raw in context.items():
        sub = f"{_path}.{key}" if _path != "$" else f"$.{key}"
        result[key] = _normalize_value(
            raw, date_iso=date_iso, path=sub, _seen=_seen
        )
    return result


def _normalize_value(
    value: DocxTemplateContextValue,
    *,
    date_iso: bool,
    path: str,
    _seen: set[int],
) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, datetime.datetime):
        if date_iso:
            return value.isoformat()
        return str(value)

    if isinstance(value, datetime.date):
        if date_iso:
            return value.isoformat()
        return str(value)

    if isinstance(value, decimal.Decimal):
        return str(value)

    oid = id(value)
    if oid in _seen:
        _fail(path, "циклическая ссылка в контексте")
    _seen.add(oid)
    try:
        if isinstance(value, Mapping):
            out: JsonObject = {}
            for k, v in value.items():
                out[k] = _normalize_value(
                    v, date_iso=date_iso, path=f"{path}.{k}", _seen=_seen
                )
            return out

        if isinstance(value, (list, tuple)):
            return [
                _normalize_value(
                    item, date_iso=date_iso, path=f"{path}[{i}]", _seen=_seen
                )
                for i, item in enumerate(value)
            ]
    finally:
        _seen.discard(oid)

    _fail(path, f"неподдерживаемый тип: {type(value).__name__}")


__all__ = ["normalize_template_context"]
