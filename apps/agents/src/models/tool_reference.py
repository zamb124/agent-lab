"""
Модель ToolReference - инструмент с inline кодом.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    title: Optional[str] = Field(default=None, description="Название для отображения")
    description: Optional[str] = Field(default=None, description="Описание инструмента")
    type: str = Field(
        default="tool",
        description="Тип инструмента (tool, function, external_api)",
    )
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
    
    tags: List[str] = Field(
        default_factory=list,
        description="Группы/категории тула: misc, math, docs, api, validation",
    )
    tool_type: str = Field(
        default="tool",
        description="Тип инструмента: tool, reason, exit"
    )
    public_fields: Optional[List[str]] = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )

    def to_registry_format(self) -> Dict[str, Any]:
        """Преобразует в формат для registry API (совместимость с platformweb)"""
        return {
            "name": self.tool_id,
            "type": self.type,
            "attributes": {
                "description": self.description or "",
                "args_schema": {
                    k: {"type": v.type, "description": v.description}
                    for k, v in self.args_schema.items()
                },
            },
            "mock_map": self.mock_map,
        }
