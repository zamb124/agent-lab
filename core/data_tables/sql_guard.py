"""Whitelist SQL для DataTable: один SELECT/DML, без DDL/ATTACH/PRAGMA."""

from __future__ import annotations

import re

from core.data_tables.identifiers import is_user_table_name, validate_ident

_FORBIDDEN = re.compile(
    r"\b(attach|detach|pragma|drop|alter|create|vacuum|reindex|analyze|explain)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)
_STRINGS = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")")
_FROM_JOIN = re.compile(
    r"\b(?:from|join|into|update|table)\s+([a-z][a-z0-9_]{0,62})",
    re.IGNORECASE,
)
_ALLOWED_START = re.compile(r"^\s*(select|insert|update|delete)\b", re.IGNORECASE)


def validate_user_sql(sql: str, *, allowed_tables: frozenset[str]) -> str:
    if not sql or not sql.strip():
        raise ValueError("sql is required")
    stripped = sql.strip()
    if ";" in stripped.rstrip(";"):
        raise ValueError("multiple SQL statements are forbidden")
    if stripped.count(";") > 1:
        raise ValueError("multiple SQL statements are forbidden")
    body = stripped.rstrip(";").strip()
    without_strings = _STRINGS.sub(" ", body)
    without_comments = _COMMENT.sub(" ", without_strings)
    if _FORBIDDEN.search(without_comments):
        raise ValueError("SQL contains a forbidden statement (DDL/ATTACH/PRAGMA)")
    if not _ALLOWED_START.match(without_comments):
        raise ValueError("SQL must be a single SELECT, INSERT, UPDATE or DELETE")
    mentioned: set[str] = set()
    for match in _FROM_JOIN.finditer(without_comments):
        table_name = match.group(1).lower()
        if not is_user_table_name(table_name):
            raise ValueError(f"table {table_name!r} is not a user DataTable")
        _ = validate_ident(table_name, kind="table")
        mentioned.add(table_name)
    if not mentioned:
        raise ValueError("SQL must reference a DataTable user table")
    unknown = mentioned - allowed_tables
    if unknown:
        raise ValueError(f"SQL references unknown tables: {sorted(unknown)}")
    return body
