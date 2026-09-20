"""HTTP contract: POST /flows/api/v1/prompts/render."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_prompt_render_substitutes_variables(client, unique_id):
    _ = unique_id
    response = await client.post(
        "/flows/api/v1/prompts/render",
        json={
            "prompt": "Hello {name}, optional {?title}",
            "variables": {"name": "Ada"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rendered"] == "Hello Ada, optional"
    assert body["used_variables"] == ["name", "title"]


@pytest.mark.asyncio
async def test_prompt_render_unmatched_braces_is_400(client, unique_id):
    _ = unique_id
    response = await client.post(
        "/flows/api/v1/prompts/render",
        json={"prompt": "Hello {name", "variables": {"name": "Ada"}},
    )
    assert response.status_code == 400
