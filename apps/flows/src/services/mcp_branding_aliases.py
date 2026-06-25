"""Алиасы server_id → canonical branding slug (ручные MCP vs catalog)."""

from __future__ import annotations

# Ручной server_id → catalog_id / manifest server_id с иконкой в bundle.
BRANDING_SERVER_ID_ALIASES: dict[str, str] = {
    "context7": "context7_catalog",
}


def resolve_branding_server_id(server_id: str) -> str:
    return BRANDING_SERVER_ID_ALIASES.get(server_id, server_id)
