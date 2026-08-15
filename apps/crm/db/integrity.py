"""Распознавание PostgreSQL UniqueViolation в цепочке SQLAlchemy/asyncpg."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def is_unique_violation(exc: BaseException) -> bool:
    """True если цепочка исключений содержит UniqueViolationError."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if type(current).__name__ == "UniqueViolationError":
            return True
        if isinstance(current, IntegrityError) and isinstance(current.orig, BaseException):
            current = current.orig
            continue
        if isinstance(current.__cause__, BaseException):
            current = current.__cause__
            continue
        if isinstance(current.__context__, BaseException):
            current = current.__context__
            continue
        current = None
    return False
