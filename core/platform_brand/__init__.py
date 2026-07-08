"""Host-aware брендинг платформы по registrable apex-домену."""

from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_brand,
    resolve_brand_domain,
    resolve_context_host,
    resolve_embed_origins,
    resolve_oauth_brand_origin,
    resolve_public_base_url,
    supported_domains,
)

__all__ = [
    "UnknownPlatformDomainError",
    "resolve_brand",
    "resolve_brand_domain",
    "resolve_context_host",
    "resolve_embed_origins",
    "resolve_oauth_brand_origin",
    "resolve_public_base_url",
    "supported_domains",
]
