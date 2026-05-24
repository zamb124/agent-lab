"""
SimpleLlmNodeExecutor - базовый класс для простых внешних агентов.

Автоматически реализует execute на основе tools и prompt.
"""

from __future__ import annotations

from typing import ClassVar, override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentSkill

from apps.flows.src.models import NodeConfig, NodeLLMConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.runners import LlmNodeRunner
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.src.tools.base import BaseTool
from core.state import ExecutionState
from core.types import JsonObject, require_json_object


class SimpleLlmNodeExecutor(AgentExecutor):
    """
    Базовый класс для простых внешних агентов.

    Просто задайте tools и prompt:

    class MyAgent(SimpleLlmNodeExecutor):
        tools = [MyTool()]
        prompt = "Ты помощник..."
        agent_skills = [AgentSkill(id="default", name="Default", description="...", tags=[])]
    """

    tools: ClassVar[list[BaseTool]] = []
    prompt: ClassVar[str] = ""
    node_id: ClassVar[str] = "llm_node"
    name: ClassVar[str] = "LlmNode"
    description: ClassVar[str] = ""
    model: ClassVar[str] = "gpt-4o"
    agent_skills: ClassVar[list[AgentSkill]] = []

    def __init__(self) -> None:
        cls = type(self)
        node_description = cls.description or f"LLM агент {cls.name}"
        config = NodeConfig(
            node_id=cls.node_id,
            type=NodeType.LLM_NODE,
            name=cls.name,
            description=node_description,
            prompt=cls.prompt,
            llm=NodeLLMConfig(model=cls.model, temperature=0.2),
        )
        self.runner: LlmNodeRunner = LlmNodeRunner(
            config,
            cls.tools,
            None,
            cls.prompt,
            llm_node=None,
        )
        self.resolved_agent_skills: list[AgentSkill] = list(cls.agent_skills)

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.task_id is None or context.context_id is None:
            raise ValueError("RequestContext.task_id and context_id are required")
        session_id = f"{self.node_id}:{context.context_id}"
        state = ExecutionState(
            task_id=context.task_id,
            context_id=context.context_id,
            session_id=session_id,
            user_id="external",
        )

        raw_metadata: object = context.metadata
        metadata = require_json_object(raw_metadata, "request.metadata")
        mock_value = metadata.get("mock")
        if mock_value is not None:
            state.mock = require_json_object(mock_value, "request.metadata.mock")

        input_data: JsonObject = {"content": context.get_user_input()}
        emitter = InMemoryEmitter(state)
        async for event in self.runner.run(input_data, state, emitter=emitter):
            await event_queue.enqueue_event(event)

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        _ = context, event_queue
        return None
