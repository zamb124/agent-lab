"""Утилиты catalog_id и slug для MCP registry."""

from __future__ import annotations

import re

_CATALOG_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")


def catalog_id_from_registry_name(registry_name: str) -> str:
    raw = registry_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not slug:
        raise ValueError("registry_name is empty after slugify")
    if not slug[0].isalpha():
        slug = f"mcp_{slug}"
    if len(slug) > 64:
        slug = slug[:64].rstrip("_")
    if not _CATALOG_ID_PATTERN.match(slug):
        raise ValueError(f"catalog_id {slug!r} is not a valid MCP server_id")
    return slug


def server_id_from_catalog_id(catalog_id: str) -> str:
    catalog_id_stripped = catalog_id.strip()
    if not _CATALOG_ID_PATTERN.match(catalog_id_stripped):
        raise ValueError(f"catalog_id {catalog_id_stripped!r} is not a valid server_id")
    return catalog_id_stripped
