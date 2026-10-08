"""Граница sqlite3.Row и Cursor. Индексация и fetch в stub отдают Any."""

import sqlite3
from collections.abc import Sequence
from typing import Protocol

from core.imports import typed_view

SqliteCell = str | int | float | bytes | None


class _SqliteRowView(Protocol):
    def __getitem__(self, key: str) -> SqliteCell: ...


class _SqliteCursorView(Protocol):
    def fetchall(self) -> Sequence[sqlite3.Row]: ...

    def fetchone(self) -> sqlite3.Row | None: ...


def sqlite_cell(row: sqlite3.Row, key: str) -> SqliteCell:
    return typed_view(row, sqlite3.Row, _SqliteRowView)[key]


def sqlite_fetchall(cursor: sqlite3.Cursor) -> list[sqlite3.Row]:
    return list(typed_view(cursor, sqlite3.Cursor, _SqliteCursorView).fetchall())


def sqlite_fetchone(cursor: sqlite3.Cursor) -> sqlite3.Row | None:
    return typed_view(cursor, sqlite3.Cursor, _SqliteCursorView).fetchone()
