"""
Модель ToolReference - инструмент с inline кодом или MCP.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import CodeMode, ReactToolRole

# Тип для permission: строка или список строк
Permission = Optional[Union[str, List[str]]]


class CallParameter(BaseModel):
    """Параметр вызова инструмента"""

    type: str = Field(default="string", description="Тип параметра")
    description: str = Field(default="", description="Описание параметра")
    required: bool = Field(default=True, description="Обязательный параметр")


class ToolReference(BaseModel):
    """Инструмент с inline кодом"""

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "tool"})

    tool_id: str = Field(..., description="ID инструмента")
    name: Optional[str] = Field(
        default=None,
        description="Подпись в UI (flows editor, модалки). Если не задана — title или tool_id.",
    )
    title: Optional[str] = Field(default=None, description="Название для отображения")
    description: Optional[str] = Field(default=None, description="Описание инструмента")
    args_schema: Dict[str, CallParameter] = Field(
        default_factory=dict, description="Схема аргументов {param_name: {type, description}}"
    )
    mock_map: Optional[Dict[str, Any]] = Field(
        default=None, description="Mock данные для api_call tools"
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="Параметры инструмента")
    code: Optional[str] = Field(default=None, description="Python код инструмента")
    permission: List[str] = Field(
        default_factory=list,
        description="Группы с доступом к tool. Пустой список = доступ для всех",
    )
    
    @field_validator("permission", mode="before")
    @classmethod
    def convert_none_to_list(cls, v):
        if v is None:
            return []
        return v

    @model_validator(mode="after")
    def default_display_name(self):
        raw = (self.name or "").strip()
        if raw:
            return self
        t = (self.title or "").strip()
        label = t if t else self.tool_id.strip()
        if not label:
            raise ValueError("tool_id must be non-empty for display name")
        object.__setattr__(self, "name", label)
        return self
    
    tags: List[str] = Field(
        default_factory=list,
        description="Группы/категории тула: misc, math, docs, api, validation",
    )
    react_role: ReactToolRole = Field(
        default=ReactToolRole.STANDARD,
        description="Роль в ReAct: standard, reason, exit",
    )
    public_fields: Optional[List[str]] = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )
    
    # MCP-специфичные поля
    code_mode: CodeMode = Field(
        default=CodeMode.INLINE_CODE,
        description="Режим кода: inline_code или mcp_tool"
    )
    mcp_server_id: Optional[str] = Field(
        default=None,
        description="ID MCP сервера (для MCP тулов)"
    )
    mcp_tool_name: Optional[str] = Field(
        default=None,
        description="Имя tool на MCP сервере"
    )

    def to_registry_format(self) -> Dict[str, Any]:
        """Преобразует в формат для registry API (совместимость с platformweb)"""
        return {
            "name": self.tool_id,
            "type": "inline_code",
            "attributes": {
                "description": self.description or "",
                "args_schema": {
                    k: {"type": v.type, "description": v.description}
                    for k, v in self.args_schema.items()
                },
            },
            "mock_map": self.mock_map,
        }
