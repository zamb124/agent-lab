"""
Process-memory кеш каталога EntityType (company_id, namespace).

Снимок отдаём только если memory.revision совпадает с
entity_type_catalog_revision в Postgres. TTL нет.
"""

from __future__ import annotations

import threading

from apps.crm.db.models import EntityType

_CatalogKey = tuple[str, str | None]
_CatalogEntry = tuple[int, tuple[EntityType, ...]]

_lock = threading.Lock()
_store: dict[_CatalogKey, _CatalogEntry] = {}


def get_entry(company_id: str, namespace: str | None) -> _CatalogEntry | None:
    with _lock:
        entry = _store.get((company_id, namespace))
        if entry is None:
            return None
        revision, items = entry
        return (revision, items)


def put_entry(
    company_id: str,
    namespace: str | None,
    revision: int,
    items: list[EntityType],
) -> None:
    with _lock:
        _store[(company_id, namespace)] = (revision, tuple(items))


def invalidate_company(company_id: str) -> None:
    with _lock:
        for key in [cached_key for cached_key in _store if cached_key[0] == company_id]:
            del _store[key]


def clear_catalog_cache() -> None:
    with _lock:
        _store.clear()
