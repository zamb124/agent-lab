"""
Тестовый A2A агент для интеграционных тестов (Protocol 1.0).
Полностью автономный агент без зависимостей от core/agents.
"""

import os
from typing import ClassVar, override

import httpx2
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from apps.test_a2a_sample.simple_agent import SimpleTestAgent

# Self-contained: пакет собирается в минимальный образ без core (apps/test_a2a_sample/Dockerfile).
type JsonObject = dict[str, object]

API_KEY = os.environ["API_KEY"]
AGENT_URL = os.environ["AGENT_URL"]


class CatFactResponse(BaseModel):
    # extra='ignore': внешний catfact.ninja отдаёт ещё и length, нам нужен только fact.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    fact: str = Field(min_length=1)


class CatFactTool:
    """Простой tool для получения фактов о котах."""

    name: ClassVar[str] = "get_cat_fact"
    description: ClassVar[str] = "Получает интересный факт о котах"

    async def execute(self, args: JsonObject, state: JsonObject | None) -> str:
        """Получает факт с внешнего API."""
        _ = args, state
        async with httpx2.AsyncClient(timeout=10.0) as client:
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


def create_app() -> FastAPI:
    """Создает FastAPI приложение с A2A Protocol 1.0."""
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
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=skills,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
    )
    card.supported_interfaces.append(
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
    )

    handler = DefaultRequestHandler(executor, InMemoryTaskStore(), card)
    app = FastAPI(title="Test A2A Agent")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(
            handler,
            rpc_url="/",
            enable_v0_3_compat=False,
        ),
    )
    app.add_middleware(APIKeyMiddleware)
    app.add_api_route("/health", health, methods=["GET"])
    return app


app = create_app()


if __name__ == "__main__":
    from granian import Granian
    from granian.constants import Interfaces

    port = int(os.environ["PORT"])
    Granian(
        target="apps.test_a2a_sample.main:app",
        address="0.0.0.0",
        port=port,
        interface=Interfaces.ASGI,
        workers=1,
    ).serve()
