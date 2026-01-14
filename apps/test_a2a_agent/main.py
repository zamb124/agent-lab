"""
Тестовый A2A агент для интеграционных тестов.
Полностью автономный агент без зависимостей от core/agents.
"""

import os
import httpx
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from apps.test_a2a_agent.simple_agent import SimpleTestAgent

API_KEY = os.getenv("API_KEY", "test-api-key-12345")


class CatFactTool:
    """Простой tool для получения фактов о котах."""
    
    name = "get_cat_fact"
    description = "Получает интересный факт о котах"
    
    async def execute(self, args=None, state=None):
        """Получает факт с внешнего API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://catfact.ninja/fact")
            if r.status_code == 200:
                return r.json().get("fact", "Коты - удивительные животные!")
            return "Коты спят в среднем 12-16 часов в день."


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки API ключа."""
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/health":
            api_key = request.headers.get("X-API-Key")
            if api_key != API_KEY:
                return JSONResponse({"error": "Invalid API key"}, status_code=401)
        return await call_next(request)


def create_app():
    """Создает FastAPI приложение с A2A протоколом."""
    # Создаем простого тестового агента
    executor = SimpleTestAgent(
        tools=[CatFactTool()],
        prompt="Ты помощник про котов."
    )
    
    skills = [
        AgentSkill(
            id="default",
            name="Test Cat Facts",
            description="Факты о котах для тестов",
            tags=["test", "cats"]
        )
    ]
    
    card = AgentCard(
        name="Test Cat Agent",
        description="Тестовый агент для интеграционных тестов",
        url=os.getenv("AGENT_URL", "http://localhost:8005"),
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, pushNotifications=False),
        skills=skills,
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
    )
    
    app = A2AStarletteApplication(
        card,
        DefaultRequestHandler(executor, InMemoryTaskStore())
    ).build()
    
    app.add_middleware(APIKeyMiddleware)
    app.routes.append(
        Route("/health", lambda r: JSONResponse({"status": "healthy"}), methods=["GET"])
    )
    
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    uvicorn.run(app, host="0.0.0.0", port=port)

