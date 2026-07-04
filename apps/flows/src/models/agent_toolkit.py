"""Группа инструментов HumanitecAgent (Platform MCP extension)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


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
