"""Одноразовый preview embed: минт flows, редирект /l на frontend, consume handoff в Redis."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


def _code_from_share_url(share_url: str) -> str:
    if "/l/" not in share_url:
        raise ValueError(f"Ожидался путь /l/ в share_url: {share_url}")
    return share_url.rstrip("/").split("/l/")[-1]


@pytest.mark.asyncio
async def test_flow_preview_share_one_shot_redis_and_short_link(
    client: AsyncClient, frontend_app, unique_id: str
) -> None:
    flow_id = f"preview_share_{unique_id}"
    create = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Preview Share Test",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "You are a test agent",
                    "tools": [],
                    "llm": {"model": "gpt-4o", "temperature": 0.5},
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert create.status_code == 200, create.text
    try:
        mint = await client.post(
            f"/flows/api/v1/flows/{flow_id}/preview-share",
            json={"branch_id": "default", "guest_max_user_messages": 10},
        )
        assert mint.status_code == 200, mint.text
        share_url = mint.json()["share_url"]
        code = _code_from_share_url(share_url)
        transport = ASGITransport(app=frontend_app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as fe:
            res_l = await fe.get(f"/l/{code}")
            assert res_l.status_code == 303
            loc = res_l.headers.get("location")
            assert loc is not None
            assert loc.startswith("/flow-preview?h=")
            res_ok = await fe.get(loc)
            assert res_ok.status_code == 200
            assert b"data-static-bearer=" in res_ok.content
            res_repeat = await fe.get(loc)
            assert res_repeat.status_code == 404
            res_l2 = await fe.get(f"/l/{code}")
            assert res_l2.status_code == 404
    finally:
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
