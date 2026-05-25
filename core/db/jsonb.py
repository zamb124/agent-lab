"""Типизированные SQLAlchemy выражения для JSONB-колонок."""

from __future__ import annotations

from typing import cast as type_cast

from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from core.types import JsonObject


def jsonb_text(
    column: (
        InstrumentedAttribute[JsonObject]
        | InstrumentedAttribute[JsonObject | None]
        | ColumnElement[JsonObject]
        | ColumnElement[JsonObject | None]
    ),
    key: str,
) -> ColumnElement[str | None]:
    """JSONB ->> key как typed SQL expression."""
    return type_cast(ColumnElement[str | None], column.op("->>")(key))
