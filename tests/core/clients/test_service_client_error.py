"""ServiceClientError: статус и detail peer-ответа для проброса 4xx."""

from core.clients.service_client import ServiceClientError


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
