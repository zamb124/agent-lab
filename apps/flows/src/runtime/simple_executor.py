"""
SimpleLlmNodeExecutor - базовый класс для простых внешних агентов.

Автоматически реализует execute на основе tools и prompt.
"""

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.message import get_message_text

from apps.flows.src.runtime.runners import LlmNodeRunner
from apps.flows.src.models import NodeConfig, NodeLLMOverride
from apps.flows.src.models.enums import NodeType
from core.state import ExecutionState
from apps.flows.src.streaming import InMemoryEmitter


class SimpleLlmNodeExecutorMeta(type(AgentExecutor)):
    """Метакласс, который автоматически добавляет __init__ и execute."""
    
    def __new__(mcs, name, bases, namespace):
        tools = namespace.get("tools", [])
        prompt = namespace.get("prompt", "")
        node_id = namespace.get("node_id", name.lower())
        node_name = namespace.get("name", name)
        node_description = namespace.get("description", f"LLM агент {node_name}")
        model = namespace.get("model", "gpt-4o")
        skills = namespace.get("skills", [])
        
        def __init__(self):
            config = NodeConfig(
                node_id=node_id,
                type=NodeType.LLM_NODE,
                name=node_name,
                description=node_description,
                prompt=prompt,
                llm_override=NodeLLMOverride(model=model, temperature=0.2),
            )
            self.runner = LlmNodeRunner(config, tools, None, prompt, llm_node=None)
            self.skills = skills
        
        async def execute(self, context: RequestContext, event_queue: EventQueue):
            session_id = f"{node_id}:{context.context_id}"
            state = ExecutionState(
                task_id=context.task_id,
                context_id=context.context_id,
                session_id=session_id,
                user_id="external",
            )
            
            metadata = {}
            if hasattr(context, "metadata"):
                metadata = getattr(context, "metadata", {}) or {}
            
            if not metadata:
                user_input = context.get_user_input()
                if not isinstance(user_input, str):
                    if hasattr(user_input, "metadata"):
                        metadata = user_input.metadata or {}
                    elif isinstance(user_input, dict):
                        metadata = user_input.get("metadata") or {}
            
            if metadata and "mock" in metadata:
                state.mock = metadata["mock"]
            
            user_input = context.get_user_input()
            if isinstance(user_input, str):
                content = user_input
            else:
                content = get_message_text(user_input)
            
            emitter = InMemoryEmitter(state)
            async for event in self.runner.run({"content": content}, state, emitter=emitter):
                await event_queue.enqueue_event(event)
        
        async def cancel(self, context: RequestContext, event_queue: EventQueue):
            pass
        
        namespace["__init__"] = __init__
        namespace["execute"] = execute
        namespace["cancel"] = cancel
        
        return super().__new__(mcs, name, bases, namespace)


class SimpleLlmNodeExecutor(AgentExecutor, metaclass=SimpleLlmNodeExecutorMeta):
    """
    Базовый класс для простых внешних агентов.
    
    Просто задайте tools и prompt:
    
    class MyAgent(SimpleLlmNodeExecutor):
        tools = [MyTool()]
        prompt = "Ты помощник..."
        skills = [AgentSkill(id="default", name="Default", description="...", tags=[])]
    """
    
    tools = []
    prompt = ""
    node_id = "llm_node"
    name = "LlmNode"
    description = ""
    model = "gpt-4o"
    skills = []
