"""
Нормализация контекста для Jinja2/docxtpl: только данные, без вызываемых объектов.

RichText, InlineImage и аналоги docxtpl пропускаются как есть (доверенный шаблон + сборка контекста вызывающим кодом).
"""

from __future__ import annotations

import datetime
import decimal
from collections.abc import Mapping
from enum import Enum
from typing import Any

from docxtpl import InlineImage, RichText

from core.files.docx_template.exceptions import DocxTemplateContextError

_PASSTHROUGH_TYPES: tuple[type[Any], ...] = (RichText, InlineImage)

_ALLOWED_SCALAR_TYPES: tuple[type[Any], ...] = (
    str,
    int,
    float,
    bool,
    type(None),
)


def _fail(path: str, msg: str) -> None:
    raise DocxTemplateContextError(
        f"Контекст шаблона: {msg} (путь: {path})",
    )


def normalize_template_context(
    context: Mapping[str, Any],
    *,
    date_iso: bool = True,
    _path: str = "$",
    _seen: set[int] | None = None,
) -> dict[str, Any]:
    """
    Рекурсивно приводит значения к JSON-подобному виду для Jinja.
    """
    if _seen is None:
        _seen = set()
    if not isinstance(context, Mapping):
        _fail(_path, "корень контекста должен быть объектом (mapping)")

    result: dict[str, Any] = {}
    for key, raw in context.items():
        if not isinstance(key, str):
            _fail(_path, "ключи контекста должны быть строками")
        sub = f"{_path}.{key}" if _path != "$" else f"$.{key}"
        result[key] = _normalize_value(
            raw, date_iso=date_iso, path=sub, _seen=_seen
        )
    return result


def _normalize_value(
    value: Any,
    *,
    date_iso: bool,
    path: str,
    _seen: set[int],
) -> Any:
    if value is None or isinstance(value, _ALLOWED_SCALAR_TYPES):
        return value

    if isinstance(value, _PASSTHROUGH_TYPES):
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

    if isinstance(value, Enum):
        return value.value

    oid = id(value)
    if oid in _seen:
        _fail(path, "циклическая ссылка в контексте")
    _seen.add(oid)
    try:
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if not isinstance(k, str):
                    _fail(path, "ключи вложенного объекта должны быть строками")
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

    if callable(value):
        _fail(path, "значения-функции запрещены")

    _fail(path, f"неподдерживаемый тип: {type(value).__name__}")


__all__ = ["normalize_template_context"]
