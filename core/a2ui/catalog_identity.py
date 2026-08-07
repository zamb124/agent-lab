"""Stable Linnex catalog identity, independent from the current request host."""

from __future__ import annotations

import re

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID

_APEX_PATTERN = re.compile(
    r"^(?:localhost|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})$"
)


def _normalize_primary_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not domain or "://" in domain or "/" in domain or ":" in domain:
        raise ValueError("primary_platform_domain must be an apex domain without scheme or path")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("primary_platform_domain is not a valid IDNA domain") from exc
    if _APEX_PATTERN.fullmatch(ascii_domain) is None:
        raise ValueError(f"Invalid primary_platform_domain: {value!r}")
    return ascii_domain


def canonical_platform_catalog_id(primary_platform_domain: str | None = None) -> str:
    """Resolve one logical catalog ID; never derive it from an HTTP Host header."""
    if primary_platform_domain is None:
        from core.config import get_settings

        primary_platform_domain = get_settings().primary_platform_domain
    domain = _normalize_primary_domain(primary_platform_domain)
    return f"https://{domain}/a2ui/catalog/platform/v1"


def validate_platform_catalog_id(
    catalog_id: str,
    *,
    primary_platform_domain: str | None = None,
) -> str:
    expected = canonical_platform_catalog_id(primary_platform_domain)
    if catalog_id != expected:
        raise ValueError(f"Catalog ID must be the canonical platform identity {expected!r}")
    return catalog_id


if canonical_platform_catalog_id("linnex.io") != A2UI_PLATFORM_CATALOG_ID:
    raise RuntimeError("A2UI platform catalog constant is inconsistent with Linnex identity")


__all__ = ["canonical_platform_catalog_id", "validate_platform_catalog_id"]
