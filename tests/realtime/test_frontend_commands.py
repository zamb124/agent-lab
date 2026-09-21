"""Live Centrifugo RPC + REST identity для всех FRONTEND_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /frontend/api/internal/realtime/command` → тот же `op_*`. REST — Granian :9004.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from httpx import AsyncClient, Response

from apps.frontend.realtime.command_router import FRONTEND_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/frontend/api"
PayloadStrategy = Literal["body", "query", "none"]
SetupFn = Callable[[str], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return require_json_object(response.json(), label)


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _setup_empty(unique_id: str) -> JsonObject:
    _ = unique_id
    return {}


_CASES: dict[str, OpCase] = {
    "frontend/dashboard/stats_requested": OpCase(RestMirror("GET", f"{_API}/dashboard/stats", "none"), _setup_empty),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 20.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required")
    event_id = uuid.uuid4().hex
    succeeded = canonical_type[: -len("_requested")] + "_succeeded"
    failed = canonical_type[: -len("_requested")] + "_failed"
    async with connect_centrifugo(auth_token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            if event.get("type") not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    assert require_json_object(terminal_http.json(), "terminal")["type"] == terminal_ws["type"]
    return terminal_ws


async def _rest_command(
    *, client: AsyncClient, headers: dict[str, str], rest: RestMirror, payload: JsonObject
) -> JsonObject:
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body":
        json_body = payload
    elif rest.strategy == "query":
        query = dict(payload)
    response = await client.request(rest.method, rest.url, headers=headers, json=json_body, params=query)
    return await _expect_json(response, ok=(200, 201, 202, 204), label=f"REST {rest.method} {rest.url}")


def test_every_frontend_operation_has_live_case() -> None:
    missing = sorted(set(FRONTEND_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(FRONTEND_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_frontend_op_ws_rest_identical(
    canonical_type: str,
    frontend_service: None,
    realtime_service: None,
    frontend_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = frontend_service, realtime_service
    case = _CASES[canonical_type]
    payload = await case.setup(unique_id)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=payload,
    )
    assert str(ws_event["type"]).endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
    )
    rest_result = await _rest_command(
        client=frontend_client_http, headers=auth_headers_system, rest=case.rest, payload=payload
    )
    assert _event_payload(ws_event) == rest_result, f"WS != REST для {canonical_type}"
