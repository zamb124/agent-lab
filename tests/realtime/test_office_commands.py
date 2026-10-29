"""Live Centrifugo RPC + REST identity для всех OFFICE_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /office/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9008, префикс `/documents/api/v1`.
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

from apps.office.realtime.command_router import OFFICE_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)
from tests.office.helpers import upload_office_file_bytes
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/documents/api/v1"
_NAMESPACE = "default"
_ORIGIN = "http://localhost:9008"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)(?=$|\W)")
_VOLATILE_KEYS = frozenset(
    {
        "catalog_id",
        "parent_catalog_id",
        "file_id",
        "s3_key",
        "share_id",
        "event_id",
        "revision_id",
        "revision_file_id",
        "task_id",
        "initial_task_id",
        "rag_namespace_id",
        "rag_index_updated_at",
        "editor_url",
        "download_url",
        "public_url",
        "share_url",
        "checksum",
        "file_size",
        "created_at",
        "updated_at",
        "expires_at",
        "request_id",
        "trace_id",
        "service",
        "observability",
        "url",
        "token",
    }
)

CompareMode = Literal["normalized", "marker_row"]
PayloadStrategy = Literal["body", "body_minus_path", "query", "none"]
ExpectMode = Literal["succeeded", "failed"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy
    query_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode
    expect: ExpectMode = "succeeded"
    marker_field: str = "title"


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str
    system_user2_id: str
    marker: str | None = None


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _path_field(payload: JsonObject, key: str) -> str:
    """Path-параметр REST: строковый id или целочисленный (`row_id`)."""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | str) or value == "":
        raise AssertionError(f"{key} is required, got {value!r}")
    return str(value)


def _token(ctx: LiveCtx) -> str:
    return f"-{ctx.suffix}-{ctx.unique_id}"


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


async def _create_catalog(
    ctx: LiveCtx,
    *,
    title: str | None = None,
    company_visible: bool = True,
) -> JsonObject:
    name = title if title is not None else f"Live cat {_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/catalogs",
        headers=ctx.headers,
        json={"title": name, "company_visible": company_visible},
    )
    body = await _expect_json(response, ok=(200, 201), label="create_catalog")
    ctx.marker = name
    return body


async def _create_empty_doc(
    ctx: LiveCtx,
    *,
    catalog_id: str,
    title: str | None = None,
    document_type: str = "word",
) -> JsonObject:
    name = title if title is not None else f"Live doc {_token(ctx)}"
    body: JsonObject = {
        "title": name,
        "document_type": document_type,
        "catalog_id": catalog_id,
    }
    response = await ctx.client.post(f"{_API}/documents/empty", headers=ctx.headers, json=body)
    created = await _expect_json(response, ok=(200, 201), label="create_empty")
    ctx.marker = name
    return created


async def _create_file(ctx: LiveCtx, *, filename: str, content: bytes) -> str:
    uploaded = await upload_office_file_bytes(
        ctx.client,
        ctx.headers,
        filename=filename,
        content=content,
        content_type="text/plain",
        namespace=_NAMESPACE,
    )
    file_id = uploaded.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        raise AssertionError("upload file_id is required")
    return file_id


async def _first_template_id(ctx: LiveCtx) -> str:
    response = await ctx.client.get(f"{_API}/namespaces/templates", headers=ctx.headers)
    page = await _expect_json(response, ok=(200,), label="templates")
    items = page.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("office namespace templates are required")
    first = items[0]
    if not isinstance(first, dict):
        raise AssertionError("template item must be object")
    return _str_field(require_json_object(first, "template"), "template_id")


async def _setup_empty(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_namespaces_list(ctx: LiveCtx) -> JsonObject:
    template_id = await _first_template_id(ctx)
    name = f"0n-{_token(ctx)}"
    created = await ctx.client.post(
        f"{_API}/namespaces",
        headers=ctx.headers,
        json={"name": name, "description": f"Live ns {_token(ctx)}", "template_id": template_id},
    )
    await _expect_json(created, ok=(200, 201), label="create_namespace")
    ctx.marker = name
    return {"limit": 1000, "offset": 0}


async def _setup_namespace_create(ctx: LiveCtx) -> JsonObject:
    template_id = await _first_template_id(ctx)
    name = f"n-{_token(ctx)}"
    ctx.marker = name
    return {"name": name, "description": f"Live create {_token(ctx)}", "template_id": template_id}


async def _setup_catalogs_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    ctx.marker = _str_field(created, "title")
    return {}


async def _setup_ensure_path(ctx: LiveCtx) -> JsonObject:
    return {"catalog_path": [f"LivePath{_token(ctx)}"]}


async def _setup_catalog_create(ctx: LiveCtx) -> JsonObject:
    title = f"Live cat create {_token(ctx)}"
    ctx.marker = title
    return {"title": title, "company_visible": True}


async def _setup_catalog_id(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    return {"catalog_id": _str_field(created, "catalog_id")}


async def _setup_catalog_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    title = f"Live cat upd {_token(ctx)}"
    ctx.marker = title
    return {"catalog_id": _str_field(created, "catalog_id"), "title": title}


async def _setup_rag_enable(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    return {"catalog_id": _str_field(created, "catalog_id")}


async def _setup_rag_disable(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    catalog_id = _str_field(created, "catalog_id")
    enabled = await ctx.client.post(
        f"{_API}/catalogs/{catalog_id}/rag-index/enable",
        headers=ctx.headers,
    )
    await _expect_json(enabled, ok=(200,), label="rag_enable")
    return {"catalog_id": catalog_id}


async def _setup_rag_settings(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    catalog_id = _str_field(created, "catalog_id")
    enabled = await ctx.client.post(
        f"{_API}/catalogs/{catalog_id}/rag-index/enable",
        headers=ctx.headers,
    )
    await _expect_json(enabled, ok=(200,), label="rag_enable")
    return {"catalog_id": catalog_id, "include_subcatalogs": True}


async def _setup_rag_search(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    catalog_id = _str_field(created, "catalog_id")
    enabled = await ctx.client.post(
        f"{_API}/catalogs/{catalog_id}/rag-index/enable",
        headers=ctx.headers,
    )
    await _expect_json(enabled, ok=(200,), label="rag_enable")
    return {"catalog_id": catalog_id, "query": f"Live query {_token(ctx)}", "limit": 10}


async def _setup_member_add(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx, company_visible=False)
    return {
        "catalog_id": _str_field(created, "catalog_id"),
        "user_id": ctx.system_user2_id,
        "relation": "viewer",
    }


async def _setup_member_remove(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx, company_visible=False)
    catalog_id = _str_field(created, "catalog_id")
    added = await ctx.client.post(
        f"{_API}/catalogs/{catalog_id}/members",
        headers=ctx.headers,
        json={"user_id": ctx.system_user2_id, "relation": "viewer"},
    )
    await _expect_json(added, ok=(200,), label="member_add")
    return {"catalog_id": catalog_id, "member_user_id": ctx.system_user2_id}


async def _setup_catalog_access_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    return {
        "catalog_id": _str_field(created, "catalog_id"),
        "origin": _ORIGIN,
        "company_visible": True,
        "link_enabled": True,
        "link_permission": "viewer",
    }


async def _setup_catalog_access_rotate(ctx: LiveCtx) -> JsonObject:
    created = await _create_catalog(ctx)
    catalog_id = _str_field(created, "catalog_id")
    patched = await ctx.client.patch(
        f"{_API}/catalogs/{catalog_id}/access",
        headers=ctx.headers,
        json={"link_enabled": True, "link_permission": "viewer"},
    )
    await _expect_json(patched, ok=(200,), label="access_enable")
    return {"catalog_id": catalog_id, "origin": _ORIGIN}


async def _setup_documents_list(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    catalog_id = _str_field(catalog, "catalog_id")
    _ = await _create_empty_doc(ctx, catalog_id=catalog_id)
    return {"catalog_ids": [catalog_id], "sort": "updated_at", "order": "desc"}


async def _setup_create_from_file(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    title = f"Live upload {_token(ctx)}"
    file_id = await _create_file(ctx, filename=f"{title}.txt", content=b"live-office")
    ctx.marker = title
    return {
        "file_id": file_id,
        "title": title,
        "catalog_id": _str_field(catalog, "catalog_id"),
    }


async def _setup_bind(ctx: LiveCtx) -> JsonObject:
    title = f"Live bind {_token(ctx)}"
    file_id = await _create_file(ctx, filename=f"{title}.txt", content=b"live-bind")
    ctx.marker = title
    return {
        "namespace": _NAMESPACE,
        "file_id": file_id,
        "title": title,
        "catalog_path": [f"Bind{_token(ctx)}"],
    }


async def _setup_rag_statuses(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {"file_ids": [_str_field(doc, "file_id")]}


async def _setup_empty_create(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    title = f"Live empty {_token(ctx)}"
    ctx.marker = title
    return {
        "title": title,
        "document_type": "word",
        "catalog_id": _str_field(catalog, "catalog_id"),
    }


async def _setup_file_id(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {"file_id": _str_field(doc, "file_id")}


async def _setup_replace_text(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {
        "file_id": _str_field(doc, "file_id"),
        "find": "zzzz-live-miss",
        "replace": "live",
        "match_case": False,
    }


async def _setup_append_text(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {"file_id": _str_field(doc, "file_id"), "text": f"Live append {_token(ctx)}"}


async def _setup_update_cells(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(
        ctx,
        catalog_id=_str_field(catalog, "catalog_id"),
        document_type="cell",
    )
    return {"file_id": _str_field(doc, "file_id"), "cells": {"A1": f"Live {_token(ctx)}"}}


async def _setup_rename(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    title = f"Live rename {_token(ctx)}"
    ctx.marker = title
    return {"file_id": _str_field(doc, "file_id"), "title": title}


async def _setup_deleted_list(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    file_id = _str_field(doc, "file_id")
    deleted = await ctx.client.delete(f"{_API}/documents/{file_id}", headers=ctx.headers)
    assert deleted.status_code == 204, deleted.text
    return {}


async def _setup_restore(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    file_id = _str_field(doc, "file_id")
    deleted = await ctx.client.delete(f"{_API}/documents/{file_id}", headers=ctx.headers)
    assert deleted.status_code == 204, deleted.text
    return {"file_id": file_id}


async def _setup_permanent_remove(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    file_id = _str_field(doc, "file_id")
    deleted = await ctx.client.delete(f"{_API}/documents/{file_id}", headers=ctx.headers)
    assert deleted.status_code == 204, deleted.text
    return {"file_id": file_id}


async def _setup_move(ctx: LiveCtx) -> JsonObject:
    source = await _create_catalog(ctx, title=f"Live src {_token(ctx)}")
    target = await _create_catalog(ctx, title=f"Live dst {_token(ctx)}")
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(source, "catalog_id"))
    return {
        "file_id": _str_field(doc, "file_id"),
        "catalog_id": _str_field(target, "catalog_id"),
    }


async def _setup_copy(ctx: LiveCtx) -> JsonObject:
    source = await _create_catalog(ctx, title=f"Live copy-src {_token(ctx)}")
    target = await _create_catalog(ctx, title=f"Live copy-dst {_token(ctx)}")
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(source, "catalog_id"))
    title = f"Live copy {_token(ctx)}"
    ctx.marker = title
    return {
        "file_id": _str_field(doc, "file_id"),
        "catalog_id": _str_field(target, "catalog_id"),
        "title": title,
    }


async def _setup_search(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    title = f"LiveSearch{_token(ctx)}"
    _ = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"), title=title)
    ctx.marker = title
    return {"q": title}


async def _setup_document_access_update(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {
        "file_id": _str_field(doc, "file_id"),
        "origin": _ORIGIN,
        "link_enabled": True,
        "link_permission": "viewer",
    }


async def _setup_document_access_rotate(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    file_id = _str_field(doc, "file_id")
    patched = await ctx.client.patch(
        f"{_API}/documents/{file_id}/access",
        headers=ctx.headers,
        json={"link_enabled": True, "link_permission": "viewer"},
    )
    await _expect_json(patched, ok=(200,), label="doc_access_enable")
    return {"file_id": file_id, "origin": _ORIGIN}


async def _setup_share_create(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {
        "file_id": _str_field(doc, "file_id"),
        "origin": _ORIGIN,
        "permission": "viewer",
    }


async def _setup_editor_config(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {"file_id": _str_field(doc, "file_id"), "public_origin": _ORIGIN}


async def _setup_editor_sync(ctx: LiveCtx) -> JsonObject:
    catalog = await _create_catalog(ctx)
    doc = await _create_empty_doc(ctx, catalog_id=_str_field(catalog, "catalog_id"))
    return {"file_id": _str_field(doc, "file_id"), "close": False, "settle_ms": 0, "dirty": False}


async def _setup_share_resolve(ctx: LiveCtx) -> JsonObject:
    share_payload = await _setup_share_create(ctx)
    created = await ctx.client.post(
        f"{_API}/documents/{share_payload['file_id']}/shares",
        headers=ctx.headers,
        json={"permission": "viewer"},
    )
    share = await _expect_json(created, ok=(200, 201), label="share create")
    share_url = _str_field(share, "share_url")
    return {"token": share_url.rstrip("/").rsplit("/", 1)[-1]}


async def _create_data_table(ctx: LiveCtx, *, with_rows: bool = False) -> str:
    created = await ctx.client.post(
        f"{_API}/data-tables",
        headers=ctx.headers,
        json={
            "original_name": f"live-table{_token(ctx)}.sqlite",
            "scope": "office_document",
            "namespace": "default",
            "tables": [
                {
                    "name": "leads",
                    "columns": [
                        {"name": "title", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                    ],
                }
            ],
        },
    )
    payload = await _expect_json(created, ok=(200,), label="create_data_table")
    file_id = _str_field(payload, "file_id")
    if with_rows:
        inserted = await ctx.client.post(
            f"{_API}/data-tables/{file_id}/tables/leads/rows",
            headers=ctx.headers,
            json={"rows": [{"title": "a", "score": 1}, {"title": "b", "score": 2}]},
        )
        _ = await _expect_json(inserted, ok=(200,), label="insert_rows")
    return file_id


async def _setup_data_table_create(ctx: LiveCtx) -> JsonObject:
    return {
        "original_name": f"live-create{_token(ctx)}.sqlite",
        "scope": "office_document",
        "namespace": "default",
        "tables": [{"name": "items", "columns": [{"name": "title", "column_type": "text"}]}],
    }


async def _setup_data_table_get(ctx: LiveCtx) -> JsonObject:
    return {"file_id": await _create_data_table(ctx, with_rows=True)}


async def _setup_data_table_table_create(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx),
        "name": "extra",
        "columns": [{"name": "note", "column_type": "text"}],
    }


async def _setup_data_table_column_add(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx),
        "table_name": "leads",
        "name": "flag",
        "column_type": "boolean",
        "not_null": False,
    }


async def _setup_data_table_rows_list(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx, with_rows=True),
        "table_name": "leads",
        "limit": 10,
        "sort_column": "score",
        "sort_dir": "asc",
    }


async def _setup_data_table_rows_insert(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx),
        "table_name": "leads",
        "rows": [{"title": "c", "score": 3}],
    }


async def _setup_data_table_row_update(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx, with_rows=True),
        "table_name": "leads",
        "row_id": 1,
        "values": {"score": 10},
    }


async def _setup_data_table_rows_delete(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx, with_rows=True),
        "table_name": "leads",
        "row_ids": [1],
    }


async def _setup_data_table_query(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx, with_rows=True),
        "sql": "SELECT title, score FROM leads ORDER BY score",
    }


async def _setup_data_table_export(ctx: LiveCtx) -> JsonObject:
    return {
        "file_id": await _create_data_table(ctx, with_rows=True),
        "table_name": "leads",
        "source_format": "csv",
    }


async def _setup_data_table_import(ctx: LiveCtx) -> JsonObject:
    file_id = await _create_data_table(ctx)
    upload = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content="city,pop\nParis,10\n".encode("utf-8-sig"),
        original_name=f"import{_token(ctx)}.csv",
        content_type="text/csv",
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
        files_api_prefix=f"{_API}/files",
    )
    uploaded = await _expect_json(upload, ok=(200,), label="chunked upload")
    return {
        "file_id": file_id,
        "table_name": "imported",
        "source_format": "csv",
        "upload_file_id": _str_field(uploaded, "file_id"),
    }


async def _setup_data_table_promote(ctx: LiveCtx) -> JsonObject:
    flow_id = f"live-dt-flow{_token(ctx)}"
    created = await ctx.client.post(
        f"{_API}/data-tables",
        headers=ctx.headers,
        json={
            "original_name": f"live-session{_token(ctx)}.sqlite",
            "scope": "flow_session",
            "flow_id": flow_id,
            "session_id": f"{flow_id}:ctx{_token(ctx)}",
            "namespace": "default",
            "tables": [{"name": "leads", "columns": [{"name": "title", "column_type": "text"}]}],
        },
    )
    payload = await _expect_json(created, ok=(200,), label="create_session_data_table")
    return {"file_id": _str_field(payload, "file_id"), "flow_id": flow_id}


async def _setup_templates_list(ctx: LiveCtx) -> JsonObject:
    template_id = f"tmpl-{ctx.unique_id}-{ctx.suffix}"
    response = await ctx.client.post(
        "http://localhost:9003/crm/api/v1/namespaces/templates",
        headers=ctx.headers,
        json={"template_id": template_id, "name": f"Live tmpl {ctx.unique_id}-{ctx.suffix}"},
    )
    _ = await _expect_json(response, ok=(201,), label="create_template")
    ctx.marker = template_id
    return {}


def _op(
    method: str,
    url: str,
    strategy: PayloadStrategy,
    setup: SetupFn,
    *,
    same: bool,
    compare: CompareMode = "normalized",
    expect: ExpectMode = "succeeded",
    marker_field: str = "title",
    query_keys: tuple[str, ...] = (),
) -> OpCase:
    return OpCase(
        RestMirror(method, url, strategy, query_keys),
        setup,
        same,
        compare,
        expect,
        marker_field,
    )


_CASES: dict[str, OpCase] = {
    "office/integration/status_requested": _op(
        "GET", f"{_API}/integration/status", "none", _setup_empty, same=True,
    ),
    "office/namespaces/list_requested": _op(
        "GET", f"{_API}/namespaces", "query", _setup_namespaces_list,
        same=True, compare="marker_row", marker_field="name",
    ),
    "office/namespaces/templates_requested": _op(
        "GET", f"{_API}/namespaces/templates", "none", _setup_templates_list,
        same=True, compare="marker_row", marker_field="template_id",
    ),
    "office/namespaces/create_requested": _op(
        "POST", f"{_API}/namespaces", "body", _setup_namespace_create, same=False,
    ),
    "office/company_members/list_requested": _op(
        "GET", f"{_API}/company-members", "none", _setup_empty, same=True,
    ),
    "office/catalogs/list_requested": _op(
        "GET", f"{_API}/catalogs", "none", _setup_catalogs_list,
        same=True, compare="marker_row",
    ),
    "office/catalogs/ensure_path_requested": _op(
        "POST", f"{_API}/catalogs/ensure-path", "body", _setup_ensure_path, same=False,
    ),
    "office/catalogs/create_requested": _op(
        "POST", f"{_API}/catalogs", "body", _setup_catalog_create, same=False,
    ),
    "office/catalogs/item_requested": _op(
        "GET", f"{_API}/catalogs/{{catalog_id}}", "none", _setup_catalog_id, same=True,
    ),
    "office/catalogs/items_requested": _op(
        "GET", f"{_API}/catalogs/{{catalog_id}}/items", "none", _setup_catalog_id, same=True,
    ),
    "office/catalogs/update_requested": _op(
        "PATCH", f"{_API}/catalogs/{{catalog_id}}", "body_minus_path", _setup_catalog_update, same=False,
    ),
    "office/catalogs/remove_requested": _op(
        "DELETE", f"{_API}/catalogs/{{catalog_id}}", "none", _setup_catalog_id, same=False,
    ),
    "office/catalogs/rag_enable_requested": _op(
        "POST", f"{_API}/catalogs/{{catalog_id}}/rag-index/enable", "none", _setup_rag_enable, same=False,
    ),
    "office/catalogs/rag_disable_requested": _op(
        "POST", f"{_API}/catalogs/{{catalog_id}}/rag-index/disable", "none", _setup_rag_disable, same=False,
    ),
    "office/catalogs/rag_rebuild_requested": _op(
        "POST", f"{_API}/catalogs/{{catalog_id}}/rag-index/rebuild", "none", _setup_rag_disable, same=False,
    ),
    "office/catalogs/rag_status_requested": _op(
        "GET", f"{_API}/catalogs/{{catalog_id}}/rag-index/status", "none", _setup_rag_enable, same=True,
    ),
    "office/catalogs/rag_settings_requested": _op(
        "PATCH",
        f"{_API}/catalogs/{{catalog_id}}/rag-index/settings",
        "body_minus_path",
        _setup_rag_settings,
        same=True,
    ),
    "office/catalogs/rag_search_requested": _op(
        "POST",
        f"{_API}/catalogs/{{catalog_id}}/rag-index/search",
        "body_minus_path",
        _setup_rag_search,
        same=True,
    ),
    "office/catalogs/members_list_requested": _op(
        "GET", f"{_API}/catalogs/{{catalog_id}}/members", "none", _setup_catalog_id, same=True,
    ),
    "office/catalogs/member_add_requested": _op(
        "POST",
        f"{_API}/catalogs/{{catalog_id}}/members",
        "body_minus_path",
        _setup_member_add,
        same=False,
    ),
    "office/catalogs/member_remove_requested": _op(
        "DELETE",
        f"{_API}/catalogs/{{catalog_id}}/members/{{member_user_id}}",
        "none",
        _setup_member_remove,
        same=False,
    ),
    "office/catalogs/access_requested": _op(
        "GET", f"{_API}/catalogs/{{catalog_id}}/access", "none", _setup_catalog_id, same=True,
    ),
    "office/catalogs/access_update_requested": _op(
        "PATCH",
        f"{_API}/catalogs/{{catalog_id}}/access",
        "body_minus_path",
        _setup_catalog_access_update,
        same=True,
    ),
    "office/catalogs/access_rotate_link_requested": _op(
        "POST",
        f"{_API}/catalogs/{{catalog_id}}/access/link/rotate",
        "none",
        _setup_catalog_access_rotate,
        same=True,
    ),
    "office/documents/list_requested": _op(
        "GET", f"{_API}/documents", "query", _setup_documents_list,
        same=True, compare="marker_row",
    ),
    "office/documents/create_from_file_requested": _op(
        "POST", f"{_API}/documents", "body", _setup_create_from_file, same=False,
    ),
    "office/documents/rag_statuses_requested": _op(
        "POST", f"{_API}/documents/rag-index-statuses", "body", _setup_rag_statuses, same=True,
    ),
    "office/documents/empty_requested": _op(
        "POST", f"{_API}/documents/empty", "body", _setup_empty_create, same=False,
    ),
    "office/documents/editor_session_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/editor-session", "none", _setup_file_id, same=True,
    ),
    "office/editor/file_config_requested": _op(
        "GET", f"{_API}/files/{{file_id}}/editor-config", "none", _setup_editor_config, same=True,
    ),
    "office/editor/document_config_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/editor-config", "none", _setup_editor_config, same=True,
    ),
    "office/editor/file_sync_requested": _op(
        "POST", f"{_API}/files/{{file_id}}/sync", "body_minus_path", _setup_editor_sync, same=True,
    ),
    "office/editor/document_sync_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/sync", "body_minus_path", _setup_editor_sync, same=True,
    ),
    "office/document_share/resolve_requested": _op(
        "GET", f"{_API}/shares/{{token}}", "none", _setup_share_resolve, same=True,
    ),
    "office/documents/replace_text_requested": _op(
        "POST",
        f"{_API}/documents/{{file_id}}/mutations/replace-text",
        "body_minus_path",
        _setup_replace_text,
        same=True,
    ),
    "office/documents/append_text_requested": _op(
        "POST",
        f"{_API}/documents/{{file_id}}/mutations/append-text",
        "body_minus_path",
        _setup_append_text,
        same=True,
    ),
    "office/documents/update_cells_requested": _op(
        "POST",
        f"{_API}/documents/{{file_id}}/mutations/update-cells",
        "body_minus_path",
        _setup_update_cells,
        same=True,
    ),
    "office/documents/rename_requested": _op(
        "PATCH", f"{_API}/documents/{{file_id}}", "body_minus_path", _setup_rename, same=False,
    ),
    "office/documents/remove_requested": _op(
        "DELETE", f"{_API}/documents/{{file_id}}", "none", _setup_file_id, same=False,
    ),
    "office/documents/deleted_list_requested": _op(
        "GET", f"{_API}/documents/deleted", "none", _setup_deleted_list,
        same=True, compare="marker_row",
    ),
    "office/documents/restore_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/restore", "none", _setup_restore, same=False,
    ),
    "office/documents/permanent_remove_requested": _op(
        "DELETE", f"{_API}/documents/{{file_id}}/permanent", "none", _setup_permanent_remove, same=False,
    ),
    "office/documents/move_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/move", "body_minus_path", _setup_move, same=False,
    ),
    "office/documents/copy_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/copy", "body_minus_path", _setup_copy, same=False,
    ),
    "office/documents/search_requested": _op(
        "GET", f"{_API}/documents/search", "query", _setup_search,
        same=True, compare="marker_row",
    ),
    "office/documents/access_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/access", "none", _setup_file_id, same=True,
    ),
    "office/documents/access_update_requested": _op(
        "PATCH",
        f"{_API}/documents/{{file_id}}/access",
        "body_minus_path",
        _setup_document_access_update,
        same=True,
    ),
    "office/documents/access_rotate_link_requested": _op(
        "POST",
        f"{_API}/documents/{{file_id}}/access/link/rotate",
        "none",
        _setup_document_access_rotate,
        same=True,
    ),
    "office/documents/preview_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/preview", "none", _setup_file_id, same=True,
    ),
    "office/documents/share_create_requested": _op(
        "POST",
        f"{_API}/documents/{{file_id}}/shares",
        "body_minus_path",
        _setup_share_create,
        same=False,
    ),
    "office/documents/shares_list_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/shares", "none", _setup_file_id, same=True,
    ),
    "office/documents/revisions_list_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/revisions", "none", _setup_file_id, same=True,
    ),
    "office/documents/revision_create_requested": _op(
        "POST", f"{_API}/documents/{{file_id}}/revisions", "none", _setup_file_id, same=False,
    ),
    "office/documents/events_list_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/events", "none", _setup_file_id, same=True,
    ),
    "office/documents/metadata_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/metadata", "none", _setup_file_id, same=True,
    ),
    "office/documents/ai_summary_requested": _op(
        "GET", f"{_API}/documents/{{file_id}}/ai-summary", "none", _setup_file_id, same=True,
    ),
    "office/data_tables/create_requested": _op(
        "POST", f"{_API}/data-tables", "body", _setup_data_table_create, same=False,
    ),
    "office/data_tables/get_requested": _op(
        "GET", f"{_API}/data-tables/{{file_id}}", "none", _setup_data_table_get, same=True,
    ),
    "office/data_tables/promote_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/promote",
        "body_minus_path",
        _setup_data_table_promote,
        same=False,
    ),
    "office/data_tables/table_create_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/tables",
        "body_minus_path",
        _setup_data_table_table_create,
        same=False,
    ),
    "office/data_tables/column_add_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/columns",
        "body_minus_path",
        _setup_data_table_column_add,
        same=False,
    ),
    "office/data_tables/rows_list_requested": _op(
        "GET",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/rows",
        "query",
        _setup_data_table_rows_list,
        same=True,
    ),
    "office/data_tables/rows_insert_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/rows",
        "body_minus_path",
        _setup_data_table_rows_insert,
        same=False,
    ),
    "office/data_tables/row_update_requested": _op(
        "PATCH",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/rows/{{row_id}}",
        "body_minus_path",
        _setup_data_table_row_update,
        same=False,
    ),
    "office/data_tables/rows_delete_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/rows/delete",
        "body_minus_path",
        _setup_data_table_rows_delete,
        same=False,
    ),
    "office/data_tables/query_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/query",
        "body_minus_path",
        _setup_data_table_query,
        same=True,
    ),
    "office/data_tables/export_requested": _op(
        "GET",
        f"{_API}/data-tables/{{file_id}}/tables/{{table_name}}/export",
        "query",
        _setup_data_table_export,
        same=True,
    ),
    "office/data_tables/import_requested": _op(
        "POST",
        f"{_API}/data-tables/{{file_id}}/import",
        "body_minus_path",
        _setup_data_table_import,
        same=False,
    ),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 25.0,
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
            namespace=_NAMESPACE,
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


def _query_params(payload: JsonObject, path_params: dict[str, str]) -> dict[str, JsonValue]:
    query: dict[str, JsonValue] = {}
    for key, value in payload.items():
        if key in path_params or value is None:
            continue
        query[key] = value
    return query


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
    expect: ExpectMode,
) -> JsonObject:
    path_params: dict[str, str] = {}
    for key in _PATH_PLACEHOLDER.findall(rest.url):
        path_params[key] = _path_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    query_keys = set(rest.query_keys)
    if rest.strategy == "body":
        json_body = {k: v for k, v in payload.items() if k != "origin"}
    elif rest.strategy == "body_minus_path":
        body = {
            k: v
            for k, v in payload.items()
            if k not in path_params and k not in query_keys and k != "origin" and v is not None
        }
        json_body = body if body else None
    elif rest.strategy == "query":
        query = _query_params(payload, path_params)
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
    if expect == "failed":
        return await _expect_json(
            response,
            ok=(400, 403, 404, 409, 422),
            label=f"REST {rest.method} {url}",
        )
    return await _expect_json(
        response,
        ok=(200, 201, 202, 204),
        label=f"REST {rest.method} {url}",
    )


def _row_by_marker(payload: JsonObject, field: str, marker: str) -> JsonObject:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("list payload must have items[]")
    matched: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get(field) == marker:
            matched.append(require_json_object(item, "list.row"))
    if len(matched) != 1:
        raise AssertionError(f"expected one row {field}={marker!r}, got {len(matched)}")
    return matched[0]


def test_every_office_operation_has_live_case() -> None:
    missing = sorted(set(OFFICE_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(OFFICE_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(90)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_office_op_ws_rest_identical(
    canonical_type: str,
    office_service: None,
    crm_service: None,
    rag_service: None,
    realtime_service: None,
    frontend_service: None,
    office_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    _ = office_service, crm_service, rag_service, realtime_service, frontend_service
    headers = {
        **auth_headers_system,
        "X-Platform-Namespace": _NAMESPACE,
        "Accept-Language": "ru",
    }
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=office_client_http,
        headers=headers,
        unique_id=unique_id,
        suffix="ws",
        system_user2_id=system_user2_id,
    )
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    if case.expect == "succeeded":
        assert str(ws_event["type"]).endswith("_succeeded"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    else:
        assert str(ws_event["type"]).endswith("_failed"), (
            f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
        )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
        rest_marker = ws_ctx.marker
    else:
        rest_ctx = LiveCtx(
            client=office_client_http,
            headers=headers,
            unique_id=unique_id,
            suffix="rest",
            system_user2_id=system_user2_id,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=office_client_http,
        headers=headers,
        rest=case.rest,
        payload=rest_payload,
        expect=case.expect,
    )
    if case.compare == "marker_row":
        if rest_marker is None:
            raise AssertionError("marker_row compare requires marker")
        assert _normalize(_row_by_marker(ws_result, case.marker_field, rest_marker)) == _normalize(
            _row_by_marker(rest_result, case.marker_field, rest_marker)
        ), f"WS != REST row для {canonical_type}"
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
