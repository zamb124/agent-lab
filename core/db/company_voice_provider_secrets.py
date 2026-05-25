"""Слияние и санитизация JSONB secrets для таблицы `company_voice_providers`."""

from __future__ import annotations

from typing import ClassVar, Final, TypeIs


class UnsetSecretsSentinel:
    """Маркер отсутствующего поля secrets в PATCH/PUT."""

    __slots__: ClassVar[tuple[str, ...]] = ()


SecretsPatchValue = dict[str, str] | None | UnsetSecretsSentinel

_UNSET_MARKER = UnsetSecretsSentinel()
UNSET_SECRETS: Final[UnsetSecretsSentinel] = _UNSET_MARKER


def unset_secrets_sentinel() -> UnsetSecretsSentinel:
    """Маркер: поле secrets в теле PUT не передано — колонка не меняется."""
    return _UNSET_MARKER


def is_unset_sentinel(value: SecretsPatchValue) -> TypeIs[UnsetSecretsSentinel]:
    return value is _UNSET_MARKER


def merge_secrets(
    *,
    existing: dict[str, str] | None,
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
            if k in allowed_keys and v != "":
                base[k] = v
    changed = patch or {}
    for k in allowed_keys.intersection(changed.keys()):
        v = changed[k]
        if v is None or v == "":
            _ = base.pop(k, None)
        else:
            base[k] = v
    return base
