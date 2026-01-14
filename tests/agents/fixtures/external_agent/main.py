"""
Тестовый A2A-совместимый агент.

Минимальная реализация для интеграционных тестов.
"""

import uuid
from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel

external_agent_app = FastAPI(title="Test External Agent")

AGENT_CARD = {
    "name": "Test External Agent",
    "description": "A2A-совместимый агент для тестов",
    "url": "http://localhost:8080",
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "default",
            "name": "Default Skill",
            "description": "Echo skill для тестов",
            "tags": ["test"],
        }
    ],
}


class MessageSendParams(BaseModel):
    """Параметры message/send."""
    message: Dict[str, Any]
    configuration: Dict[str, Any] = {}


class MessageSendRequest(BaseModel):
    """JSON-RPC запрос message/send."""
    jsonrpc: str = "2.0"
    id: str
    method: str
    params: MessageSendParams


@external_agent_app.get("/.well-known/agent-card.json")
async def get_agent_card() -> Dict[str, Any]:
    """Возвращает agent-card."""
    return AGENT_CARD


@external_agent_app.get("/health")
async def health() -> Dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@external_agent_app.post("/")
async def send_task(request: MessageSendRequest) -> Dict[str, Any]:
    """Обрабатывает задачу (echo)."""
    text = ""
    for part in request.params.message.get("parts", []):
        if part.get("type") == "text":
            text += part.get("text", "")

    response_text = f"Echo: {text}"

    task_id = request.params.message.get("taskId", str(uuid.uuid4()))
    return {
        "jsonrpc": "2.0",
        "id": request.id,
        "result": {
            "id": task_id,
            "status": {
                "state": "completed",
                "message": {
                    "role": "assistant",
                    "parts": [{"type": "text", "text": response_text}],
                },
            },
            "artifacts": [
                {
                    "type": "message",
                    "parts": [{"type": "text", "text": response_text}],
                }
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(external_agent_app, host="0.0.0.0", port=8080)

