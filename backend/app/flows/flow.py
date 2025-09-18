"""
Flow = административная сущность для управления агентами.
"""

from typing import Dict, Any, Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models import FlowConfig
from app.core.container import get_container


class Flow:
    """
    Flow = простая обертка над агентом.
    Административная сущность с настройками:
    - Какой агент точка входа
    - На каких платформах работает
    - ID, описание, настройки
    """

    def __init__(self, config: FlowConfig):
        self.config = config
        self.entry_agent = None  # Будет установлен при инициализации

    async def initialize(self):
        """Инициализирует entry агента"""
        # Получаем entry point агента
        container = get_container()
        agent_factory = container.get_agent_factory()
        self.entry_agent = await agent_factory.get_agent(self.config.entry_point_agent)

    async def ainvoke(
        self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Унифицированный метод вызова Flow.
        Просто передает вызов entry агенту.
        """
        if not self.entry_agent:
            await self.initialize()

        # Передаем вызов entry агенту
        return await self.entry_agent.ainvoke(input_data, config)

    def as_tool(self, name: Optional[str] = None, description: Optional[str] = None):
        """Flow может быть инструментом для других агентов"""

        class FlowInput(BaseModel):
            input: str = Field(description="Входные данные для flow")

        async def flow_func(input: str) -> str:
            result = await self.ainvoke({"input": input})
            return str(result)

        return StructuredTool.from_function(
            func=flow_func,
            name=name or f"flow_{self.config.flow_id}",
            description=description or self.config.description,
            args_schema=FlowInput,
        )
