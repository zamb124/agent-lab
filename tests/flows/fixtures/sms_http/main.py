"""
Локальный HTTP echo для тестов SmsChannelHandler.

Реальный TCP (granian) + get_httpx_client — без unittest.mock.
Ответ всегда JSON object (handler делает parse_json_object).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.types import JsonObject, JsonValue, parse_json_value

sms_http_app = FastAPI(title="Test SMS HTTP Echo")


def _header_snapshot(request: Request) -> JsonObject:
    content_type = request.headers.get("content-type")
    authorization = request.headers.get("authorization")
    snapshot: JsonObject = {}
    if content_type is not None:
        snapshot["content_type"] = content_type
    if authorization is not None:
        snapshot["authorization"] = authorization
    return snapshot


async def _read_body(request: Request) -> tuple[JsonValue | None, JsonObject | None]:
    if request.method == "GET":
        return None, None
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        form_body: JsonObject = {str(key): str(value) for key, value in form.items()}
        return None, form_body
    raw = await request.body()
    if not raw:
        return None, None
    if "application/json" in content_type or content_type == "":
        return parse_json_value(raw, "sms_http.echo.body"), None
    return raw.decode("utf-8"), None


@sms_http_app.api_route("/sms/echo", methods=["GET", "POST", "PUT", "PATCH"])
async def sms_echo(request: Request) -> JsonObject:
    """Echo: method, path, query, headers, json|form body."""
    json_body, form_body = await _read_body(request)
    return {
        "echo": True,
        "method": request.method,
        "path": request.url.path,
        "query": request.url.query,
        "headers": _header_snapshot(request),
        "json": json_body,
        "form": form_body,
    }


@sms_http_app.get("/sms/accounts/{account_id}/Messages.json")
@sms_http_app.post("/sms/accounts/{account_id}/Messages.json")
async def sms_account_messages(account_id: str, request: Request) -> JsonObject:
    """Echo с path-параметром (подстановка {account_id} / @var: в URL)."""
    json_body, form_body = await _read_body(request)
    return {
        "echo": True,
        "method": request.method,
        "account_id": account_id,
        "path": request.url.path,
        "headers": _header_snapshot(request),
        "json": json_body,
        "form": form_body,
    }


@sms_http_app.post("/sms/fail")
async def sms_fail() -> JSONResponse:
    """Имитация ошибки провайдера SMS."""
    return JSONResponse(
        status_code=400,
        content={"error": "sms_provider_rejected", "detail": "bad request"},
    )


@sms_http_app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
