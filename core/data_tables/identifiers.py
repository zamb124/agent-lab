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


def _ident_problem(name: str, *, kind: str) -> str | None:
    value = name.strip()
    if value == "":
        return f"{kind} name is required"
    if value in _RESERVED_NAMES or value.startswith(_RESERVED_PREFIXES):
        return f"{kind} name {value!r} is reserved"
    if _IDENT_RE.fullmatch(value) is None:
        return f"{kind} name {value!r} must match ^[a-z][a-z0-9_]{{0,62}}$"
    return None


def validate_ident(name: str, *, kind: str) -> str:
    problem = _ident_problem(name, kind=kind)
    if problem is not None:
        raise ValueError(problem)
    return name.strip()


def is_valid_ident(name: str) -> bool:
    return _ident_problem(name, kind="ident") is None


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
