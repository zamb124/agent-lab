"""
Тестовый HTTP API сервер.

Простой API для интеграционных тестов ExternalAPINode и ExternalAPITool.
"""

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from core.types import JsonObject

external_api_app = FastAPI(title="Test External API")


class EchoRequest(BaseModel):
    """Запрос echo."""
    message: str
    uppercase: bool = False


class CalculatorRequest(BaseModel):
    """Запрос калькулятора."""
    a: float
    b: float
    operation: str = "add"


class InterruptResponse(BaseModel):
    """Ответ с interrupt."""
    status: str = "waiting_input"
    interrupt: JsonObject


@external_api_app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@external_api_app.post("/echo")
async def echo(request: EchoRequest) -> JsonObject:
    """Echo API - возвращает сообщение."""
    message = request.message
    if request.uppercase:
        message = message.upper()

    return {
        "status": "completed",
        "data": {
            "result": message,
            "original": request.message,
        }
    }


@external_api_app.post("/calculate")
async def calculate(request: CalculatorRequest) -> JsonObject:
    """Калькулятор."""
    result = 0
    if request.operation == "add":
        result = request.a + request.b
    elif request.operation == "subtract":
        result = request.a - request.b
    elif request.operation == "multiply":
        result = request.a * request.b
    elif request.operation == "divide":
        if request.b == 0:
            return {
                "status": "error",
                "error": "Division by zero"
            }
        result = request.a / request.b
    else:
        return {
            "status": "error",
            "error": f"Unknown operation: {request.operation}"
        }

    return {
        "status": "completed",
        "data": {
            "result": result,
            "operation": request.operation,
        }
    }


@external_api_app.get("/user/{user_id}")
async def get_user(user_id: str) -> JsonObject:
    """Получение пользователя по ID."""
    users = {
        "1": {"name": "Alice", "email": "alice@example.com"},
        "2": {"name": "Bob", "email": "bob@example.com"},
    }

    if user_id not in users:
        return {
            "status": "error",
            "error": f"User {user_id} not found"
        }

    return {
        "status": "completed",
        "data": users[user_id]
    }


@external_api_app.post("/ask-clarification")
async def ask_clarification(request: EchoRequest) -> JsonObject:
    """API который требует уточнения (interrupt)."""
    if len(request.message) < 10:
        return {
            "status": "waiting_input",
            "interrupt": {
                "kind": "user_message",
                "question": "Пожалуйста, предоставьте больше деталей",
            }
        }

    return {
        "status": "completed",
        "data": {
            "result": f"Processed: {request.message}"
        }
    }


@external_api_app.post("/auth-required")
async def auth_required(
    request: EchoRequest,
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key")
) -> JsonObject:
    """API требующий авторизации."""
    if not authorization and not x_api_key:
        raise HTTPException(status_code=401, detail="Authorization required")

    token = authorization or x_api_key
    return {
        "status": "completed",
        "data": {
            "message": request.message,
            "auth_type": "bearer" if authorization else "api_key",
            "token_prefix": token[:10] if token else None
        }
    }


if __name__ == "__main__":
    from granian import Granian
    from granian.constants import Interfaces

    Granian(
        target="main:external_api_app",
        address="0.0.0.0",
        port=8081,
        interface=Interfaces.ASGI,
        workers=1,
    ).serve()
