"""Лимиты Flow UI — контракт настроек сервиса flows.

Leaf-модуль: импортируется ``apps.flows.config`` и publish-gate ``problems``,
сам ни от чего доменного не зависит.
"""

from pydantic import Field

from core.models.base import StrictBaseModel


class FlowUILimits(StrictBaseModel):
    """Лимиты интерфейса; задаются в настройках сервиса flows, не в документе."""

    max_pages: int = Field(default=24, ge=1, le=100)
    max_blocks_per_page: int = Field(default=400, ge=1, le=5000)
    max_blocks_per_render: int = Field(default=60, ge=1, le=500)
    max_state_bytes: int = Field(default=1_000_000, ge=1024, le=50_000_000)
    max_html_source_bytes: int = Field(default=200_000, ge=1024, le=5_000_000)
    max_html_blocks_per_page: int = Field(default=12, ge=1, le=100)


__all__ = ["FlowUILimits"]
