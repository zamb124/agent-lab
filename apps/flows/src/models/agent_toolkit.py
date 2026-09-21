"""Группа инструментов HumanitecAgent (Platform MCP extension)."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models.base import StrictBaseModel


class AgentToolkit(BaseModel):
    """Группа flows/tools, экспонируемая в HumanitecAgent как отдельное MCP-расширение."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "agent_toolkit"},
        extra="forbid",
    )

    toolkit_id: str = Field(..., min_length=1, description="Стабильный id группы (slug)")
    name: str = Field(..., min_length=1, description="Отображаемое имя в агенте")
    description: str = Field(..., min_length=1, description="Описание для UI агента")
    default_enabled: bool = Field(
        default=False,
        description="Включать расширение по умолчанию при первом появлении на устройстве",
    )
    position: int = Field(default=0, description="Порядок в списке расширений")
    flow_ids: list[str] = Field(
        default_factory=list,
        description="flow_id, входящие в группу",
    )
    tool_ids: list[str] = Field(
        default_factory=list,
        description="tool_id (builtin и custom), входящие в группу",
    )
    source: str = Field(
        default="platform",
        description="platform — из registry bootstrap; custom — создана компанией",
    )


class AgentToolkitIdPayload(StrictBaseModel):
    toolkit_id: str = Field(min_length=1)


class AgentToolkitCreateRequest(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool = False
    position: int = 100
    flow_ids: list[str] = []
    tool_ids: list[str] = []


class AgentToolkitUpdateRequest(StrictBaseModel):
    name: str
    description: str
    default_enabled: bool
    position: int
    flow_ids: list[str]
    tool_ids: list[str]


class AgentToolkitUpdatePayload(AgentToolkitUpdateRequest):
    toolkit_id: str = Field(min_length=1)


class AgentToolkitDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    toolkit_id: str


class AgentToolkitCatalogListPayload(StrictBaseModel):
    """Каталог для LinnexAgent: MCP URL строятся под публичный origin фронта вызывающего."""

    frontend_base_url: str = Field(min_length=1)
    desktop_only: bool = False


class AgentToolkitCatalogItem(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool
    position: int
    mcp_url: str
