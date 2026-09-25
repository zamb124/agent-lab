"""Общий разбор подстроки для админских distinct-фасетов.

Модуль лежит вне ``core.tracing``: модели биллинга импортируют его на уровне
файла, а пакет ``core.tracing`` при загрузке тянет эти же модели.
"""

MIN_ADMIN_ILIKE_LEN = 2
ADMIN_FACETS_MAX_LIMIT = 20


def facet_query_fragment(q: str | None) -> str | None:
    if q is None:
        return None
    stripped = q.strip()
    if stripped == "":
        return None
    if len(stripped) < MIN_ADMIN_ILIKE_LEN:
        return None
    return stripped
