"""SERP click endpoint: контракт и валидация payload."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_serp_click_returns_204(search_client):
    response = await search_client.post(
        "/search/api/v1/search/serp/click",
        json={
            "query": "свежие новости технологий",
            "mode": "quick",
            "url": "https://example.ru/articles/tech",
            "position": 3,
            "provider": "index",
            "search_index_id": "runet",
            "serp_cache_key": "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f",
        },
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_serp_click_minimal_payload_returns_204(search_client):
    response = await search_client.post(
        "/search/api/v1/search/serp/click",
        json={
            "query": "запрос",
            "url": "https://example.ru/",
            "position": 1,
        },
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_serp_click_rejects_invalid_payload(search_client):
    empty_query = await search_client.post(
        "/search/api/v1/search/serp/click",
        json={"query": "", "url": "https://example.ru/", "position": 1},
    )
    assert empty_query.status_code == 422

    zero_position = await search_client.post(
        "/search/api/v1/search/serp/click",
        json={"query": "запрос", "url": "https://example.ru/", "position": 0},
    )
    assert zero_position.status_code == 422

    unknown_field = await search_client.post(
        "/search/api/v1/search/serp/click",
        json={"query": "запрос", "url": "https://example.ru/", "position": 1, "extra": True},
    )
    assert unknown_field.status_code == 422
