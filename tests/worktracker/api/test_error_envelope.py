"""Error envelope: request_id/trace_id в JSON ошибках worktracker."""

from __future__ import annotations

import pytest

from tests.worktracker.conftest import API_PREFIX

pytestmark = pytest.mark.asyncio


async def test_not_found_includes_correlation_fields(worktracker_client, unique_id: str) -> None:
    response = await worktracker_client.get(
        f"{API_PREFIX}/work-items/wi_missing_{unique_id}",
        headers={"X-Request-Id": f"req-{unique_id}"},
    )
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert body.get("request_id") == f"req-{unique_id}"
    assert isinstance(body.get("trace_id"), str)
    assert body.get("service") == "worktracker"


async def test_bad_request_includes_correlation_fields(worktracker_client, unique_id: str) -> None:
    create_resp = await worktracker_client.post(
        f"{API_PREFIX}/work-items",
        json={"title": f"Bad move {unique_id}"},
    )
    work_item_id = create_resp.json()["work_item_id"]
    await worktracker_client.post(
        f"{API_PREFIX}/work-items/{work_item_id}/complete",
        json={"resolution_text": "done"},
    )

    move_resp = await worktracker_client.post(
        f"{API_PREFIX}/work-items/{work_item_id}/move",
        json={"board_column_id": "todo"},
        headers={"X-Request-Id": f"req-move-{unique_id}"},
    )
    assert move_resp.status_code == 400
    body = move_resp.json()
    assert body.get("request_id") == f"req-move-{unique_id}"
    assert isinstance(body.get("trace_id"), str)
