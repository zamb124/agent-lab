"""
Инструменты для работы с сессионным хранилищем.

Категория: Session
Позволяют агентам сохранять и получать данные между запросами.
Данные автоматически персистятся через checkpointer.
"""

from .session_tools import (
    session_set,
    session_get,
    session_has,
    session_delete,
    session_keys,
    get_variable,
)

__all__ = [
    "session_set",
    "session_get",
    "session_has",
    "session_delete",
    "session_keys",
    "get_variable",
]

