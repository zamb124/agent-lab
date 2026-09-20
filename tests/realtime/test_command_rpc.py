"""Centrifugo inbound + RPC: только *_requested, owner, company meta, terminal GET."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event, wait_platform_event


def _inbound_body(
    *,
    unique_id: str,
    user_id: str,
    event_type: str,
    company_id: str = "system",
    payload: dict[str, object] | None = None,
    method: str = "platform.event",
    meta_company_id: str | None = "system",
) -> dict[str, object]:
    meta: dict[str, object] | None = None
    if meta_company_id is not None:
        meta = {"company_id": meta_company_id}
    return {
        "client": f"c_{unique_id}",
        "transport": "websocket",
        "protocol": "json",
        "encoding": "json",
        "user": user_id,
        "method": method,
        "data": {
            "event_id": f"e_{unique_id}",
            "type": event_type,
            "company_id": company_id,
            "payload": payload if payload is not None else {},
            "meta": {"source": "ws"},
        },
        "meta": meta,
    }


@pytest.mark.asyncio
async def test_inbound_rejects_non_requested(
    realtime_client_http: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    response = await realtime_client_http.post(
        "/realtime/api/v1/internal/centrifugo/inbound",
        json=_inbound_body(
            unique_id=unique_id,
            user_id=system_user_id,
            event_type="crm/entity/updated",
        ),
    )
    assert response.status_code == 400
    assert "requested" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_inbound_rejects_wrong_rpc_method(
    realtime_client_http: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    response = await realtime_client_http.post(
        "/realtime/api/v1/internal/centrifugo/inbound",
        json=_inbound_body(
            unique_id=unique_id,
            user_id=system_user_id,
            event_type="sync/channels/create_requested",
            method="wrong.method",
        ),
    )
    assert response.status_code == 400
    assert "platform.event" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_inbound_rejects_unknown_owner(
    realtime_client_http: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    response = await realtime_client_http.post(
        "/realtime/api/v1/internal/centrifugo/inbound",
        json=_inbound_body(
            unique_id=unique_id,
            user_id=system_user_id,
            event_type="zzz/foo/bar_requested",
        ),
    )
    assert response.status_code == 400
    assert "owner" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_inbound_rejects_company_mismatch(
    realtime_client_http: AsyncClient,
    system_user_id: str,
    unique_id: str,
) -> None:
    response = await realtime_client_http.post(
        "/realtime/api/v1/internal/centrifugo/inbound",
        json=_inbound_body(
            unique_id=unique_id,
            user_id=system_user_id,
            event_type="sync/channels/create_requested",
            company_id="other_company",
            meta_company_id="system",
        ),
    )
    assert response.status_code == 400
    assert "company_id" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_inbound_rejects_empty_user(
    realtime_client_http: AsyncClient,
    unique_id: str,
) -> None:
    body = _inbound_body(
        unique_id=unique_id,
        user_id="",
        event_type="sync/channels/create_requested",
    )
    response = await realtime_client_http.post(
        "/realtime/api/v1/internal/centrifugo/inbound",
        json=body,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_centrifugo_rpc_rejects_fact_event(
    realtime_service: None,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = realtime_service
    async with connect_centrifugo(auth_token_system) as client:
        with pytest.raises(RuntimeError, match="Centrifugo command error"):
            _ = await rpc_platform_event(
                client,
                event_type="crm/entity/updated",
                payload={"entity_id": unique_id},
                company_id="system",
                event_id=f"e_fact_{unique_id}",
            )


@pytest.mark.asyncio
async def test_centrifugo_rpc_rejects_unknown_method(
    realtime_service: None,
    auth_token_system: str,
) -> None:
    _ = realtime_service
    async with connect_centrifugo(auth_token_system) as client:
        with pytest.raises(RuntimeError, match="Centrifugo command error"):
            _ = await client.rpc("not.platform.event", {"event_id": "x"})


@pytest.mark.asyncio
async def test_command_rpc_failed_terminal_via_get(
    sync_service: None,
    auth_token_system: str,
    realtime_session_client: AsyncClient,
    unique_id: str,
) -> None:
    _ = sync_service
    event_id = f"e_cmd_{unique_id}"
    async with connect_centrifugo(auth_token_system) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type="sync/channels/update_requested",
            payload={"channel_id": f"missing_{unique_id}", "body": {"name": "X"}},
            company_id="system",
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        assert accepted.get("event_id") == event_id
        terminal_ws = await wait_platform_event(
            ws,
            type_="sync/channels/update_failed",
            meta_where={"causation_id": event_id},
            timeout=10.0,
        )
        meta = terminal_ws.get("meta")
        if not isinstance(meta, dict):
            raise AssertionError("terminal meta must be object")
        assert meta.get("causation_id") == event_id
        fetched = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
        assert fetched.status_code == 200, fetched.text
        command = fetched.json()
        assert command["type"] == "sync/channels/update_requested"
        terminal_http = await realtime_session_client.get(
            f"/realtime/api/v1/events/{event_id}/terminal"
        )
        assert terminal_http.status_code == 200, terminal_http.text
        terminal = terminal_http.json()
        assert terminal["type"] == "sync/channels/update_failed"
        assert terminal["meta"]["causation_id"] == event_id
        assert terminal["payload"]["error_code"] == "forbidden"


@pytest.mark.asyncio
async def test_get_terminal_unknown_is_404(
    realtime_session_client: AsyncClient,
    unique_id: str,
) -> None:
    response = await realtime_session_client.get(
        f"/realtime/api/v1/events/e_missing_{unique_id}/terminal"
    )
    assert response.status_code == 404
