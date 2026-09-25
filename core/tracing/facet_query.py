"""Общий разбор подстроки для админских distinct-фасетов."""

from core.facet_query import ADMIN_FACETS_MAX_LIMIT, MIN_ADMIN_ILIKE_LEN, facet_query_fragment

__all__ = [
    "ADMIN_FACETS_MAX_LIMIT",
    "MIN_ADMIN_ILIKE_LEN",
    "facet_query_fragment",
]
