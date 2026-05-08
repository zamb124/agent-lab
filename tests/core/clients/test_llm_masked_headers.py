"""Маскирование чувствительных HTTP-заголовков в логах LLM."""

from core.clients.llm.factory import _masked_headers


def test_masked_headers_authorization_and_api_key() -> None:
    out = _masked_headers(
        {
            "Authorization": "Bearer secret",
            "authorization": "Basic x",
            "X-API-Key": "k",
            "OpenAI-Organization": "org",
            "X-Title": "app",
        }
    )
    assert out["Authorization"] == "***"
    assert out["authorization"] == "***"
    assert out["X-API-Key"] == "***"
    assert out["OpenAI-Organization"] == "org"
    assert out["X-Title"] == "app"
