from __future__ import annotations

import pytest

from core.datasources.models import DatasourceOperation, DatasourceSqlOperation
from core.datasources.sql_policy import (
    assert_operation_allowed,
    bind_named_params,
    classify_sql_operation,
    rewrite_placeholders_percent,
    rewrite_placeholders_pyformat,
    split_single_statement,
)


def test_split_single_statement_strips_trailing_semicolons() -> None:
    assert split_single_statement("SELECT 1;") == "SELECT 1"


def test_split_rejects_second_statement() -> None:
    with pytest.raises(ValueError, match="exactly one statement"):
        split_single_statement("SELECT 1; SELECT 2")


def test_classify_select_and_with() -> None:
    assert classify_sql_operation("SELECT 1") is DatasourceSqlOperation.SELECT
    assert classify_sql_operation("WITH x AS (SELECT 1) SELECT * FROM x") is DatasourceSqlOperation.SELECT


def test_classify_mutating() -> None:
    assert classify_sql_operation("INSERT INTO t VALUES (1)") is DatasourceSqlOperation.INSERT
    assert classify_sql_operation("UPDATE t SET a = 1") is DatasourceSqlOperation.UPDATE
    assert classify_sql_operation("DELETE FROM t") is DatasourceSqlOperation.DELETE


def test_query_rejects_insert() -> None:
    with pytest.raises(ValueError, match="query accepts only SELECT"):
        assert_operation_allowed(
            "INSERT INTO t VALUES (1)",
            protocol=DatasourceOperation.QUERY,
            allowed=[DatasourceSqlOperation.INSERT],
        )


def test_execute_rejects_select() -> None:
    with pytest.raises(ValueError, match="execute does not accept SELECT"):
        assert_operation_allowed(
            "SELECT 1",
            protocol=DatasourceOperation.EXECUTE,
            allowed=[DatasourceSqlOperation.SELECT],
        )


def test_allowed_operations_enforced() -> None:
    with pytest.raises(ValueError, match="not in allowed_operations"):
        assert_operation_allowed(
            "INSERT INTO t VALUES (1)",
            protocol=DatasourceOperation.EXECUTE,
            allowed=[DatasourceSqlOperation.SELECT],
        )


def test_bind_named_params_rewrites_and_orders() -> None:
    rewritten, values = bind_named_params(
        "SELECT * FROM t WHERE id = :id AND name = :name",
        {"name": "a", "id": 7},
    )
    assert rewritten == "SELECT * FROM t WHERE id = $1 AND name = $2"
    assert values == [7, "a"]


def test_bind_named_params_missing_and_extra() -> None:
    with pytest.raises(ValueError, match="missing"):
        bind_named_params("SELECT :id", {})
    with pytest.raises(ValueError, match="unused"):
        bind_named_params("SELECT :id", {"id": 1, "x": 2})


def test_placeholder_rewrites() -> None:
    assert rewrite_placeholders_percent("SELECT $1, $2") == "SELECT %s, %s"
    assert rewrite_placeholders_pyformat("SELECT :id") == "SELECT %(id)s"
