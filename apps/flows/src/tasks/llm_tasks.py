"""
TaskIQ tasks для LLM вызовов.

Обеспечивает единообразное выполнение LLM через worker.
"""

from typing import Any, Dict, List, Optional

from core.clients.llm import get_llm
from core.logging import get_logger
from apps.flows_worker.broker import broker

logger = get_logger(__name__)


@broker.task(task_name="invoke_llm", queue_name="flows_worker")
async def invoke_llm(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    task_id: Optional[str] = None,
    context_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Вызывает LLM и возвращает результат.
    
    Args:
        messages: Список сообщений в OpenAI формате [{"role": "...", "content": "..."}]
        tools: Опциональный список tools
        task_id: ID задачи для трейсинга
        context_id: ID контекста
        
    Returns:
        {"content": "...", "reasoning": "...", "tool_calls": [...]}
    """
    llm = get_llm()
    
    content_parts = []
    reasoning_parts = []
    tool_calls = None
    
    async for event in llm.stream(
        messages=messages,
        tools=tools or [],
        task_id=task_id,
        context_id=context_id,
    ):
        if hasattr(event, "artifact") and event.artifact:
            artifact_name = event.artifact.name
            if event.artifact.parts:
                for part in event.artifact.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        text = part.root.text
                        if artifact_name == "reasoning":
                            reasoning_parts.append(text)
                        else:
                            content_parts.append(text)
        
        # Извлекаем tool_calls из TaskStatusUpdateEvent
        if hasattr(event, "status") and event.status:
            if event.status.message and event.status.message.metadata:
                tc = event.status.message.metadata.get("tool_calls")
                if tc:
                    tool_calls = tc
    
    return {
        "content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts) if reasoning_parts else None,
        "tool_calls": tool_calls,
    }

