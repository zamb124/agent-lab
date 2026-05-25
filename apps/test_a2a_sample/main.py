"""
Тестовый A2A агент для интеграционных тестов.
Полностью автономный агент без зависимостей от core/agents.
"""

import os
from typing import ClassVar, override

import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from pydantic import Field
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from apps.test_a2a_sample.simple_agent import SimpleTestAgent
from core.models.base import StrictBaseModel
from core.types import JsonObject

API_KEY = os.environ["API_KEY"]
AGENT_URL = os.environ["AGENT_URL"]


class CatFactResponse(StrictBaseModel):
    fact: str = Field(min_length=1)


class CatFactTool:
    """Простой tool для получения фактов о котах."""

    name: ClassVar[str] = "get_cat_fact"
    description: ClassVar[str] = "Получает интересный факт о котах"

    async def execute(self, args: JsonObject, state: JsonObject | None) -> str:
        """Получает факт с внешнего API."""
        _ = args, state
        async with httpx.AsyncClient(timeout=10.0) as client:
            http_response = await client.get("https://catfact.ninja/fact")
            _ = http_response.raise_for_status()
            return CatFactResponse.model_validate_json(http_response.text).fact


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки API ключа."""

    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path != "/health":
            api_key = request.headers.get("X-API-Key")
            if api_key != API_KEY:
                return JSONResponse({"error": "Invalid API key"}, status_code=401)
        return await call_next(request)


def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy"})


def create_app() -> Starlette:
    """Создает FastAPI приложение с A2A протоколом."""
    # Создаем простого тестового агента
    executor = SimpleTestAgent(
        tools=[CatFactTool()],
    )

    skills = [
        AgentSkill(
            id="default",
            name="Test Cat Facts",
            description="Факты о котах для тестов",
            tags=["test", "cats"],
        )
    ]

    card = AgentCard(
        name="Test Cat Agent",
        description="Тестовый агент для интеграционных тестов",
        url=AGENT_URL,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=skills,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
    )

    app = A2AStarletteApplication(
        card,
        DefaultRequestHandler(executor, InMemoryTaskStore()),
    ).build()

    app.add_middleware(APIKeyMiddleware)
    app.routes.append(
        Route("/health", health, methods=["GET"])
    )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    uvicorn.run(app, host="0.0.0.0", port=port)
