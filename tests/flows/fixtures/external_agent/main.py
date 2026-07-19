"""
Тестовый A2A-совместимый агент (Protocol 1.0 JSON-RPC).

Минимальная реализация для интеграционных тестов.
"""

import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

external_agent_app = FastAPI(title="Test External Agent")

AGENT_CARD: dict[str, Any] = {
    "name": "Test External Agent",
    "description": "A2A-совместимый агент для тестов",
    "version": "1.0.0",
    "supportedInterfaces": [
        {
            "url": "http://localhost:8080",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ],
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "extendedAgentCard": False,
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "default",
            "name": "Default Skill",
            "description": "Echo skill для тестов",
            "tags": ["test"],
        }
    ],
}


class SendMessageParams(BaseModel):
    message: dict[str, Any]
    configuration: dict[str, Any] = Field(default_factory=dict)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: SendMessageParams


@external_agent_app.get("/.well-known/agent-card.json")
async def get_agent_card() -> dict[str, Any]:
    return AGENT_CARD


@external_agent_app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@external_agent_app.post("/")
async def send_task(request: JsonRpcRequest) -> dict[str, Any]:
    if request.method != "SendMessage":
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": -32601, "message": "Method not found"},
        }

    text = ""
    for part in request.params.message.get("parts", []):
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text += part["text"]

    response_text = f"Echo: {text}"
    task_id = request.params.message.get("taskId") or str(uuid.uuid4())
    context_id = request.params.message.get("contextId") or str(uuid.uuid4())
    return {
        "jsonrpc": "2.0",
        "id": request.id,
        "result": {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "TASK_STATE_COMPLETED",
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_AGENT",
                    "parts": [{"text": response_text}],
                },
            },
            "artifacts": [
                {
                    "artifactId": str(uuid.uuid4()),
                    "name": "response",
                    "parts": [{"text": response_text}],
                }
            ],
        },
    }


if __name__ == "__main__":
    from granian import Granian
    from granian.constants import Interfaces

    Granian(
        target="main:external_agent_app",
        address="0.0.0.0",
        port=8080,
        interface=Interfaces.ASGI,
        workers=1,
    ).serve()
