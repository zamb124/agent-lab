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


class AgentToolkitRegistryEntry(StrictBaseModel):
    """Bootstrap-запись agent_toolkits в registry.yaml."""

    id: str = Field(min_length=1)
    public: bool = False
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    default_enabled: bool = False
    position: int = 0
    flow_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)


class FlowBundleRegistry(StrictBaseModel):
    """Корневой документ apps/flows/registry.yaml."""

    version: str | None = None
    flows: list[FlowBundleRegistryEntry] = Field(default_factory=list)
    tools: list[BundleRegistryEntry] = Field(default_factory=list)
    agent_toolkits: list[AgentToolkitRegistryEntry] = Field(default_factory=list)
    defaults: JsonObject = Field(default_factory=dict)
