"""Публичный API бренда платформы по Host header (re-export из core)."""

from core.api.platform_brand import PlatformBrandResponse, router

__all__ = ["PlatformBrandResponse", "router"]
