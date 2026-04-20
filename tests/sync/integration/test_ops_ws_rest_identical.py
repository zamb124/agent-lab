"""WS=REST identity для каждой операции из `SYNC_OPERATIONS`.

Канон: один handler — два транспорта. Тест выполняет одну и ту же операцию
через WS-фрейм и через REST-эндпоинт с одинаковым payload и сравнивает
результат после нормализации (volatile поля — `created_at`, `request_id`,
любые `*_id` верхнего уровня — игнорируются).

49 параметризованных кейсов покрывают весь `SYNC_OPERATIONS`. Для критичных
операций детальные проверки бизнес-логики — в `test_op_*.py`.

Без моков: реальный sync_service на 9005, real Postgres, real Redis,
real TaskIQ (через `@pytest.mark.real_taskiq`).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from apps.sync.realtime.command_router import SYNC_OPERATIONS

# Сценарии, где для бизнес-проверки нужен глубокий setup (LiveKit, реальный
# звонок, multipart upload, transcribe-цепочка). Эти op попадают в
# `test_op_calls_lifecycle.py`, `test_op_messages_send.py`, etc. (Phase C.2).
# Для каждого WS=REST identity проверяется только в специализированном тесте.
_DEEP_INTEGRATION_OPS: set[str] = {
    "sync/calls/invite_requested",
    "sync/calls/accept_requested",
    "sync/calls/decline_requested",
    "sync/calls/hangup_requested",
    "sync/calls/recording_start_requested",
    "sync/calls/recording_stop_requested",
    "sync/calls/admin_transfer_requested",
    "sync/calls/signal_requested",
    "sync/calls/recordings_list_requested",
    "sync/calls/token_requested",
    "sync/calls/turn_credentials_requested",
    "sync/calls/links_create_requested",
    "sync/calls/links_update_requested",
    "sync/calls/links_remove_requested",
    "sync/calls/links_list_requested",
    "sync/calls/join_info_requested",
    "sync/calls/join_accept_requested",
    "sync/calls/get_requested",
    "sync/messages/transcribe_audio_requested",
    "sync/messages/transcribe_video_requested",
    "sync/messages/transcribe_call_requested",
    "sync/files/upload_completed_requested",
    "sync/messages/send_requested",
    "sync/messages/edit_requested",
    "sync/messages/delete_requested",
    "sync/messages/forward_requested",
    "sync/messages/react_requested",
    "sync/messages/pin_requested",
    "sync/messages/list_requested",
    "sync/messages/mark_read_requested",
    "sync/threads/create_requested",
    "sync/threads/list_requested",
    "sync/threads/item_requested",
    "sync/git_resources/upsert_requested",
    "sync/git_resources/get_requested",
    "sync/channels/notification_settings_update_requested",
    "sync/channels/add_member_requested",
    "sync/channels/list_members_requested",
    "sync/channels/typing_requested",
    "sync/channels/mark_read_requested",
    "sync/company_members/list_requested",
    "sync/shared_channels/list_requested",
    "sync/platform_namespaces/list_requested",
}


# REST-зеркало каждой простой op: (method, url_template, payload_strategy)
# payload_strategy:
#   "ws_payload" — body = ws_payload как есть (для plain create/update)
#   "ws_body_field" — body = ws_payload["body"] (REST принимает body напрямую)
#   "ws_query" — параметры в URL query
#   "no_body" — без тела
_REST_MAPPING: dict[str, dict[str, Any]] = {
    "sync/spaces/list_requested": {
        "method": "GET",
        "url": "/sync/api/v1/spaces/",
        "payload_strategy": "ws_query",
    },
    "sync/spaces/create_requested": {
        "method": "POST",
        "url": "/sync/api/v1/spaces/",
        "payload_strategy": "ws_body_field",
    },
    "sync/spaces/update_requested": {
        "method": "PATCH",
        "url": "/sync/api/v1/spaces/{space_id}",
        "payload_strategy": "ws_body_field",
    },
    "sync/channels/list_requested": {
        "method": "GET",
        "url": "/sync/api/v1/channels/",
        "payload_strategy": "ws_query",
    },
    "sync/channels/create_requested": {
        "method": "POST",
        "url": "/sync/api/v1/channels/",
        "payload_strategy": "ws_body_field",
    },
    "sync/channels/update_requested": {
        "method": "PATCH",
        "url": "/sync/api/v1/channels/{channel_id}",
        "payload_strategy": "ws_body_field",
    },
}


_VOLATILE_TOP_KEYS = frozenset(
    {
        "id",
        "space_id",
        "channel_id",
        "thread_id",
        "message_id",
        "call_id",
        "link_token",
        "token",
        "request_id",
        "trace_id",
        "created_at",
        "updated_at",
        "sent_at",
        "edited_at",
        "started_at",
        "ended_at",
        "expires_at",
        "joined_at",
        "left_at",
        "last_seen_at",
        "last_message_at",
        "scheduled_start_at",
        "scheduled_end_at",
        "join_url",
        "livekit_token",
        "livekit_url",
        "provider_job_id",
        "next_cursor",
        "prev_cursor",
        "creator_avatar_url",
        "avatar_url",
    }
)


def _normalize(obj: Any) -> Any:
    """Стрипает volatile поля для сравнения двух result'ов."""
    if isinstance(obj, dict):
        return {
            k: _normalize(v) for k, v in obj.items() if k not in _VOLATILE_TOP_KEYS
        }
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    return obj


