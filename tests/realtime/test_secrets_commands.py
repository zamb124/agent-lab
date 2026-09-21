"""Live Centrifugo RPC + REST identity для всех SECRETS_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /secrets/api/internal/realtime/command` → тот же `op_*`. REST — Granian :9022.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from httpx import AsyncClient, Response

from apps.secrets.realtime.command_router import SECRETS_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/secrets/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"_(?:WS|REST)_")
_VOLATILE_KEYS = frozenset({"created_at", "updated_at", "created_by", "version"})

PayloadStrategy = Literal["body", "body_minus_path", "query", "none"]
CompareMode = Literal["normalized", "marker_row"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    marker: str | None = None


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode = "normalized"


def _variable_key(ctx: LiveCtx) -> str:
    return f"LIVE_{ctx.suffix.upper()}_{ctx.unique_id.upper()}"


def _write_body(variable_key: str) -> JsonObject:
    return {
        "variable_key": variable_key,
        "payload": {"base": {"value_kind": "static", "value": "live"}, "scopes": []},
        "secret": False,
        "shared_for_execution": False,
        "public": False,
        "title": "Live variable",
        "description": "identity test",
    }


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    return require_json_object(response.json(), label)


async def _create_variable(ctx: LiveCtx, variable_key: str) -> JsonObject:
    response = await ctx.client.post(f"{_API}/variables", headers=ctx.headers, json=_write_body(variable_key))
    return await _expect_json(response, ok=(200,), label="create variable")


async def _setup_list(ctx: LiveCtx) -> JsonObject:
    key = _variable_key(ctx)
    _ = await _create_variable(ctx, key)
    ctx.marker = key
    return {"limit": 1000, "offset": 0}


async def _setup_key(ctx: LiveCtx) -> JsonObject:
    key = _variable_key(ctx)
    _ = await _create_variable(ctx, key)
    return {"variable_key": key}


async def _setup_versions(ctx: LiveCtx) -> JsonObject:
    key = _variable_key(ctx)
    _ = await _create_variable(ctx, key)
    return {"variable_key": key, "limit": 50, "offset": 0}


async def _setup_create(ctx: LiveCtx) -> JsonObject:
    return _write_body(_variable_key(ctx))


async def _setup_resolve(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"user_id": None, "namespace": None, "channel": "identity"}


_CASES: dict[str, OpCase] = {
    "secrets/variables/list_requested": OpCase(
        RestMirror("GET", f"{_API}/variables", "query"), _setup_list, True, "marker_row"
    ),
    "secrets/variables/item_requested": OpCase(
        RestMirror("GET", f"{_API}/variables/{{variable_key}}", "none"), _setup_key, True
    ),
    "secrets/variables/create_requested": OpCase(
        RestMirror("POST", f"{_API}/variables", "body"), _setup_create, False
    ),
    "secrets/variables/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/variables/{{variable_key}}", "none"), _setup_key, False
    ),
    "secrets/variables/versions_requested": OpCase(
        RestMirror("GET", f"{_API}/variables/{{variable_key}}/versions", "query"), _setup_versions, True
    ),
    "secrets/variables/resolve_requested": OpCase(
        RestMirror("POST", f"{_API}/variables/resolve", "body"), _setup_resolve, True
    ),
}


def _normalize(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _TRANSPORT_MARKER.sub("_X_", value)
    return value


def _row_by_marker(payload: JsonObject, marker: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched = [item for item in items if isinstance(item, dict) and item.get("variable_key") == marker]
    if len(matched) != 1:
        raise AssertionError(f"expected one row variable_key={marker!r}, got {len(matched)}")
    return require_json_object(matched[0], "list.row")


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


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
    path_params = {key: str(payload[key]) for key in _PATH_PLACEHOLDER.findall(rest.url)}
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body":
        json_body = payload
    elif rest.strategy == "body_minus_path":
        json_body = {k: v for k, v in payload.items() if k not in path_params}
    elif rest.strategy == "query":
        query = {k: v for k, v in payload.items() if k not in path_params and v is not None}
    response = await client.request(rest.method, url, headers=headers, json=json_body, params=query)
    return await _expect_json(response, ok=(200, 201, 202), label=f"REST {rest.method} {url}")


def test_every_secrets_operation_has_live_case() -> None:
    missing = sorted(set(SECRETS_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(SECRETS_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_secrets_op_ws_rest_identical(
    canonical_type: str,
    secrets_service: None,
    realtime_service: None,
    secrets_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = secrets_service, realtime_service
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(client=secrets_client_http, headers=auth_headers_system, unique_id=unique_id, suffix="ws")
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    assert str(ws_event["type"]).endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
    )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = LiveCtx(client=secrets_client_http, headers=auth_headers_system, unique_id=unique_id, suffix="rest")
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=secrets_client_http, headers=auth_headers_system, rest=case.rest, payload=rest_payload
    )
    if case.compare == "marker_row":
        if rest_marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(_row_by_marker(ws_result, rest_marker)) == _normalize(
            _row_by_marker(rest_result, rest_marker)
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
