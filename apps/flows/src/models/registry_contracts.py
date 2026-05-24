"""Typed contracts for flows registry API and visual schema."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field

from core.models.base import StrictBaseModel
from core.types import JsonObject


class RegistryProviderOption(StrictBaseModel):
    value: str
    label: str
    kind: Literal["custom", "virtual"]
    custom_id: str | None = None


class RegistryBranchInfo(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    tags: list[str]
    input_modes: list[str] = Field(alias="inputModes")
    output_modes: list[str] = Field(alias="outputModes")
    examples: None = None
    security: None = None


class RegistryFlowCapabilities(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    streaming: bool
    push_notifications: None = Field(alias="pushNotifications")
    state_transition_history: None = Field(alias="stateTransitionHistory")
    extensions: None = None


class RegistryFlowCard(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    flow_id: str
    name: str
    url: str
    description: str
    version: str
    protocol_version: str = Field(alias="protocolVersion")
    preferred_transport: str = Field(alias="preferredTransport")
    default_input_modes: list[str] = Field(alias="defaultInputModes")
    default_output_modes: list[str] = Field(alias="defaultOutputModes")
    capabilities: RegistryFlowCapabilities
    branches: list[RegistryBranchInfo]
    tags: list[str]
    provider: None = None
    documentation_url: None = Field(default=None, alias="documentationUrl")
    icon_url: None = Field(default=None, alias="iconUrl")
    security: None = None
    security_schemes: None = Field(default=None, alias="securitySchemes")
    signatures: None = None
    supports_authenticated_extended_card: bool = Field(alias="supportsAuthenticatedExtendedCard")
    additional_interfaces: None = Field(default=None, alias="additionalInterfaces")
    variables: dict[str, JsonObject] | None = None


class RegistrySchemaSubflow(StrictBaseModel):
    id: str
    name: str
    tools: list[str] = Field(default_factory=list)
    subflows: list["RegistrySchemaSubflow"] = Field(default_factory=list)


class RegistrySchemaNode(StrictBaseModel):
    type: str
    flow_id: str | None = None
    name: str
    tools: list[str] = Field(default_factory=list)
    subflows: list[RegistrySchemaSubflow] = Field(default_factory=list)


class RegistrySchemaEdge(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to: str | None = None
    condition: str | None = None


class RegistryBranchSchema(StrictBaseModel):
    name: str
    description: str
    entry: str
    nodes: dict[str, RegistrySchemaNode]
    edges: list[RegistrySchemaEdge]


class RegistryFlowSchema(StrictBaseModel):
    flow_id: str
    name: str
    description: str
    branches: dict[str, RegistryBranchSchema]
