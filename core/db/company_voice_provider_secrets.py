"""Слияние и санитизация JSONB secrets для таблицы `company_voice_providers`."""

from __future__ import annotations

from typing import Any

_UNSET_MARKER = object()


def unset_secrets_sentinel() -> object:
    """Маркер: поле secrets в теле PUT не передано — колонка не меняется."""
    return _UNSET_MARKER


def is_unset_sentinel(obj: object) -> bool:
    return obj is _UNSET_MARKER


def merge_secrets(
    *,
    existing: dict[str, Any] | None,
    patch: dict[str, str | None] | None,
    allowed_keys: frozenset[str],
) -> dict[str, str]:
    """Слить patch в existing (только allowed_keys).

    Отсутствующий ключ в patch не трогает existing.
    ``None`` или пустая строка в значении patch удаляет ключ из результата.
    """
    for k in patch or {}:
        if k not in allowed_keys:
            raise ValueError(f"Неизвестный ключ secrets для провайдера: {k!r}")
    base: dict[str, str] = {}
    if existing:
        for k, v in existing.items():
            if k in allowed_keys and isinstance(v, str) and v != "":
                base[k] = v
    changed = patch or {}
    for k in allowed_keys.intersection(changed.keys()):
        v = changed[k]
        if v is None or v == "":
            base.pop(k, None)
        elif isinstance(v, str):
            base[k] = v
        else:
            raise ValueError(f"secrets[{k}] ожидалась строка или null, получено: {type(v).__name__}")
    return base
