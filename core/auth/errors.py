"""
Ошибки авторизации для A2A протокола.

Используют JSON-RPC формат с кастомными кодами ошибок.
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """Конвертирует snake_case в camelCase."""
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class PermissionDeniedA2AError(BaseModel):
    """
    Ошибка отсутствия прав доступа для A2A протокола.

    Используется для отказа в доступе к flow, branch или tool.
    Код -32008 - кастомный код для permission denied.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_by_alias=True,
    )

    code: Literal[-32008] = Field(default=-32008, description="Код ошибки")
    message: str = Field(default="Permission denied", description="Сообщение об ошибке")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Дополнительные данные (resource type, resource id)",
    )

    @classmethod
    def for_flow(cls, flow_id: str, required_groups: list[str]) -> "PermissionDeniedA2AError":
        """Создает ошибку для отказа доступа к flow."""
        return cls(
            message=f"Permission denied for flow '{flow_id}'",
            data={
                "entity_type": "flow",
                "entity_id": flow_id,
                "required_groups": required_groups,
            },
        )

    @classmethod
    def for_branch(cls, branch_id: str, flow_id: str, required_groups: list[str]) -> "PermissionDeniedA2AError":
        """Создает ошибку для отказа доступа к ветке графа."""
        return cls(
            message=f"Permission denied for branch '{branch_id}' in flow '{flow_id}'",
            data={
                "entity_type": "branch",
                "entity_id": branch_id,
                "flow_id": flow_id,
                "required_groups": required_groups,
            },
        )

    @classmethod
    def for_tool(cls, tool_id: str, required_groups: list[str]) -> "PermissionDeniedA2AError":
        """Создает ошибку для отказа доступа к tool."""
        return cls(
            message=f"Permission denied for tool '{tool_id}'",
            data={
                "entity_type": "tool",
                "entity_id": tool_id,
                "required_groups": required_groups,
            },
        )

    def to_json_rpc_error(self) -> Dict[str, Any]:
        """Возвращает ошибку в формате JSON-RPC."""
        error = {
            "code": self.code,
            "message": self.message,
        }
        if self.data:
            error["data"] = self.data
        return error

