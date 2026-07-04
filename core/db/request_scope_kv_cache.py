"""
In-request memo для повторных Storage/Users key lookup в одном async scope.
"""

from __future__ import annotations

import contextvars
from typing import NamedTuple

_KvKey = tuple[str, str, str]
_cache_var: contextvars.ContextVar[dict[_KvKey, str | None] | None] = contextvars.ContextVar(
    "platform_request_scope_kv_cache",
    default=None,
)


class MemoLookupResult(NamedTuple):
    hit: bool
    value: str | None


def _store() -> dict[_KvKey, str | None]:
    current = _cache_var.get()
    if current is None:
        created: dict[_KvKey, str | None] = {}
        _ = _cache_var.set(created)
        return created
    return current


def lookup_memoized(table_name: str, final_key: str, *, for_update: bool) -> MemoLookupResult:
    if for_update:
        return MemoLookupResult(hit=False, value=None)
    cache_key = (table_name, final_key, "get")
    store = _store()
    if cache_key not in store:
        return MemoLookupResult(hit=False, value=None)
    return MemoLookupResult(hit=True, value=store[cache_key])


def set_memoized(table_name: str, final_key: str, value: str | None) -> None:
    _store()[(table_name, final_key, "get")] = value


def invalidate_key(table_name: str, final_key: str) -> None:
    _ = _store().pop((table_name, final_key, "get"), None)


def clear_request_scope_kv_cache() -> None:
    _ = _cache_var.set(None)
