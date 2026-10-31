"""Live Centrifugo RPC + REST identity для всех RAG_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /rag/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9002.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from httpx2 import AsyncClient, Response

from apps.rag.realtime.command_router import RAG_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.files.chunked_upload_helpers import chunked_upload_file
from tests.rag.helpers import RAG_FILES_API_PREFIX, rag_document_upload_spec_json
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/rag/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)(?=$|\W)")
_VOLATILE_KEYS = frozenset(
    {
        "document_id",
        "task_id",
        "file_id",
        "chunk_id",
        "status",
        "created_at",
        "updated_at",
        "completed_at",
        "request_id",
        "trace_id",
        "service",
        "observability",
    }
)

CompareMode = Literal["exact", "normalized"]
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
    # Снапшот глобального реестра: read-only пара WS/REST переснимается до равного снапшота,
    # иначе параллельные тесты (другие компании/воркеры) меняют выдачу между двумя вызовами.
    eventual: bool = False


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _strip_transport_marker(text: str) -> str:
    return _TRANSPORT_MARKER.sub("", text)


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _strip_transport_marker(text=value)
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


def _ns_name(ctx: LiveCtx, kind: str) -> str:
    return f"ns-{kind}-{ctx.unique_id}-{ctx.suffix}"


async def _create_namespace(ctx: LiveCtx, kind: str) -> str:
    name = _ns_name(ctx, kind)
    response = await ctx.client.post(
        f"{_API}/namespaces",
        headers=ctx.headers,
        json={"name": name, "description": f"live-{kind}-{ctx.suffix}"},
    )
    body = await _expect_json(response, ok=(201,), label="create_namespace")
    return _str_field(body, "name")


async def _ingest_text(ctx: LiveCtx, namespace_id: str, kind: str) -> JsonObject:
    text = f"Live rag {kind} {ctx.unique_id}-{ctx.suffix} document about retrieval."
    response = await ctx.client.post(
        f"{_API}/namespaces/{namespace_id}/ingest-text",
        headers=ctx.headers,
        json={
            "text": text,
            "document_name": f"live-{kind}-{ctx.suffix}.txt",
        },
    )
    return await _expect_json(response, ok=(200,), label="ingest_text")


async def _upload_file(ctx: LiveCtx, namespace_id: str, kind: str) -> str:
    content = f"Live rag file {kind} {ctx.unique_id}-{ctx.suffix}\n".encode()
    upload = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content=content,
        original_name=f"live-{kind}-{ctx.suffix}.txt",
        content_type="text/plain",
        spec_json=rag_document_upload_spec_json(namespace_id),
        files_api_prefix=RAG_FILES_API_PREFIX,
    )
    if upload.status_code != 200:
        raise AssertionError(f"RAG file upload failed: {upload.status_code} {upload.text}")
    return _str_field(_json(upload, "file_upload"), "file_id")


async def _index_file(ctx: LiveCtx, namespace_id: str, file_id: str) -> JsonObject:
    response = await ctx.client.post(
        f"{_API}/namespaces/{namespace_id}/documents/index-file",
        headers=ctx.headers,
        json={"file_id": file_id, "document_name": f"indexed-{ctx.suffix}.txt"},
    )
    return await _expect_json(response, ok=(202,), label="index_file")


async def _await_document_terminal(ctx: LiveCtx, document_id: str) -> None:
    """Ждёт терминальный статус документа — индексация асинхронная, иначе WS/REST видят разные снапшоты."""
    deadline = asyncio.get_running_loop().time() + 30.0
    while asyncio.get_running_loop().time() < deadline:
        response = await ctx.client.get(
            f"{_API}/documents/{document_id}/status", headers=ctx.headers
        )
        body = await _expect_json(response, ok=(200,), label="poll_status")
        if body.get("status") in {"completed", "failed"}:
            return
        await asyncio.sleep(0.25)
    raise AssertionError(f"document {document_id} не дошёл до терминального статуса за 30s")


async def _setup_namespaces_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_namespace(ctx, "list")
    return {"limit": 200, "offset": 0}


async def _setup_namespaces_create(ctx: LiveCtx) -> JsonObject:
    return {"name": _ns_name(ctx, "create"), "description": f"created-{ctx.suffix}"}


async def _setup_namespaces_remove(ctx: LiveCtx) -> JsonObject:
    name = await _create_namespace(ctx, "rmns")
    return {"name": name}


async def _setup_documents_list(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "docs")
    _ = await _ingest_text(ctx, namespace_id, "docs")
    return {"namespace_id": namespace_id, "offset": 0, "limit": 100}


async def _setup_documents_ingest_text(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "ing")
    return {
        "namespace_id": namespace_id,
        "text": f"Ingest live {ctx.unique_id}-{ctx.suffix} about semantic search.",
        "document_name": f"ingest-{ctx.suffix}.txt",
    }


async def _setup_documents_index_file(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "idx")
    file_id = await _upload_file(ctx, namespace_id, "idx")
    return {
        "namespace_id": namespace_id,
        "file_id": file_id,
        "document_name": f"index-{ctx.suffix}.txt",
    }


async def _setup_documents_remove(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "rmdoc")
    ingested = await _ingest_text(ctx, namespace_id, "rmdoc")
    return {
        "namespace_id": namespace_id,
        "document_id": _str_field(ingested, "document_id"),
    }


async def _setup_documents_index_remove(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "rmidx")
    ingested = await _ingest_text(ctx, namespace_id, "rmidx")
    return {
        "namespace_id": namespace_id,
        "document_id": _str_field(ingested, "document_id"),
    }


async def _setup_documents_content(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "cnt")
    ingested = await _ingest_text(ctx, namespace_id, "cnt")
    return {
        "namespace_id": namespace_id,
        "document_id": _str_field(ingested, "document_id"),
    }


async def _setup_documents_status(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "st")
    file_id = await _upload_file(ctx, namespace_id, "st")
    indexed = await _index_file(ctx, namespace_id, file_id)
    document_id = _str_field(indexed, "document_id")
    await _await_document_terminal(ctx, document_id)
    return {"document_id": document_id}


async def _setup_documents_statuses(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "sts")
    file_id = await _upload_file(ctx, namespace_id, "sts")
    indexed = await _index_file(ctx, namespace_id, file_id)
    document_id = _str_field(indexed, "document_id")
    await _await_document_terminal(ctx, document_id)
    return {"document_ids": [document_id]}


async def _setup_search_defaults(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_search_namespace(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "srch")
    _ = await _ingest_text(ctx, namespace_id, "srch")
    return {
        "namespace_id": namespace_id,
        "query": f"Live rag srch {ctx.unique_id} retrieval",
        "limit": 5,
    }


async def _setup_search_global(ctx: LiveCtx) -> JsonObject:
    namespace_id = await _create_namespace(ctx, "gsrch")
    _ = await _ingest_text(ctx, namespace_id, "gsrch")
    return {
        "namespace_ids": [namespace_id],
        "query": f"Live rag gsrch {ctx.unique_id} retrieval",
        "limit": 5,
    }


async def _setup_providers_list(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


_CASES: dict[str, OpCase] = {
    "rag/namespaces/list_requested": OpCase(
        RestMirror("GET", f"{_API}/namespaces", "query"),
        _setup_namespaces_list,
        True,
        "normalized",
        eventual=True,
    ),
    "rag/namespaces/create_requested": OpCase(
        RestMirror("POST", f"{_API}/namespaces", "body_minus_path"),
        _setup_namespaces_create,
        False,
        "normalized",
    ),
    "rag/namespaces/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/namespaces/{{namespace_id}}", "none"),
        _setup_namespaces_remove,
        False,
        "normalized",
    ),
    "rag/documents/list_requested": OpCase(
        RestMirror("GET", f"{_API}/namespaces/{{namespace_id}}/documents", "query"),
        _setup_documents_list,
        True,
        "normalized",
    ),
    "rag/documents/ingest_text_requested": OpCase(
        RestMirror("POST", f"{_API}/namespaces/{{namespace_id}}/ingest-text", "body_minus_path"),
        _setup_documents_ingest_text,
        False,
        "normalized",
    ),
    "rag/documents/index_file_requested": OpCase(
        RestMirror(
            "POST",
            f"{_API}/namespaces/{{namespace_id}}/documents/index-file",
            "body_minus_path",
        ),
        _setup_documents_index_file,
        False,
        "normalized",
    ),
    "rag/documents/remove_requested": OpCase(
        RestMirror(
            "DELETE",
            f"{_API}/namespaces/{{namespace_id}}/documents/{{document_id}}",
            "none",
        ),
        _setup_documents_remove,
        False,
        "normalized",
    ),
    "rag/documents/index_remove_requested": OpCase(
        RestMirror(
            "DELETE",
            f"{_API}/namespaces/{{namespace_id}}/documents/{{document_id}}/index",
            "none",
        ),
        _setup_documents_index_remove,
        False,
        "normalized",
    ),
    "rag/documents/content_requested": OpCase(
        RestMirror(
            "GET",
            f"{_API}/namespaces/{{namespace_id}}/documents/{{document_id}}/content",
            "none",
        ),
        _setup_documents_content,
        True,
        "normalized",
    ),
    "rag/documents/status_requested": OpCase(
        RestMirror("GET", f"{_API}/documents/{{document_id}}/status", "none"),
        _setup_documents_status,
        True,
        "normalized",
    ),
    "rag/documents/statuses_requested": OpCase(
        RestMirror("POST", f"{_API}/documents/statuses", "body_minus_path"),
        _setup_documents_statuses,
        True,
        "normalized",
    ),
    "rag/search/defaults_requested": OpCase(
        RestMirror("GET", f"{_API}/search-defaults", "none"),
        _setup_search_defaults,
        True,
        "normalized",
    ),
    "rag/search/namespace_requested": OpCase(
        RestMirror("POST", f"{_API}/namespaces/{{namespace_id}}/search", "body_minus_path"),
        _setup_search_namespace,
        True,
        "normalized",
    ),
    "rag/search/global_requested": OpCase(
        RestMirror("POST", f"{_API}/search", "body_minus_path"),
        _setup_search_global,
        True,
        "normalized",
    ),
    "rag/providers/list_requested": OpCase(
        RestMirror("GET", f"{_API}/providers", "none"),
        _setup_providers_list,
        True,
        "normalized",
    ),
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
        if key == "namespace_id" and "namespace_id" not in payload:
            path_params[key] = _str_field(payload, "name")
        else:
            path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body_minus_path":
        body = {k: v for k, v in payload.items() if k not in path_params and v is not None}
        json_body = body if body else None
    elif rest.strategy == "query":
        query = {k: v for k, v in payload.items() if k not in path_params and v is not None}
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
        ok=(200, 201, 202, 204),
        label=f"REST {rest.method} {url}",
    )


def test_every_rag_operation_has_live_case() -> None:
    missing = sorted(set(RAG_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(RAG_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(45)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_rag_op_ws_rest_identical(
    canonical_type: str,
    rag_service: None,
    realtime_service: None,
    rag_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = rag_service, realtime_service
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=rag_client_http,
        headers=auth_headers_system,
        unique_id=unique_id,
        suffix="ws",
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
    else:
        rest_ctx = LiveCtx(
            client=rag_client_http,
            headers=auth_headers_system,
            unique_id=unique_id,
            suffix="rest",
        )
        rest_payload = await case.setup(rest_ctx)
    rest_result = await _rest_command(
        client=rag_client_http,
        headers=auth_headers_system,
        rest=case.rest,
        payload=rest_payload,
    )
    if case.eventual:
        attempts = 0
        while _normalize(ws_result) != _normalize(rest_result) and attempts < 5:
            attempts += 1
            await asyncio.sleep(0.25)
            ws_event = await _ws_command(
                auth_token=auth_token_system,
                realtime_session_client=realtime_session_client,
                canonical_type=canonical_type,
                payload=ws_payload,
            )
            assert str(ws_event["type"]).endswith("_succeeded")
            ws_result = _event_payload(ws_event)
            rest_result = await _rest_command(
                client=rag_client_http,
                headers=auth_headers_system,
                rest=case.rest,
                payload=rest_payload,
            )
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_rag_get_missing_failed_terminal(
    rag_service: None,
    realtime_service: None,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = rag_service, realtime_service
    event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type="rag/documents/status_requested",
        payload={"document_id": f"missing_{unique_id}"},
    )
    assert event["type"] == "rag/documents/status_failed"
    payload = _event_payload(event)
    assert payload["error_code"] == "not_found"
