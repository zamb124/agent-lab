"""
Request-scope кэш каталога EntityType (company_id, namespace).

Живёт в contextvars — один async request / TaskIQ job scope.
Invalidate при мутациях EntityTypeRepository.
"""

from __future__ import annotations

import contextvars

from apps.crm.db.models import EntityType

_CatalogKey = tuple[str, str | None]
_cache_var: contextvars.ContextVar[dict[_CatalogKey, list[EntityType]] | None] = contextvars.ContextVar(
    "crm_entity_type_catalog_cache",
    default=None,
)


def _store() -> dict[_CatalogKey, list[EntityType]]:
    current = _cache_var.get()
    if current is None:
        created: dict[_CatalogKey, list[EntityType]] = {}
        _ = _cache_var.set(created)
        return created
    return current


def get_cached(company_id: str, namespace: str | None) -> list[EntityType] | None:
    return _store().get((company_id, namespace))


def put_cached(company_id: str, namespace: str | None, items: list[EntityType]) -> None:
    _store()[(company_id, namespace)] = list(items)


def invalidate_company(company_id: str) -> None:
    store = _store()
    for key in list(store):
        if key[0] == company_id:
            del store[key]


def clear_catalog_cache() -> None:
    _ = _cache_var.set(None)
