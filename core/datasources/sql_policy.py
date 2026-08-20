"""Политика SQL для внешних datasource: один statement, named params, операция."""

from __future__ import annotations

import re
from collections.abc import Mapping

from core.datasources.models import DatasourceOperation, DatasourceSqlOperation
from core.types import JsonObject, JsonValue

_PARAM_TOKEN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
_LEADING_WORD = re.compile(r"^\s*\(?\s*([A-Za-z]+)", re.IGNORECASE)

_SELECT_HEADS = frozenset({"select", "with"})
_HEAD_TO_OPERATION: dict[str, DatasourceSqlOperation] = {
    "select": DatasourceSqlOperation.SELECT,
    "with": DatasourceSqlOperation.SELECT,
    "insert": DatasourceSqlOperation.INSERT,
    "update": DatasourceSqlOperation.UPDATE,
    "delete": DatasourceSqlOperation.DELETE,
}


def split_single_statement(sql: str) -> str:
    stripped = sql.strip()
    if not stripped:
        raise ValueError("sql is empty")
    leftover = _strip_trailing_semicolons(stripped)
    if _has_unquoted_semicolon(leftover):
        raise ValueError("sql must contain exactly one statement")
    return leftover


def classify_sql_operation(sql: str) -> DatasourceSqlOperation:
    statement = split_single_statement(sql)
    match = _LEADING_WORD.match(statement)
    if match is None:
        raise ValueError("sql must start with SELECT, WITH, INSERT, UPDATE or DELETE")
    head = match.group(1).lower()
    operation = _HEAD_TO_OPERATION.get(head)
    if operation is None:
        raise ValueError(
            f"sql head {head!r} is not allowed; use SELECT/WITH/INSERT/UPDATE/DELETE"
        )
    return operation


def assert_operation_allowed(
    sql: str,
    *,
    protocol: DatasourceOperation,
    allowed: list[DatasourceSqlOperation],
) -> DatasourceSqlOperation:
    sql_operation = classify_sql_operation(sql)
    if protocol is DatasourceOperation.QUERY and sql_operation is not DatasourceSqlOperation.SELECT:
        raise ValueError("query accepts only SELECT/WITH")
    if protocol is DatasourceOperation.EXECUTE and sql_operation is DatasourceSqlOperation.SELECT:
        raise ValueError("execute does not accept SELECT; use query")
    if sql_operation not in allowed:
        allowed_names = sorted(str(item) for item in allowed)
        raise ValueError(
            f"sql operation {str(sql_operation)!r} is not in allowed_operations {allowed_names}"
        )
    return sql_operation


def bind_named_params(sql: str, params: Mapping[str, JsonValue]) -> tuple[str, list[JsonValue]]:
    statement = split_single_statement(sql)
    names: list[str] = []
    seen: set[str] = set()

    def _collect(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in seen:
            names.append(name)
            seen.add(name)
        return match.group(0)

    _ = _PARAM_TOKEN.sub(_collect, statement)
    missing = [name for name in names if name not in params]
    if missing:
        raise ValueError(f"sql params missing: {missing}")
    extra = sorted(key for key in params if key not in seen)
    if extra:
        raise ValueError(f"sql params unused: {extra}")
    values = [params[name] for name in names]
    index_by_name = {name: index + 1 for index, name in enumerate(names)}

    def _replace(match: re.Match[str]) -> str:
        return f"${index_by_name[match.group(1)]}"

    rewritten = _PARAM_TOKEN.sub(_replace, statement)
    return rewritten, values


def rewrite_placeholders_percent(sql_with_dollar: str) -> str:
    return re.sub(r"\$(\d+)", "%s", sql_with_dollar)


def rewrite_placeholders_pyformat(sql: str) -> str:
    statement = split_single_statement(sql)
    return _PARAM_TOKEN.sub(lambda match: f"%({match.group(1)})s", statement)


def json_params(params: JsonObject) -> dict[str, JsonValue]:
    return dict(params)


def _strip_trailing_semicolons(sql: str) -> str:
    cut = sql.rstrip()
    while cut.endswith(";"):
        cut = cut[:-1].rstrip()
    return cut


def _has_unquoted_semicolon(sql: str) -> bool:
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if not in_single and not in_double:
            if char == "-" and nxt == "-":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and nxt == "*":
                in_block_comment = True
                index += 2
                continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if char == ";" and not in_single and not in_double:
            return True
        index += 1
    return False
