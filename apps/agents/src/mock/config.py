"""
MockConfig - модель конфигурации моков.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class MockLLMResponse(BaseModel):
    """
    Формат mock ответа LLM.
    
    Типы:
    - text: текстовый ответ
    - tool_call: вызов инструмента
    """
    
    type: str = Field(description="Тип ответа: 'text' или 'tool_call'")
    content: Optional[str] = Field(default=None, description="Текст ответа (для type='text')")
    tool: Optional[str] = Field(default=None, description="Имя tool (для type='tool_call')")
    args: Optional[Dict[str, Any]] = Field(default=None, description="Аргументы tool (для type='tool_call')")


class MockConfig(BaseModel):
    """
    Конфигурация моков.
    
    Может быть задана на уровне:
    - Global config (conf.json)
    - Agent config (agent.json)
    - Skill config (skill в agent.json)
    - Request metadata (metadata.mock)
    """
    
    model_config = ConfigDict(extra="allow")
    
    enabled: bool = Field(default=False, description="Включен ли mock режим")
    
    llm: Optional[Union[List[MockLLMResponse], List[Dict[str, Any]]]] = Field(
        default=None,
        description="Очередь mock ответов LLM"
    )
    
    tools: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mock ответы для tools по имени"
    )
    
    agents: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mock ответы для agents (субагентов) по ID"
    )
    
    nodes: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Mock ответы для nodes по ID (мержится в state)"
    )
    
    permission_groups: List[str] = Field(
        default_factory=lambda: ["admin", "developers"],
        description="Группы с правом использования mock через request metadata"
    )

