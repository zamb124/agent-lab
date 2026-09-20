"""Live Centrifugo RPC + REST identity для всех WORKTRACKER_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /worktracker/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9021. После RPC — `GET /realtime/api/v1/events/{id}/terminal`.
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

from apps.worktracker.realtime.command_router import WORKTRACKER_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/worktracker/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_VOLATILE_KEYS = frozenset(
    {
        "work_item_id",
        "board_id",
        "work_queue_id",
        "comment_id",
        "work_queue_slug",
        "created_at",
        "updated_at",
        "request_id",
        "trace_id",
        "service",
        "observability",
    }
)

CompareMode = Literal["exact", "normalized", "summary", "named_slug"]
PayloadStrategy = Literal["body_minus_path", "query", "none"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


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
    compare: CompareMode


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    system_user_id: str
    system_user2_id: str
    marker: str | None = None


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _strip_transport_marker(text: str) -> str:
    if text.endswith("-ws"):
        return text[: -len("-ws")]
    if text.endswith("-rest"):
        return text[: -len("-rest")]
    return text


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _strip_transport_marker(value)
    return value


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return _json(response, label)


async def _create_queue(ctx: LiveCtx) -> JsonObject:
    slug = f"q-{ctx.unique_id}-{ctx.suffix}"
    response = await ctx.client.post(
        f"{_API}/work-queues",
        headers=ctx.headers,
        json={"name": f"Live queue {ctx.unique_id}", "slug": slug},
    )
    body = await _expect_json(response, ok=(201,), label="create_queue")
    ctx.marker = slug
    return body


async def _create_board(ctx: LiveCtx) -> JsonObject:
    namespace = f"ns-{ctx.unique_id}"
    response = await ctx.client.post(
        f"{_API}/boards",
        headers=ctx.headers,
        json={
            "name": f"Live board {ctx.unique_id}",
            "namespace": namespace,
            "columns": [
                {"board_column_id": "todo", "label": "To do", "state": "open", "position": 0},
                {"board_column_id": "done", "label": "Done", "state": "done", "position": 1},
            ],
        },
    )
    body = await _expect_json(response, ok=(201,), label="create_board")
    ctx.marker = namespace
    return body


async def _create_item(ctx: LiveCtx, extra: JsonObject | None = None) -> JsonObject:
    payload: JsonObject = {"title": f"Live item {ctx.unique_id}-{ctx.suffix}"}
    if extra is not None:
        payload.update(extra)
    response = await ctx.client.post(f"{_API}/work-items", headers=ctx.headers, json=payload)
    return await _expect_json(response, ok=(201,), label="create_item")


async def _setup_items_list(ctx: LiveCtx) -> JsonObject:
    namespace = f"ns-list-{ctx.unique_id}"
    await _create_item(ctx, {"namespace": namespace})
    ctx.marker = namespace
    return {"namespace": namespace, "limit": 200, "offset": 0}


async def _setup_mine_summary(ctx: LiveCtx) -> JsonObject:
    await _create_item(ctx)
    return {}


async def _setup_item_get(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {"work_item_id": _str_field(item, "work_item_id")}


async def _setup_item_create(ctx: LiveCtx) -> JsonObject:
    return {"title": f"Created {ctx.unique_id}-{ctx.suffix}"}


async def _setup_item_update(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {
        "work_item_id": _str_field(item, "work_item_id"),
        "title": f"Renamed {ctx.unique_id}",
        "description": "live-update",
    }


async def _setup_item_assign(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {
        "work_item_id": _str_field(item, "work_item_id"),
        "assignment": {"assignee_kind": "users", "user_ids": [ctx.system_user2_id]},
    }


async def _setup_item_move(ctx: LiveCtx) -> JsonObject:
    board = await _create_board(ctx)
    item = await _create_item(
        ctx,
        {
            "board_id": _str_field(board, "board_id"),
            "board_column_id": "todo",
        },
    )
    return {"work_item_id": _str_field(item, "work_item_id"), "board_column_id": "done"}


async def _setup_item_claim(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    item = await _create_item(
        ctx,
        {"assignment": {"assignee_kind": "queue", "work_queue_id": _str_field(queue, "work_queue_id")}},
    )
    return {"work_item_id": _str_field(item, "work_item_id")}


async def _setup_item_comment(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {"work_item_id": _str_field(item, "work_item_id"), "text": f"note {ctx.unique_id}"}


async def _setup_item_comments_list(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    work_item_id = _str_field(item, "work_item_id")
    added = await ctx.client.post(
        f"{_API}/work-items/{work_item_id}/comments",
        headers=ctx.headers,
        json={"text": f"listed {ctx.unique_id}"},
    )
    await _expect_json(added, ok=(201,), label="add_comment")
    return {"work_item_id": work_item_id}


async def _setup_item_complete(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {
        "work_item_id": _str_field(item, "work_item_id"),
        "resolution_text": f"done {ctx.unique_id}",
    }


async def _setup_item_cancel(ctx: LiveCtx) -> JsonObject:
    item = await _create_item(ctx)
    return {"work_item_id": _str_field(item, "work_item_id")}


async def _setup_boards_list(ctx: LiveCtx) -> JsonObject:
    board = await _create_board(ctx)
    namespace = _str_field(board, "namespace")
    ctx.marker = namespace
    return {"namespace": namespace, "limit": 200, "offset": 0}


async def _setup_board_get(ctx: LiveCtx) -> JsonObject:
    board = await _create_board(ctx)
    return {"board_id": _str_field(board, "board_id")}


async def _setup_board_create(ctx: LiveCtx) -> JsonObject:
    return {
        "name": f"Created board {ctx.unique_id}",
        "namespace": f"ns-create-{ctx.unique_id}-{ctx.suffix}",
        "columns": [
            {"board_column_id": "todo", "label": "To do", "state": "open", "position": 0},
            {"board_column_id": "done", "label": "Done", "state": "done", "position": 1},
        ],
    }


async def _setup_board_update(ctx: LiveCtx) -> JsonObject:
    board = await _create_board(ctx)
    return {
        "board_id": _str_field(board, "board_id"),
        "name": f"Renamed board {ctx.unique_id}",
    }


async def _setup_queues_list(ctx: LiveCtx) -> JsonObject:
    await _create_queue(ctx)
    return {"limit": 200, "offset": 0}


async def _setup_queue_create(ctx: LiveCtx) -> JsonObject:
    slug = f"qc-{ctx.unique_id}-{ctx.suffix}"
    ctx.marker = slug
    return {"name": f"Created queue {ctx.unique_id}", "slug": slug}


async def _setup_queue_update(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    return {
        "work_queue_id": _str_field(queue, "work_queue_id"),
        "name": f"Renamed queue {ctx.unique_id}",
        "description": "live-queue",
    }


async def _setup_queue_remove(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    return {"work_queue_id": _str_field(queue, "work_queue_id")}


async def _setup_members_list(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    return {"work_queue_id": _str_field(queue, "work_queue_id")}


async def _setup_member_add(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    return {
        "work_queue_id": _str_field(queue, "work_queue_id"),
        "member": {"actor_kind": "user", "user_id": ctx.system_user2_id},
        "role": "member",
    }


async def _setup_member_remove(ctx: LiveCtx) -> JsonObject:
    queue = await _create_queue(ctx)
    work_queue_id = _str_field(queue, "work_queue_id")
    added = await ctx.client.post(
        f"{_API}/work-queues/{work_queue_id}/members",
        headers=ctx.headers,
        json={"member": {"actor_kind": "user", "user_id": ctx.system_user2_id}, "role": "member"},
    )
    await _expect_json(added, ok=(201,), label="add_member")
    return {
        "work_queue_id": work_queue_id,
        "member": {"actor_kind": "user", "user_id": ctx.system_user2_id},
    }


_CASES: dict[str, OpCase] = {
    "worktracker/work_items/list_requested": OpCase(
        RestMirror("GET", f"{_API}/work-items", "query"),
        _setup_items_list,
        True,
        "exact",
    ),
    "worktracker/work_items/mine_summary_requested": OpCase(
        RestMirror("GET", f"{_API}/work-items/mine/summary", "none"),
        _setup_mine_summary,
        True,
        "summary",
    ),
    "worktracker/work_items/item_requested": OpCase(
        RestMirror("GET", f"{_API}/work-items/{{work_item_id}}", "none"),
        _setup_item_get,
        True,
        "exact",
    ),
    "worktracker/work_items/create_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items", "body_minus_path"),
        _setup_item_create,
        False,
        "normalized",
    ),
    "worktracker/work_items/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/work-items/{{work_item_id}}", "body_minus_path"),
        _setup_item_update,
        False,
        "normalized",
    ),
    "worktracker/work_items/assign_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/assign", "body_minus_path"),
        _setup_item_assign,
        False,
        "normalized",
    ),
    "worktracker/work_items/move_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/move", "body_minus_path"),
        _setup_item_move,
        False,
        "normalized",
    ),
    "worktracker/work_items/claim_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/claim", "none"),
        _setup_item_claim,
        False,
        "normalized",
    ),
    "worktracker/work_items/comment_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/comments", "body_minus_path"),
        _setup_item_comment,
        False,
        "normalized",
    ),
    "worktracker/work_items/comments_list_requested": OpCase(
        RestMirror("GET", f"{_API}/work-items/{{work_item_id}}/comments", "none"),
        _setup_item_comments_list,
        True,
        "exact",
    ),
    "worktracker/work_items/complete_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/complete", "body_minus_path"),
        _setup_item_complete,
        False,
        "normalized",
    ),
    "worktracker/work_items/cancel_requested": OpCase(
        RestMirror("POST", f"{_API}/work-items/{{work_item_id}}/cancel", "none"),
        _setup_item_cancel,
        False,
        "normalized",
    ),
    "worktracker/boards/list_requested": OpCase(
        RestMirror("GET", f"{_API}/boards", "query"),
        _setup_boards_list,
        True,
        "exact",
    ),
    "worktracker/boards/item_requested": OpCase(
        RestMirror("GET", f"{_API}/boards/{{board_id}}", "none"),
        _setup_board_get,
        True,
        "exact",
    ),
    "worktracker/boards/create_requested": OpCase(
        RestMirror("POST", f"{_API}/boards", "body_minus_path"),
        _setup_board_create,
        False,
        "normalized",
    ),
    "worktracker/boards/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/boards/{{board_id}}", "body_minus_path"),
        _setup_board_update,
        False,
        "normalized",
    ),
    "worktracker/work_queues/list_requested": OpCase(
        RestMirror("GET", f"{_API}/work-queues", "query"),
        _setup_queues_list,
        True,
        "named_slug",
    ),
    "worktracker/work_queues/create_requested": OpCase(
        RestMirror("POST", f"{_API}/work-queues", "body_minus_path"),
        _setup_queue_create,
        False,
        "normalized",
    ),
    "worktracker/work_queues/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/work-queues/{{work_queue_id}}", "body_minus_path"),
        _setup_queue_update,
        False,
        "normalized",
    ),
    "worktracker/work_queues/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/work-queues/{{work_queue_id}}", "none"),
        _setup_queue_remove,
        False,
        "normalized",
    ),
    "worktracker/work_queues/members_list_requested": OpCase(
        RestMirror("GET", f"{_API}/work-queues/{{work_queue_id}}/members", "none"),
        _setup_members_list,
        True,
        "exact",
    ),
    "worktracker/work_queues/member_add_requested": OpCase(
        RestMirror("POST", f"{_API}/work-queues/{{work_queue_id}}/members", "body_minus_path"),
        _setup_member_add,
        False,
        "normalized",
    ),
    "worktracker/work_queues/member_remove_requested": OpCase(
        RestMirror("POST", f"{_API}/work-queues/{{work_queue_id}}/members/remove", "body_minus_path"),
        _setup_member_remove,
        False,
        "normalized",
    ),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 15.0,
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
        assert accepted.get("event_id") == event_id
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            event_type = event.get("type")
            if event_type not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    stored = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["type"] == canonical_type
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    terminal = require_json_object(terminal_http.json(), "terminal")
    assert terminal["type"] == terminal_ws["type"]
    assert terminal["meta"]["causation_id"] == event_id
    return terminal_ws


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
) -> JsonObject:
    path_params: dict[str, str] = {}
    for key in _PATH_PLACEHOLDER.findall(rest.url):
        path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body_minus_path":
        body = {k: v for k, v in payload.items() if k not in path_params and v is not None}
        json_body = body if body else None
    elif rest.strategy == "query":
        query = {k: v for k, v in payload.items() if v is not None}
    elif rest.strategy == "none":
        pass
    else:
        raise AssertionError(f"unknown REST strategy {rest.strategy!r}")
    response = await client.request(
        rest.method,
        url,
        headers=headers,
        json=json_body,
        params=query,
    )
    return await _expect_json(
        response,
        ok=(200, 201, 204),
        label=f"REST {rest.method} {url}",
    )


def _assert_compare(
    *,
    mode: CompareMode,
    ws_result: JsonObject,
    rest_result: JsonObject,
    marker: str | None,
    canonical_type: str,
) -> None:
    if mode == "exact":
        assert ws_result == rest_result, (
            f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )
        return
    if mode == "normalized":
        assert _normalize(ws_result) == _normalize(rest_result), (
            f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )
        return
    if mode == "summary":
        for body in (ws_result, rest_result):
            assert isinstance(body.get("assigned_open_count"), int)
            assert isinstance(body.get("queue_inbox_count"), int)
            assert isinstance(body.get("work_queue_ids"), list)
            assert body["assigned_open_count"] >= 1
        return
    if mode == "named_slug":
        if not isinstance(marker, str) or not marker:
            raise AssertionError("named_slug compare requires queue slug marker")
        ws_items = ws_result.get("items")
        rest_items = rest_result.get("items")
        if not isinstance(ws_items, list) or not isinstance(rest_items, list):
            raise AssertionError(f"{canonical_type}: list payload must have items[]")
        ws_row = _row_by_slug(ws_items, marker)
        rest_row = _row_by_slug(rest_items, marker)
        assert ws_row == rest_row, (
            f"WS != REST queue row для {canonical_type}\nWS: {ws_row}\nREST: {rest_row}"
        )
        return
    raise AssertionError(f"unknown compare mode {mode!r}")


def _row_by_slug(items: list[JsonValue], slug: str) -> JsonObject:
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("work_queue_slug") == slug:
            matched.append(require_json_object(item, "queue.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one queue with slug {slug!r}, got {len(matched)}")
    return matched[0]


def test_every_worktracker_operation_has_live_case() -> None:
    missing = sorted(set(WORKTRACKER_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(WORKTRACKER_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_worktracker_op_ws_rest_identical(
    canonical_type: str,
    worktracker_http_service: None,
    realtime_service: None,
    worktracker_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user_id: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    _ = worktracker_http_service, realtime_service
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=worktracker_client_http,
        headers=auth_headers_system,
        unique_id=unique_id,
        suffix="ws",
        system_user_id=system_user_id,
        system_user2_id=system_user2_id,
    )
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
        rest_ctx = LiveCtx(
            client=worktracker_client_http,
            headers=auth_headers_system,
            unique_id=unique_id,
            suffix="rest",
            system_user_id=system_user_id,
            system_user2_id=system_user2_id,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=worktracker_client_http,
        headers=auth_headers_system,
        rest=case.rest,
        payload=rest_payload,
    )
    _assert_compare(
        mode=case.compare,
        ws_result=ws_result,
        rest_result=rest_result,
        marker=rest_marker,
        canonical_type=canonical_type,
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_worktracker_get_missing_failed_terminal(
    worktracker_http_service: None,
    realtime_service: None,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = worktracker_http_service, realtime_service
    event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type="worktracker/work_items/item_requested",
        payload={"work_item_id": f"wi_missing_{unique_id}"},
    )
    assert event["type"] == "worktracker/work_items/item_failed"
    payload = _event_payload(event)
    assert payload["error_code"] == "not_found"


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_worktracker_create_empty_payload_failed_terminal(
    worktracker_http_service: None,
    realtime_service: None,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
) -> None:
    _ = worktracker_http_service, realtime_service
    event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type="worktracker/work_items/create_requested",
        payload={},
    )
    assert event["type"] == "worktracker/work_items/create_failed"
    payload = _event_payload(event)
    assert payload["error_code"] == "ws_invalid_payload"
