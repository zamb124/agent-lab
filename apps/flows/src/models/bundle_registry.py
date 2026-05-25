"""Строгий контракт apps/flows/registry.yaml."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject


class BundleRegistryEntry(StrictBaseModel):
    """Общая запись flow/tool в registry.yaml."""

    id: str = Field(min_length=1)
    public: bool = False
    description: str | None = None


class FlowBundleRegistryEntry(BundleRegistryEntry):
    """Запись flow bundle в registry.yaml."""

    landing_public_demo: bool = False


class FlowBundleRegistry(StrictBaseModel):
    """Корневой документ apps/flows/registry.yaml."""

    version: str | None = None
    flows: list[FlowBundleRegistryEntry] = Field(default_factory=list)
    tools: list[BundleRegistryEntry] = Field(default_factory=list)
    defaults: JsonObject = Field(default_factory=dict)
