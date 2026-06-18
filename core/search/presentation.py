"""SERP presentation helpers shared by search providers and UI."""

from __future__ import annotations

from urllib.parse import quote, urlparse

from core.rag.models import RAGMetadata


def extract_domain_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.strip().lower()
    if not netloc:
        raise ValueError("url must contain a host")
    return netloc


def build_favicon_proxy_url(domain: str) -> str:
    host = domain.strip().lower()
    if not host:
        raise ValueError("domain is required for favicon proxy url")
    return f"/frontend/api/public/search/favicon?domain={quote(host, safe='')}"


def resolve_site_name(*, metadata: RAGMetadata, display_url: str) -> str:
    for field in ("site_name", "publisher"):
        raw = metadata.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return display_url


def resolve_preview_image_url(metadata: RAGMetadata) -> str:
    raw = metadata.get("og_image_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""
