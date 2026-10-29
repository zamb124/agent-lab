"""ServiceClientError: статус и detail peer-ответа для проброса 4xx."""

import httpx2
import pytest
from aiohttp import web

from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from tests.core.http_proxy_helpers import install_mock_httpx_client
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server

pytestmark = pytest.mark.no_service_client_patch


def test_is_client_error_for_4xx() -> None:
    error = ServiceClientError("boom", status_code=422, response_text='{"detail":"x"}')
    assert error.is_client_error is True


def test_is_client_error_false_for_5xx_and_missing_status() -> None:
    assert ServiceClientError("boom", status_code=500).is_client_error is False
    assert ServiceClientError("boom").is_client_error is False


def test_http_detail_extracts_fastapi_detail_object() -> None:
    error = ServiceClientError(
        "HTTP 422",
        status_code=422,
        response_text=(
            '{"detail":{"tool_id":"ask_user","message":"Tool arguments failed validation"}}'
        ),
    )
    detail = error.http_detail()
    assert isinstance(detail, dict)
    assert detail["tool_id"] == "ask_user"
    assert detail["message"] == "Tool arguments failed validation"


def test_http_detail_falls_back_to_raw_text() -> None:
    error = ServiceClientError("HTTP 400", status_code=400, response_text="not-json")
    assert error.http_detail() == "not-json"


def _raise_blank_exception(_request: httpx2.Request) -> httpx2.Response:
    raise Exception()


@pytest.mark.asyncio
async def test_request_wraps_empty_exception_message_with_type_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_httpx_client(monkeypatch, _raise_blank_exception)
    client = ServiceClient()
    with pytest.raises(ServiceClientError) as raised:
        await client.request("flows", "GET", "/flows/api/v1/flows/missing")

    assert str(raised.value) == "Request error for flows: Exception"
    cause = raised.value.__cause__
    assert type(cause) is Exception
    assert str(cause) == ""


@pytest.mark.asyncio
async def test_request_preserves_http_status_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handle_not_found(_request: web.Request) -> web.Response:
        return web.json_response({"detail": "Flow not found"}, status=404)

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handle_not_found)
    async with ephemeral_web_server(app) as base_url:
        monkeypatch.setattr(get_settings().server, "flows_service_url", base_url)
        client = ServiceClient()
        with pytest.raises(ServiceClientError) as raised:
            await client.request("flows", "GET", "/flows/api/v1/flows/missing")

    assert "HTTP 404 while requesting flows" in str(raised.value)
    assert "Flow not found" in str(raised.value)
    assert raised.value.status_code == 404
    assert raised.value.response_text is not None
    assert "Flow not found" in raised.value.response_text
