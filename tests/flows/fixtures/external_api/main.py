"""
Тестовый HTTP API сервер.

Простой API для интеграционных тестов ExternalAPINode и ExternalAPITool.
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

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
    interrupt: Dict[str, Any]


@external_api_app.get("/health")
async def health() -> Dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@external_api_app.post("/echo")
async def echo(request: EchoRequest) -> Dict[str, Any]:
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
async def calculate(request: CalculatorRequest) -> Dict[str, Any]:
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
async def get_user(user_id: str) -> Dict[str, Any]:
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
async def ask_clarification(request: EchoRequest) -> Dict[str, Any]:
    """API который требует уточнения (interrupt)."""
    if len(request.message) < 10:
        return {
            "status": "waiting_input",
            "interrupt": {
                "question": "Пожалуйста, предоставьте больше деталей",
                "min_length": 10
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
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
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
    import uvicorn
    uvicorn.run(external_api_app, host="0.0.0.0", port=8081)

