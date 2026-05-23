"""HTTP-инвариант: cross-origin ES module может загрузить статику /static/core (embed)."""


import pytest


@pytest.mark.asyncio
async def test_static_core_embed_script_includes_acao_when_origin_sent(frontend_client):
    """GET к entrypoint embed-сборки с чужым Origin получает ACAO=* ."""
    response = await frontend_client.get(
        "/static/core/lib/embed-chat/platform-lara-assistant.js",
        headers={"Origin": "https://example.invalid"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


@pytest.mark.asyncio
async def test_static_core_options_preflight_returns_acao(frontend_client):
    response = await frontend_client.request(
        "OPTIONS",
        "/static/core/lib/embed-chat/platform-lara-assistant.js",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 204
    assert response.headers.get("access-control-allow-origin") == "*"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/i18n/en", "/api/platform/file-types"])
async def test_public_embed_bootstrap_endpoints_include_acao(frontend_client, path):
    response = await frontend_client.get(path, headers={"Origin": "https://example.invalid"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
