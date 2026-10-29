"""Unit: SQLite layout, ident whitelist, guarded SQL."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.data_tables.identifiers import validate_ident
from core.data_tables.import_tabular import import_rows_into_new_table, parse_tabular_bytes
from core.data_tables.models import DataTableColumnSpec
from core.data_tables.sql_guard import validate_user_sql
from core.data_tables.sqlite_format import (
    add_user_column,
    create_user_table,
    initialize_platform_schema,
    insert_rows,
    open_sqlite,
    page_rows_by_sort_then_row_id,
    read_schema_snapshot_by_table_name_asc,
    schema_summary_text,
    update_row,
)


def test_csv_reserved_header_becomes_col_index() -> None:
    columns, rows = parse_tabular_bytes(
        b"row_id,Customer Name\n1,Ada\n",
        source_format="csv",
    )
    assert [column.name for column in columns] == ["col_1", "customer_name"]
    assert rows == [{"col_1": "1", "customer_name": "Ada"}]


def test_validate_ident_rejects_reserved_and_invalid() -> None:
    assert validate_ident("leads", kind="table") == "leads"
    with pytest.raises(ValueError, match="reserved"):
        validate_ident("row_id", kind="column")
    with pytest.raises(ValueError, match="reserved"):
        validate_ident("_platform_meta", kind="table")
    with pytest.raises(ValueError, match="must match"):
        validate_ident("Leads", kind="table")


def test_sql_guard_allows_single_select_and_rejects_ddl() -> None:
    allowed = frozenset({"leads"})
    assert validate_user_sql("SELECT name FROM leads", allowed_tables=allowed)
    with pytest.raises(ValueError, match="forbidden"):
        validate_user_sql("ATTACH DATABASE 'x' AS other", allowed_tables=allowed)
    with pytest.raises(ValueError, match="forbidden"):
        validate_user_sql("DROP TABLE leads", allowed_tables=allowed)
    with pytest.raises(ValueError, match="multiple"):
        validate_user_sql("SELECT 1 FROM leads; SELECT 2 FROM leads", allowed_tables=allowed)
    with pytest.raises(ValueError, match="unknown"):
        validate_user_sql("SELECT 1 FROM other", allowed_tables=allowed)


def test_sqlite_format_create_page_and_update(tmp_path: Path) -> None:
    path = tmp_path / "leads.sqlite"
    connection = open_sqlite(path)
    try:
        initialize_platform_schema(
            connection,
            scope="office_document",
            flow_id=None,
            session_id=None,
        )
        create_user_table(
            connection,
            table_name="leads",
            columns=[
                DataTableColumnSpec(name="name", column_type="text"),
                DataTableColumnSpec(name="score", column_type="integer"),
            ],
        )
        row_ids = insert_rows(
            connection,
            table_name="leads",
            rows=[{"name": "Ada", "score": 10}, {"name": "Bob", "score": 3}],
        )
        assert len(row_ids) == 2
        page = page_rows_by_sort_then_row_id(connection, table_name="leads", limit=1)
        assert page.has_more is True
        assert len(page.items) == 1
        assert page.items[0].values["name"] == "Ada"
        second = page_rows_by_sort_then_row_id(
            connection,
            table_name="leads",
            limit=1,
            cursor=page.next_cursor,
        )
        assert second.has_more is False
        assert second.items[0].values["name"] == "Bob"
        update_row(
            connection,
            table_name="leads",
            row_id=row_ids[0],
            values={"score": 99},
        )
        add_user_column(
            connection,
            table_name="leads",
            spec=DataTableColumnSpec(name="note", column_type="text"),
        )
        snapshot = read_schema_snapshot_by_table_name_asc(connection)
        assert snapshot.scope == "office_document"
        assert snapshot.tables[0].name == "leads"
        assert snapshot.tables[0].row_count == 2
        names = [column.name for column in snapshot.tables[0].columns]
        assert names == ["name", "score", "note"]
        summary = schema_summary_text(connection)
        assert "table leads" in summary
        assert "name:text" in summary
        matched = page_rows_by_sort_then_row_id(connection, table_name="leads", limit=10, q="Ada")
        assert len(matched.items) == 1
        assert matched.items[0].values["name"] == "Ada"
        escaped = page_rows_by_sort_then_row_id(connection, table_name="leads", limit=10, q="%")
        assert escaped.items == []
        by_name = page_rows_by_sort_then_row_id(
            connection,
            table_name="leads",
            limit=10,
            column_q=["name:Ada"],
        )
        assert len(by_name.items) == 1
        assert by_name.items[0].values["name"] == "Ada"
        by_score = page_rows_by_sort_then_row_id(
            connection,
            table_name="leads",
            limit=10,
            column_q=["score:99"],
        )
        assert len(by_score.items) == 1
        assert by_score.items[0].values["name"] == "Ada"
        and_miss = page_rows_by_sort_then_row_id(
            connection,
            table_name="leads",
            limit=10,
            column_q=["name:Ada", "score:3"],
        )
        assert and_miss.items == []
        with pytest.raises(ValueError, match="column_q must be column:query"):
            page_rows_by_sort_then_row_id(connection, table_name="leads", limit=10, column_q=["Ada"])
        with pytest.raises(ValueError, match="unknown column_q column"):
            page_rows_by_sort_then_row_id(connection, table_name="leads", limit=10, column_q=["missing:x"])
    finally:
        connection.close()


def test_import_csv_creates_user_table(tmp_path: Path) -> None:
    path = tmp_path / "import.sqlite"
    connection = open_sqlite(path)
    try:
        initialize_platform_schema(
            connection,
            scope="office_document",
            flow_id=None,
            session_id=None,
        )
        columns, rows = parse_tabular_bytes(
            b"Name,Score\nAda,10\nBob,3\n",
            source_format="csv",
        )
        inserted = import_rows_into_new_table(
            connection,
            table_name="imported",
            columns=columns,
            rows=rows,
        )
        assert inserted == 2
        snapshot = read_schema_snapshot_by_table_name_asc(connection)
        assert snapshot.tables[0].name == "imported"
        names = [column.name for column in snapshot.tables[0].columns]
        assert names == ["name", "score"]
    finally:
        connection.close()
