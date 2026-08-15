"""Whitelist имён таблиц и колонок DataTable."""

from __future__ import annotations

import re

from core.data_tables.models import PLATFORM_COLUMNS_TABLE, PLATFORM_META_TABLE, SYSTEM_COLUMNS

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_RESERVED_PREFIXES: tuple[str, ...] = ("sqlite_", "_platform_")
_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        PLATFORM_META_TABLE,
        PLATFORM_COLUMNS_TABLE,
        *SYSTEM_COLUMNS,
    }
)


def validate_ident(name: str, *, kind: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError(f"{kind} name is required")
    if value in _RESERVED_NAMES or value.startswith(_RESERVED_PREFIXES):
        raise ValueError(f"{kind} name {value!r} is reserved")
    if not _IDENT_RE.fullmatch(value):
        raise ValueError(
            f"{kind} name {value!r} must match ^[a-z][a-z0-9_]{{0,62}}$"
        )
    return value


def quote_sql_ident(name: str) -> str:
    if not name or not _IDENT_RE.fullmatch(name):
        raise ValueError(f"invalid SQL identifier {name!r}")
    return '"' + name + '"'


def is_user_table_name(name: str) -> bool:
    if name in _RESERVED_NAMES:
        return False
    if name.startswith(_RESERVED_PREFIXES):
        return False
    return _IDENT_RE.fullmatch(name) is not None
