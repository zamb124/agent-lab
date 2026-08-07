"""ServiceClientError: статус и detail peer-ответа для проброса 4xx."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.clients.service_client import ServiceClient, ServiceClientError

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


@pytest.mark.asyncio
async def test_request_wraps_empty_exception_message_with_type_name() -> None:
    client = ServiceClient()
    mock_http = MagicMock()
    mock_http.request = AsyncMock(side_effect=Exception())
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(client, "_get_service_url", return_value="http://flows.test"),
        patch("core.clients.service_client.get_httpx_client", return_value=mock_http),
    ):
        with pytest.raises(ServiceClientError) as raised:
            await client.request("flows", "GET", "/flows/api/v1/flows/missing")

    assert str(raised.value) == "Ошибка запроса к flows: Exception"
    assert raised.value.__cause__ is not None


@pytest.mark.asyncio
async def test_request_preserves_http_status_error_body() -> None:
    client = ServiceClient()
    response = MagicMock()
    response.status_code = 404
    response.text = '{"detail":"Flow not found"}'
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404",
        request=MagicMock(),
        response=response,
    )
    mock_http = MagicMock()
    mock_http.request = AsyncMock(return_value=response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(client, "_get_service_url", return_value="http://flows.test"),
        patch("core.clients.service_client.get_httpx_client", return_value=mock_http),
    ):
        with pytest.raises(ServiceClientError) as raised:
            await client.request("flows", "GET", "/flows/api/v1/flows/missing")

    assert "HTTP 404 при запросе к flows" in str(raised.value)
    assert raised.value.status_code == 404
