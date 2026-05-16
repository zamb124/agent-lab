"""
MockConfig - модель конфигурации моков.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MockLLMResponse(BaseModel):
    """
    Формат mock ответа LLM.

    Типы:
    - text: текстовый ответ
    - tool_call: вызов инструмента
    """

    type: str = Field(description="Тип ответа: 'text' или 'tool_call'")
    content: str | None = Field(default=None, description="Текст ответа (для type='text')")
    tool: str | None = Field(default=None, description="Имя tool (для type='tool_call')")
    args: dict[str, Any] | None = Field(default=None, description="Аргументы tool (для type='tool_call')")


class MockConfig(BaseModel):
    """
    Конфигурация моков.

    Может быть задана на уровне:
    - Global config (conf.json)
    - Конфиг flow (flow.json в bundle и БД)
    - Skill (блок skill во flow.json)
    - Request metadata (metadata.mock)
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Включен ли mock режим")

    llm: list[MockLLMResponse] | list[dict[str, Any]] | None = Field(
        default=None,
        description="Очередь mock ответов LLM"
    )

    tools: dict[str, Any] = Field(
        default_factory=dict,
        description="Mock ответы для tools по имени"
    )

    flows: dict[str, Any] = Field(
        default_factory=dict,
        description="Mock ответы для вложенных flows по ID"
    )

    nodes: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Mock ответы для nodes по ID (мержится в state)"
    )

    permission_groups: list[str] = Field(
        default_factory=lambda: ["admin", "developers"],
        description="Группы с правом использования mock через request metadata"
    )