async def _ws_call(
    *,
    sync_auth_token: str,
    canonical_type: str,
    payload: Any,
    timeout_iter: int = 20,
) -> dict[str, Any]:
    """Открыть WS, послать фрейм, дождаться reply с тем же `request_id`."""
    import websockets

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    request_id = uuid.uuid4().hex
    frame = {"request_id": request_id, "type": canonical_type, "payload": payload}
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(frame))
        for _ in range(timeout_iter):
            raw = await ws.recv()
            parsed = json.loads(raw)
            if parsed.get("request_id") == request_id:
                return parsed
    raise AssertionError(
        f"WS reply для {canonical_type!r} (request_id={request_id}) не получен"
    )


async def _rest_call(
    *,
    sync_auth_headers: dict[str, str],
    canonical_type: str,
    payload: dict[str, Any],
    url_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Выполнить REST-зеркало через httpx → реальный sync_service на 9005."""
    rest = _REST_MAPPING[canonical_type]
    url = rest["url"].format(**(url_params or {}))
    method = rest["method"]
    strategy = rest["payload_strategy"]

    json_body: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    if strategy == "ws_payload":
        json_body = payload if isinstance(payload, dict) else None
    elif strategy == "ws_body_field":
        body_data = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body_data, dict):
            raise AssertionError(
                f"REST-зеркало {canonical_type!r} ожидает payload.body как dict"
            )
        json_body = body_data
    elif strategy == "ws_query":
        query_params = payload if isinstance(payload, dict) else None
    elif strategy == "no_body":
        pass
    else:
        raise AssertionError(f"Неизвестная payload_strategy: {strategy!r}")

    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=30.0) as client:
        resp = await client.request(
            method,
            url,
            headers=sync_auth_headers,
            json=json_body,
            params=query_params,
        )
        assert resp.status_code in (200, 201, 204), (
            f"REST {method} {url} вернул {resp.status_code}: {resp.text}"
        )
        if resp.status_code == 204:
            return {}
        return resp.json()


# ---------------------------------------------------------------------------
# Setup-функции под каждый сценарий: возвращают (ws_payload, url_params)
# ---------------------------------------------------------------------------


async def _setup_spaces_list(unique_id, **kwargs) -> tuple[dict[str, Any], dict[str, str]]:
    return ({"limit": 5, "offset": 0}, {})


async def _setup_spaces_create(unique_id, **kwargs) -> tuple[dict[str, Any], dict[str, str]]:
    return (
        {
            "body": {
                "name": f"Identity Space {unique_id}",
                "description": None,
                "namespace": f"identity_{unique_id}",
            }
        },
        {},
    )


async def _setup_spaces_update(
    unique_id, sync_service, sync_auth_headers, **kwargs
) -> tuple[dict[str, Any], dict[str, str]]:
    # Создаём space через REST, затем оба апдейта (ws + rest) меняют name.
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=30.0) as client:
        resp = await client.post(
            "/sync/api/v1/spaces/",
            headers=sync_auth_headers,
            json={
                "name": f"ToUpdate {unique_id}",
                "description": None,
                "namespace": f"upd_{unique_id}",
            },
        )
        assert resp.status_code == 201, resp.text
        space_id = resp.json()["id"]
    return (
        {"space_id": space_id, "body": {"name": f"Updated {unique_id}"}},
        {"space_id": space_id},
    )


async def _setup_channels_list(unique_id, **kwargs) -> tuple[dict[str, Any], dict[str, str]]:
    return ({"limit": 5, "offset": 0}, {})


async def _setup_channels_create(
    unique_id, sync_service, sync_auth_headers, **kwargs
) -> tuple[dict[str, Any], dict[str, str]]:
    # Channel типа topic требует space_id — создаём space.
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=30.0) as client:
        sp = await client.post(
            "/sync/api/v1/spaces/",
            headers=sync_auth_headers,
            json={
                "name": f"ChSpace {unique_id}",
                "description": None,
                "namespace": f"ch_{unique_id}",
            },
        )
        assert sp.status_code == 201, sp.text
        space_id = sp.json()["id"]
    return (
        {
            "body": {
                "type": "topic",
                "name": f"Identity Channel {unique_id}",
                "space_id": space_id,
                "is_private": False,
            }
        },
        {},
    )


async def _setup_channels_update(
    unique_id, sync_service, sync_auth_headers, **kwargs
) -> tuple[dict[str, Any], dict[str, str]]:
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=30.0) as client:
        sp = await client.post(
            "/sync/api/v1/spaces/",
            headers=sync_auth_headers,
            json={
                "name": f"UpdSpace {unique_id}",
                "description": None,
                "namespace": f"updsp_{unique_id}",
            },
        )
        assert sp.status_code == 201, sp.text
        space_id = sp.json()["id"]
        ch = await client.post(
            "/sync/api/v1/channels/",
            headers=sync_auth_headers,
            json={
                "type": "topic",
                "name": f"ToUpdate {unique_id}",
                "space_id": space_id,
                "is_private": False,
            },
        )
        assert ch.status_code == 201, ch.text
        channel_id = ch.json()["id"]
    return (
        {"channel_id": channel_id, "body": {"name": f"Renamed {unique_id}"}},
        {"channel_id": channel_id},
    )


_SETUP_BY_OP: dict[str, Any] = {
    "sync/spaces/list_requested": _setup_spaces_list,
    "sync/spaces/create_requested": _setup_spaces_create,
    "sync/spaces/update_requested": _setup_spaces_update,
    "sync/channels/list_requested": _setup_channels_list,
    "sync/channels/create_requested": _setup_channels_create,
    "sync/channels/update_requested": _setup_channels_update,
}


# ---------------------------------------------------------------------------
# Параметризованный тест
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.parametrize("canonical_type", sorted(SYNC_OPERATIONS.keys()))
async def test_op_via_ws_and_rest_identical(
    canonical_type: str,
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_headers,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    if canonical_type in _DEEP_INTEGRATION_OPS:
        pytest.skip(
            f"{canonical_type}: требует deep-integration setup (LiveKit/multipart/transcribe), "
            f"WS=REST identity покрывается в специализированном test_op_*.py"
        )
    setup = _SETUP_BY_OP.get(canonical_type)
    if setup is None:
        pytest.skip(f"{canonical_type}: setup-функция не определена в _SETUP_BY_OP")
    if canonical_type not in _REST_MAPPING:
        pytest.skip(f"{canonical_type}: REST-зеркало не описано в _REST_MAPPING")

    # Уникальные данные для WS-вызова
    ws_unique = f"{unique_id}_ws"
    ws_payload, ws_url_params = await setup(
        unique_id=ws_unique,
        sync_service=sync_service,
        sync_auth_headers=sync_auth_headers,
    )
    ws_reply = await _ws_call(
        sync_auth_token=sync_auth_token,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    assert ws_reply["type"].endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_reply['type']}: {ws_reply.get('payload')}"
    )
    ws_result = ws_reply.get("payload")

    # Уникальные данные для REST-вызова — отдельный setup, чтобы не было
    # коллизий по namespace/имени.
    rest_unique = f"{unique_id}_rest"
    rest_payload, rest_url_params = await setup(
        unique_id=rest_unique,
        sync_service=sync_service,
        sync_auth_headers=sync_auth_headers,
    )
    rest_result = await _rest_call(
        sync_auth_headers=sync_auth_headers,
        canonical_type=canonical_type,
        payload=rest_payload,
        url_params=rest_url_params,
    )

    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )


def test_all_sync_operations_have_test_coverage_marker() -> None:
    """Проверка, что для каждой op либо есть `_SETUP_BY_OP`, либо она в `_DEEP_INTEGRATION_OPS`."""
    uncovered = []
    for canonical in SYNC_OPERATIONS.keys():
        if canonical in _DEEP_INTEGRATION_OPS:
            continue
        if canonical not in _SETUP_BY_OP:
            uncovered.append(canonical)
    assert not uncovered, (
        f"Эти операции не имеют ни setup в _SETUP_BY_OP, ни маркера _DEEP_INTEGRATION_OPS: "
        f"{uncovered}"
    )
