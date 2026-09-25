"""Live Centrifugo RPC + REST identity для всех CRM_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /crm/api/internal/realtime/command` → тот же `op_*`.
REST — Granian :9003.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pytest
from httpx import AsyncClient, Response

from apps.crm.realtime.command_router import CRM_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.crm.e2e.attachment_upload_helpers import (
    CRM_FILES_API_PREFIX,
    crm_entity_upload_spec_json,
)
from tests.files.chunked_upload_helpers import chunked_upload_file
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/crm/api/v1"
_NAMESPACE = "default"
_ORIGIN = "http://localhost:9003"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"-(?:ws|rest)(?=$|\W)")
_VOLATILE_KEYS = frozenset(
    {
        "entity_id",
        "relationship_id",
        "grant_id",
        "resource_id",
        "color",
        "access_request_id",
        "suggest_id",
        "task_id",
        "taskiq_task_id",
        "work_item_id",
        "work_item",
        "attachment_id",
        "attachment_ids",
        "document_id",
        "file_id",
        "download_url",
        "authorize_url",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "source_entity_id",
        "target_entity_id",
        "survivor_entity_id",
        "note_id",
        "deleted",
        "progress_pct",
        "stage",
        "source_text_sha256",
        "generated_at",
        "merged_from_entity_id",
        "request_id",
        "trace_id",
        "service",
        "observability",
        "url",
        "s3_key",
        "checksum",
        "file_size",
        "expires_at",
    }
)

CompareMode = Literal["normalized", "error_code", "marker_row"]
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
    marker_field: str = "name"


@dataclass
class LiveCtx:
    client: AsyncClient
    headers: dict[str, str]
    user2_headers: dict[str, str]
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


def _token(ctx: LiveCtx) -> str:
    return f"{ctx.suffix}-{ctx.unique_id}"


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


async def _create_template(ctx: LiveCtx) -> JsonObject:
    template_id = f"tmpl-{_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/namespaces/templates",
        headers=ctx.headers,
        json={"template_id": template_id, "name": f"Live tmpl {ctx.unique_id}-{ctx.suffix}"},
    )
    body = await _expect_json(response, ok=(201,), label="create_template")
    ctx.marker = template_id
    return body


async def _create_namespace(ctx: LiveCtx, *, name: str | None = None) -> JsonObject:
    template = await _create_template(ctx)
    if name is None:
        name = f"n-{_token(ctx)}"
    response = await ctx.client.post(
        f"{_API}/namespaces",
        headers=ctx.headers,
        json={
            "name": name,
            "description": f"Live ns {ctx.unique_id}-{ctx.suffix}",
            "template_id": _str_field(template, "template_id"),
        },
    )
    body = await _expect_json(response, ok=(201,), label="create_namespace")
    ctx.marker = name
    return body


async def _create_entity(
    ctx: LiveCtx,
    *,
    entity_type: str = "contact",
    name: str | None = None,
    namespace: str = _NAMESPACE,
    description: str | None = None,
    headers: dict[str, str] | None = None,
) -> JsonObject:
    title = name if name is not None else f"Live {entity_type} {ctx.unique_id}-{ctx.suffix}"
    body: JsonObject = {"entity_type": entity_type, "name": title, "namespace": namespace}
    if description is not None:
        body["description"] = description
    response = await ctx.client.post(
        f"{_API}/entities",
        headers=headers if headers is not None else ctx.headers,
        json=body,
    )
    return await _expect_json(response, ok=(200, 201), label="create_entity")


async def _create_relationship(
    ctx: LiveCtx,
    source_entity_id: str,
    target_entity_id: str,
    *,
    relationship_type: str = "linked",
    namespace: str = _NAMESPACE,
) -> JsonObject:
    response = await ctx.client.post(
        f"{_API}/relationships",
        headers=ctx.headers,
        json={
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "relationship_type": relationship_type,
            "namespace": namespace,
        },
    )
    return await _expect_json(response, ok=(200, 201), label="create_relationship")


async def _create_public_grant(ctx: LiveCtx, entity_id: str) -> JsonObject:
    response = await ctx.client.post(
        f"{_API}/grants",
        headers=ctx.headers,
        json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "subject": "public",
        },
    )
    return await _expect_json(response, ok=(200, 201), label="create_public_grant")


async def _start_knowledge_import(ctx: LiveCtx, namespace: str) -> JsonObject:
    response = await ctx.client.post(
        f"{_API}/tasks/knowledge-import",
        headers=ctx.headers,
        json={
            "namespace": namespace,
            "mode": "notes_only",
            "source_text": f"Live import {ctx.unique_id}-{ctx.suffix}",
        },
    )
    return await _expect_json(response, ok=(202,), label="knowledge_import")


async def _upload_file_id(ctx: LiveCtx, entity: JsonObject) -> str:
    entity_id = _str_field(entity, "entity_id")
    entity_type = _str_field(entity, "entity_type")
    title = _str_field(entity, "name")
    content = f"Live crm file {ctx.unique_id}-{ctx.suffix}\n".encode()
    uploaded = await chunked_upload_file(
        ctx.client,
        ctx.headers,
        content=content,
        original_name=f"live-{ctx.suffix}.txt",
        content_type="text/plain",
        spec_json=crm_entity_upload_spec_json(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_title=title,
        ),
        files_api_prefix=CRM_FILES_API_PREFIX,
    )
    if uploaded.status_code != 200:
        raise AssertionError(f"CRM file upload failed: {uploaded.status_code} {uploaded.text}")
    return _str_field(_json(uploaded, "file_upload"), "file_id")


async def _setup_offset_page(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"limit": 200, "offset": 0}


async def _setup_namespaces_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx, name=f"0n-{_token(ctx)}")
    ctx.marker = _str_field(created, "name")
    return {"limit": 200, "offset": 0}


async def _setup_namespace_create(ctx: LiveCtx) -> JsonObject:
    template = await _create_template(ctx)
    name = f"n-{_token(ctx)}"
    ctx.marker = name
    return {
        "name": name,
        "description": f"Live create ns {ctx.unique_id}-{ctx.suffix}",
        "template_id": _str_field(template, "template_id"),
    }


async def _setup_namespace_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "name": _str_field(created, "name"),
        "description": f"Live ns updated {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_namespace_name(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {"name": _str_field(created, "name")}


async def _setup_lara_summary(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {"namespace": _str_field(created, "name")}


async def _setup_templates_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_template(ctx)
    ctx.marker = _str_field(created, "template_id")
    return {"limit": 200, "offset": 0}


async def _setup_template_item(ctx: LiveCtx) -> JsonObject:
    created = await _create_template(ctx)
    return {"template_id": _str_field(created, "template_id")}


async def _setup_template_create(ctx: LiveCtx) -> JsonObject:
    template_id = f"tmpl-{_token(ctx)}"
    ctx.marker = template_id
    return {"template_id": template_id, "name": f"Live tmpl create {ctx.unique_id}-{ctx.suffix}"}


async def _setup_template_update(ctx: LiveCtx) -> JsonObject:
    created = await _create_template(ctx)
    return {
        "template_id": _str_field(created, "template_id"),
        "name": f"Live tmpl done {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_template_type_upsert(ctx: LiveCtx) -> JsonObject:
    created = await _create_template(ctx)
    type_id = f"t-{_token(ctx)}"
    return {
        "template_id": _str_field(created, "template_id"),
        "type_id": type_id,
        "name": f"Live type {ctx.unique_id}-{ctx.suffix}",
        "required_fields": {},
        "optional_fields": {},
        "namespace_ids": [],
    }


async def _setup_template_type_remove(ctx: LiveCtx) -> JsonObject:
    created = await _create_template(ctx)
    template_id = _str_field(created, "template_id")
    for type_id, name in (("note", "Note"), ("task", "Task")):
        seed = await ctx.client.post(
            f"{_API}/namespaces/templates/{template_id}/types",
            headers=ctx.headers,
            json={
                "type_id": type_id,
                "name": name,
                "required_fields": {},
                "optional_fields": {},
                "namespace_ids": [],
            },
        )
        await _expect_json(seed, ok=(200, 201), label=f"template_type_seed_{type_id}")
    type_id = f"t-{_token(ctx)}"
    upsert = await ctx.client.post(
        f"{_API}/namespaces/templates/{template_id}/types",
        headers=ctx.headers,
        json={
            "type_id": type_id,
            "name": f"Live drop type {ctx.unique_id}-{ctx.suffix}",
            "required_fields": {},
            "optional_fields": {},
            "namespace_ids": [],
        },
    )
    await _expect_json(upsert, ok=(201,), label="template_type_upsert")
    return {"template_id": template_id, "type_id": type_id}


async def _setup_entity_types_list(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_entity_type_create(ctx)
    created = await ctx.client.post(f"{_API}/entity-types", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="entity_type_create")
    ctx.marker = _str_field(body, "type_id")
    return {"namespace": _str_field(body, "namespace"), "limit": 200, "offset": 0}


async def _setup_entity_type_item(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"type_id": "contact", "namespace": _NAMESPACE}


async def _setup_entity_type_create(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    type_id = f"t-{_token(ctx)}"
    return {
        "type_id": type_id,
        "namespace": _str_field(created, "name"),
        "name": f"Live et {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_entity_type_update(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_entity_type_create(ctx)
    created = await ctx.client.post(f"{_API}/entity-types", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="entity_type_create")
    return {
        "type_id": _str_field(body, "type_id"),
        "namespace": _str_field(body, "namespace"),
        "description": f"Live et upd {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_entity_type_public_fields(ctx: LiveCtx) -> JsonObject:
    payload = await _setup_entity_type_create(ctx)
    created = await ctx.client.post(f"{_API}/entity-types", headers=ctx.headers, json=payload)
    body = await _expect_json(created, ok=(200, 201), label="entity_type_create")
    return {
        "type_id": _str_field(body, "type_id"),
        "namespace": _str_field(body, "namespace"),
        "public_fields": ["name"],
    }


async def _setup_grants_list(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    entity_id = _str_field(entity, "entity_id")
    _ = await _create_public_grant(ctx, entity_id)
    return {
        "resource_type": "entity",
        "resource_id": entity_id,
        "limit": 200,
        "offset": 0,
    }


async def _setup_grants_create(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {
        "resource_type": "entity",
        "resource_id": _str_field(entity, "entity_id"),
        "subject": "public",
    }


async def _setup_grants_item(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    grant = await _create_public_grant(ctx, _str_field(entity, "entity_id"))
    return {"grant_id": _str_field(grant, "grant_id")}


async def _setup_entity_create(ctx: LiveCtx) -> JsonObject:
    return {
        "entity_type": "contact",
        "name": f"Live contact {ctx.unique_id}-{ctx.suffix}",
        "namespace": _NAMESPACE,
    }


async def _setup_entity_id(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_id": _str_field(entity, "entity_id")}


async def _setup_entity_update(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {
        "entity_id": _str_field(entity, "entity_id"),
        "description": f"Live upd {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_entity_query(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {
        "query": _str_field(entity, "name"),
        "search_mode": "text",
        "namespace": _NAMESPACE,
        "limit": 50,
    }


async def _setup_mentions(ctx: LiveCtx) -> JsonObject:
    name = f"Mention{_token(ctx)}"
    entity = await _create_entity(ctx, name=name)
    ctx.marker = _str_field(entity, "name")
    return {"text": f"hello @{name}", "namespace": _NAMESPACE}


async def _setup_merge(ctx: LiveCtx) -> JsonObject:
    survivor = await _create_entity(ctx, name=f"Survivor {ctx.unique_id}-{ctx.suffix}")
    source = await _create_entity(ctx, name=f"Source {ctx.unique_id}-{ctx.suffix}")
    return {
        "survivor_entity_id": _str_field(survivor, "entity_id"),
        "source_entity_id": _str_field(source, "entity_id"),
        "scalar_choices": {"name": "survivor"},
    }


async def _setup_bulk_create(ctx: LiveCtx) -> JsonObject:
    return {
        "items": [
            {
                "entity_type": "contact",
                "name": f"Live bulk {ctx.unique_id}-{ctx.suffix}",
                "namespace": _NAMESPACE,
            }
        ]
    }


async def _setup_bulk_update(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {
        "items": [
            {
                "entity_id": _str_field(entity, "entity_id"),
                "updates": {"description": f"bulk {ctx.unique_id}-{ctx.suffix}"},
            }
        ]
    }


async def _setup_bulk_delete(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_ids": [_str_field(entity, "entity_id")]}


async def _setup_aggregate(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"namespace": _NAMESPACE}


async def _setup_entities_export(ctx: LiveCtx) -> JsonObject:
    _ = await _create_entity(ctx)
    return {"namespace": _NAMESPACE, "export_format": "csv", "entity_type": "note", "limit": 50}


async def _setup_cards_bulk(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_ids": [_str_field(entity, "entity_id")]}


async def _setup_empty(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_company_init(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"company_id": "system"}


async def _setup_timeline(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {"namespace": _str_field(created, "name")}


async def _setup_overview_graph(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_ids": [_str_field(entity, "entity_id")], "max_depth": 2}


async def _setup_influence(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_id": _str_field(entity, "entity_id"), "max_depth": 2}


async def _setup_related(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    return {"entity_id": _str_field(entity, "entity_id"), "direction": "both"}


async def _setup_note_id(ctx: LiveCtx) -> JsonObject:
    note = await _create_entity(
        ctx,
        entity_type="note",
        name=f"Live note {ctx.unique_id}-{ctx.suffix}",
        description=f"Live note body {ctx.unique_id}-{ctx.suffix}",
    )
    return {"note_id": _str_field(note, "entity_id")}


async def _setup_exclusive_related(ctx: LiveCtx) -> JsonObject:
    note = await _create_entity(
        ctx,
        entity_type="note",
        name=f"Live excl {ctx.unique_id}-{ctx.suffix}",
    )
    return {"entity_id": _str_field(note, "entity_id")}


async def _setup_draft_save(ctx: LiveCtx) -> JsonObject:
    note = await _setup_note_id(ctx)
    return {**note, "expected_version": 0}


async def _setup_analyze(ctx: LiveCtx) -> JsonObject:
    note = await _setup_note_id(ctx)
    return {"note_id": note["note_id"], "mode": "analyze", "include_attachments": False}


async def _setup_path(ctx: LiveCtx) -> JsonObject:
    left = await _create_entity(ctx, name=f"Path A {ctx.unique_id}-{ctx.suffix}")
    right = await _create_entity(ctx, name=f"Path B {ctx.unique_id}-{ctx.suffix}")
    _ = await _create_relationship(
        ctx, _str_field(left, "entity_id"), _str_field(right, "entity_id")
    )
    return {
        "source_entity_id": _str_field(left, "entity_id"),
        "target_entity_id": _str_field(right, "entity_id"),
        "max_depth": 5,
        "namespace": _NAMESPACE,
    }


async def _setup_relationships_list(ctx: LiveCtx) -> JsonObject:
    left = await _create_entity(ctx, name=f"Rel A {ctx.unique_id}-{ctx.suffix}")
    right = await _create_entity(ctx, name=f"Rel B {ctx.unique_id}-{ctx.suffix}")
    rel = await _create_relationship(
        ctx, _str_field(left, "entity_id"), _str_field(right, "entity_id")
    )
    ctx.marker = _str_field(rel, "relationship_id")
    return {
        "entity_id": _str_field(left, "entity_id"),
        "namespace": _NAMESPACE,
        "limit": 200,
    }


async def _setup_relationship_item(ctx: LiveCtx) -> JsonObject:
    left = await _create_entity(ctx, name=f"Rel get A {ctx.unique_id}-{ctx.suffix}")
    right = await _create_entity(ctx, name=f"Rel get B {ctx.unique_id}-{ctx.suffix}")
    rel = await _create_relationship(
        ctx, _str_field(left, "entity_id"), _str_field(right, "entity_id")
    )
    return {"relationship_id": _str_field(rel, "relationship_id")}


async def _setup_relationship_create(ctx: LiveCtx) -> JsonObject:
    left = await _create_entity(ctx, name=f"Rel c A {ctx.unique_id}-{ctx.suffix}")
    right = await _create_entity(ctx, name=f"Rel c B {ctx.unique_id}-{ctx.suffix}")
    return {
        "source_entity_id": _str_field(left, "entity_id"),
        "target_entity_id": _str_field(right, "entity_id"),
        "relationship_type": "linked",
        "namespace": _NAMESPACE,
    }


async def _setup_rel_type_create(ctx: LiveCtx) -> JsonObject:
    type_id = f"rel-{_token(ctx)}"
    return {"type_id": type_id, "name": f"Live rel {ctx.unique_id}-{ctx.suffix}"}


async def _setup_suggests_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace": _str_field(created, "name"),
        "status": "pending",
        "limit": 50,
        "offset": 0,
    }


async def _setup_suggest_missing(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace": _str_field(created, "name"),
        "suggest_id": f"sug_missing_{ctx.unique_id}_{ctx.suffix}",
    }


async def _setup_access_list(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"limit": 100, "offset": 0}


async def _setup_access_create(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(
        ctx,
        name=f"Access tgt {ctx.unique_id}-{ctx.suffix}",
        headers=ctx.user2_headers,
    )
    return {
        "resource_type": "entity",
        "resource_id": _str_field(entity, "entity_id"),
        "message": f"Live access {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_access_item(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx, name=f"Access own {ctx.unique_id}-{ctx.suffix}")
    created = await ctx.client.post(
        f"{_API}/access-requests",
        headers=ctx.user2_headers,
        json={
            "resource_type": "entity",
            "resource_id": _str_field(entity, "entity_id"),
            "message": f"Live ar {ctx.unique_id}-{ctx.suffix}",
        },
    )
    body = await _expect_json(created, ok=(200, 201), label="access_create")
    return {"access_request_id": _str_field(body, "access_request_id")}


async def _setup_access_update(ctx: LiveCtx) -> JsonObject:
    item = await _setup_access_item(ctx)
    return {**item, "status": "rejected"}


async def _setup_daily_summary(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"date": date(2026, 9, 20).isoformat(), "namespace": _NAMESPACE, "force_rebuild": False}


async def _setup_period_summary(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {
        "date_from": "2026-09-01",
        "date_to": "2026-09-20",
        "namespace": _NAMESPACE,
        "force_rebuild": False,
    }


async def _setup_daily_summary_start(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace": _str_field(created, "name"),
        "date_str": "2026-09-20",
        "reason": "manual",
    }


async def _setup_period_summary_start(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace": _str_field(created, "name"),
        "date_from": "2026-09-01",
        "date_to": "2026-09-20",
        "reason": "manual",
    }


async def _setup_tasks_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    namespace = _str_field(created, "name")
    task = await _start_knowledge_import(ctx, namespace)
    ctx.marker = _str_field(task, "task_id")
    return {"namespace": namespace, "limit": 50, "offset": 0}


async def _setup_task_item(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    task = await _start_knowledge_import(ctx, _str_field(created, "name"))
    return {"task_id": _str_field(task, "task_id")}


async def _setup_task_missing(ctx: LiveCtx) -> JsonObject:
    return {"task_id": f"missing-{ctx.unique_id}"}


async def _setup_knowledge_import(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace": _str_field(created, "name"),
        "mode": "notes_only",
        "source_text": f"Live ki {ctx.unique_id}-{ctx.suffix}",
    }


async def _setup_activity_create(ctx: LiveCtx) -> JsonObject:
    return {
        "title": f"Live activity {ctx.unique_id}-{ctx.suffix}",
        "namespace": _NAMESPACE,
        "priority": "normal",
    }


async def _setup_activity_list(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"namespace": _NAMESPACE, "limit": 50, "offset": 0}


async def _setup_attachments_list(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    file_id = await _upload_file_id(ctx, entity)
    attach = await ctx.client.post(
        f"{_API}/entities/{_str_field(entity, 'entity_id')}/attachments",
        headers=ctx.headers,
        json={"file_id": file_id},
    )
    await _expect_json(attach, ok=(200, 201), label="attach")
    return {"entity_id": _str_field(entity, "entity_id")}


async def _setup_attachments_attach(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    file_id = await _upload_file_id(ctx, entity)
    return {"entity_id": _str_field(entity, "entity_id"), "file_id": file_id}


async def _setup_attachments_remove(ctx: LiveCtx) -> JsonObject:
    entity = await _create_entity(ctx)
    entity_id = _str_field(entity, "entity_id")
    file_id = await _upload_file_id(ctx, entity)
    attach = await ctx.client.post(
        f"{_API}/entities/{entity_id}/attachments",
        headers=ctx.headers,
        json={"file_id": file_id},
    )
    body = await _expect_json(attach, ok=(200, 201), label="attach")
    attachment_id = body.get("document_id")
    if not isinstance(attachment_id, str) or not attachment_id:
        attachment_id = file_id
    return {"entity_id": entity_id, "attachment_id": attachment_id}


async def _setup_integrations_list(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {"namespace_name": _str_field(created, "name")}


async def _setup_integration_authorize(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace_name": _str_field(created, "name"),
        "provider_id": "amocrm",
        "subdomain": "livecrm",
        "return_path": "/crm/namespaces",
        "return_origin": _ORIGIN,
        "accept_language": "ru",
        "brand_host": "localhost:9003",
    }


async def _setup_integration_auto_sync(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace_name": _str_field(created, "name"),
        "provider_id": "amocrm",
        "auto_sync_enabled": False,
    }


async def _setup_integration_auto_note(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace_name": _str_field(created, "name"),
        "provider_id": "amocrm",
        "auto_note_ai_analyze": False,
    }


async def _setup_integration_sync(ctx: LiveCtx) -> JsonObject:
    created = await _create_namespace(ctx)
    return {
        "namespace_name": _str_field(created, "name"),
        "provider_id": "amocrm",
    }


def _op(
    method: str,
    url: str,
    strategy: PayloadStrategy,
    setup: SetupFn,
    *,
    same: bool,
    compare: CompareMode = "normalized",
    expect: ExpectMode = "succeeded",
    marker_field: str = "name",
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
    "crm/company/init_requested": _op(
        "POST", f"{_API}/internal/company/init", "body_minus_path", _setup_company_init, same=True,
    ),
    "crm/namespaces/list_requested": _op(
        "GET", f"{_API}/namespaces", "query", _setup_namespaces_list,
        same=True, compare="marker_row", marker_field="name",
    ),
    "crm/namespaces/create_requested": _op(
        "POST", f"{_API}/namespaces", "body_minus_path", _setup_namespace_create, same=False,
    ),
    "crm/namespaces/update_requested": _op(
        "PUT", f"{_API}/namespaces/{{name}}", "body_minus_path", _setup_namespace_update, same=False,
    ),
    "crm/namespaces/editability_requested": _op(
        "GET", f"{_API}/namespaces/{{name}}/editability", "none", _setup_namespace_name, same=True,
    ),
    "crm/namespaces/lara_summary_requested": _op(
        "GET", f"{_API}/namespaces/lara-summary", "query", _setup_lara_summary, same=True,
    ),
    "crm/templates/list_requested": _op(
        "GET", f"{_API}/namespaces/templates", "query", _setup_templates_list,
        same=True, compare="marker_row", marker_field="template_id",
    ),
    "crm/templates/item_requested": _op(
        "GET", f"{_API}/namespaces/templates/{{template_id}}", "none", _setup_template_item, same=True,
    ),
    "crm/templates/create_requested": _op(
        "POST", f"{_API}/namespaces/templates", "body_minus_path", _setup_template_create, same=False,
    ),
    "crm/templates/update_requested": _op(
        "PUT",
        f"{_API}/namespaces/templates/{{template_id}}",
        "body_minus_path",
        _setup_template_update,
        same=False,
    ),
    "crm/templates/remove_requested": _op(
        "DELETE",
        f"{_API}/namespaces/templates/{{template_id}}",
        "none",
        _setup_template_item,
        same=False,
    ),
    "crm/templates/schema_options_requested": _op(
        "GET", f"{_API}/namespaces/templates/schema/options", "none", _setup_empty, same=True,
    ),
    "crm/templates/type_upsert_requested": _op(
        "POST",
        f"{_API}/namespaces/templates/{{template_id}}/types",
        "body_minus_path",
        _setup_template_type_upsert,
        same=False,
    ),
    "crm/templates/type_remove_requested": _op(
        "DELETE",
        f"{_API}/namespaces/templates/{{template_id}}/types/{{type_id}}",
        "none",
        _setup_template_type_remove,
        same=False,
    ),
    "crm/entity_types/list_requested": _op(
        "GET", f"{_API}/entity-types", "query", _setup_entity_types_list,
        same=True, compare="marker_row", marker_field="type_id",
    ),
    "crm/entity_types/item_requested": _op(
        "GET", f"{_API}/entity-types/{{type_id}}", "query", _setup_entity_type_item, same=True,
    ),
    "crm/entity_types/create_requested": _op(
        "POST", f"{_API}/entity-types", "body_minus_path", _setup_entity_type_create, same=False,
    ),
    "crm/entity_types/update_requested": _op(
        "PUT",
        f"{_API}/entity-types/{{type_id}}",
        "body_minus_path",
        _setup_entity_type_update,
        same=False,
        query_keys=("namespace",),
    ),
    "crm/entity_types/public_fields_requested": _op(
        "PUT",
        f"{_API}/entity-types/{{type_id}}/public-fields",
        "body",
        _setup_entity_type_public_fields,
        same=True,
    ),
    "crm/grants/list_requested": _op(
        "GET", f"{_API}/grants", "query", _setup_grants_list, same=True,
    ),
    "crm/grants/create_requested": _op(
        "POST", f"{_API}/grants", "body", _setup_grants_create, same=True,
    ),
    "crm/grants/item_requested": _op(
        "GET", f"{_API}/grants/{{grant_id}}", "none", _setup_grants_item, same=True,
    ),
    "crm/grants/remove_requested": _op(
        "DELETE", f"{_API}/grants/{{grant_id}}", "none", _setup_grants_item, same=False,
    ),
    "crm/entities/create_requested": _op(
        "POST", f"{_API}/entities", "body_minus_path", _setup_entity_create, same=False,
    ),
    "crm/entities/item_requested": _op(
        "GET", f"{_API}/entities/{{entity_id}}", "none", _setup_entity_id, same=True,
    ),
    "crm/entities/update_requested": _op(
        "PUT", f"{_API}/entities/{{entity_id}}", "body_minus_path", _setup_entity_update, same=False,
    ),
    "crm/entities/remove_requested": _op(
        "DELETE", f"{_API}/entities/{{entity_id}}", "none", _setup_entity_id, same=False,
    ),
    "crm/entities/query_requested": _op(
        "POST", f"{_API}/entities/query", "body_minus_path", _setup_entity_query, same=True,
    ),
    "crm/entities/mentions_search_requested": _op(
        "POST",
        f"{_API}/entities/search/mentions",
        "body_minus_path",
        _setup_mentions,
        same=True,
        compare="marker_row",
        marker_field="name",
    ),
    "crm/entities/merge_requested": _op(
        "POST", f"{_API}/entities/merge", "body_minus_path", _setup_merge, same=False,
    ),
    "crm/entities/bulk_create_requested": _op(
        "POST", f"{_API}/entities/bulk", "body_minus_path", _setup_bulk_create, same=False,
    ),
    "crm/entities/bulk_update_requested": _op(
        "PUT", f"{_API}/entities/bulk", "body_minus_path", _setup_bulk_update, same=False,
    ),
    "crm/entities/bulk_delete_requested": _op(
        "POST", f"{_API}/entities/bulk-delete", "body_minus_path", _setup_bulk_delete, same=False,
    ),
    "crm/entities/card_requested": _op(
        "GET", f"{_API}/entities/{{entity_id}}/card", "none", _setup_entity_id, same=True,
    ),
    "crm/entities/aggregate_requested": _op(
        "GET", f"{_API}/entities/aggregate", "query", _setup_aggregate, same=True,
    ),
    "crm/entities/export_requested": _op(
        "GET", f"{_API}/entities/export", "query", _setup_entities_export, same=True,
    ),
    "crm/entities/cards_bulk_requested": _op(
        "POST", f"{_API}/entities/cards/bulk", "body_minus_path", _setup_cards_bulk, same=True,
    ),
    "crm/notes/analysis_draft_save_requested": _op(
        "PATCH",
        f"{_API}/entities/notes/{{note_id}}/analysis-draft",
        "body_minus_path",
        _setup_draft_save,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/notes/analysis_draft_discard_requested": _op(
        "DELETE",
        f"{_API}/entities/notes/{{note_id}}/analysis-draft",
        "none",
        _setup_note_id,
        same=True,
    ),
    "crm/notes/analysis_error_dismiss_requested": _op(
        "DELETE",
        f"{_API}/entities/notes/{{note_id}}/analysis-error",
        "none",
        _setup_note_id,
        same=True,
    ),
    "crm/notes/analysis_draft_repair_requested": _op(
        "POST",
        f"{_API}/entities/notes/{{note_id}}/analysis-draft-repair",
        "none",
        _setup_note_id,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/notes/markdown_format_requested": _op(
        "POST",
        f"{_API}/entities/notes/{{note_id}}/format-markdown",
        "none",
        _setup_note_id,
        same=False,
    ),
    "crm/notes/analyze_requested": _op(
        "POST", f"{_API}/tasks/note-analyze", "body_minus_path", _setup_analyze, same=False,
    ),
    "crm/entities/person_self_requested": _op(
        "GET", f"{_API}/entities/person-entity/self", "none", _setup_empty, same=True,
    ),
    "crm/entities/timeline_bounds_requested": _op(
        "GET", f"{_API}/entities/timeline/bounds", "query", _setup_timeline, same=True,
    ),
    "crm/entities/overview_graph_requested": _op(
        "POST",
        f"{_API}/entities/overview-graph",
        "body_minus_path",
        _setup_overview_graph,
        same=True,
    ),
    "crm/entities/influence_graph_requested": _op(
        "GET",
        f"{_API}/entities/{{entity_id}}/influence-graph",
        "query",
        _setup_influence,
        same=True,
    ),
    "crm/entities/related_requested": _op(
        "GET", f"{_API}/entities/{{entity_id}}/related", "query", _setup_related, same=True,
    ),
    "crm/entities/relationships_requested": _op(
        "GET",
        f"{_API}/entities/{{entity_id}}/relationships",
        "none",
        _setup_entity_id,
        same=True,
    ),
    "crm/entities/exclusive_related_requested": _op(
        "GET",
        f"{_API}/entities/{{entity_id}}/exclusive-related",
        "none",
        _setup_exclusive_related,
        same=True,
    ),
    "crm/relationships/path_requested": _op(
        "GET", f"{_API}/relationships/path/", "query", _setup_path, same=True,
    ),
    "crm/relationships/list_requested": _op(
        "GET", f"{_API}/relationships", "query", _setup_relationships_list,
        same=True, compare="marker_row", marker_field="relationship_id",
    ),
    "crm/relationships/item_requested": _op(
        "GET",
        f"{_API}/relationships/{{relationship_id}}",
        "none",
        _setup_relationship_item,
        same=True,
    ),
    "crm/relationships/create_requested": _op(
        "POST",
        f"{_API}/relationships",
        "body_minus_path",
        _setup_relationship_create,
        same=False,
    ),
    "crm/relationships/remove_requested": _op(
        "DELETE",
        f"{_API}/relationships/{{relationship_id}}",
        "none",
        _setup_relationship_item,
        same=False,
    ),
    "crm/relationship_types/list_requested": _op(
        "GET", f"{_API}/relationships/types/", "query", _setup_offset_page, same=True,
    ),
    "crm/relationship_types/create_requested": _op(
        "POST",
        f"{_API}/relationships/types/",
        "body_minus_path",
        _setup_rel_type_create,
        same=False,
    ),
    "crm/suggests/list_requested": _op(
        "GET", f"{_API}/namespaces/{{namespace}}/suggests", "query", _setup_suggests_list, same=True,
    ),
    "crm/suggests/resolve_requested": _op(
        "POST",
        f"{_API}/namespaces/{{namespace}}/suggests/{{suggest_id}}/resolve",
        "none",
        _setup_suggest_missing,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/suggests/dismiss_requested": _op(
        "POST",
        f"{_API}/namespaces/{{namespace}}/suggests/{{suggest_id}}/dismiss",
        "none",
        _setup_suggest_missing,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/access_requests/list_requested": _op(
        "GET", f"{_API}/access-requests", "query", _setup_access_list, same=True,
    ),
    "crm/access_requests/create_requested": _op(
        "POST", f"{_API}/access-requests", "body_minus_path", _setup_access_create, same=False,
    ),
    "crm/access_requests/item_requested": _op(
        "GET",
        f"{_API}/access-requests/{{access_request_id}}",
        "none",
        _setup_access_item,
        same=True,
    ),
    "crm/access_requests/update_requested": _op(
        "PUT",
        f"{_API}/access-requests/{{access_request_id}}",
        "body_minus_path",
        _setup_access_update,
        same=False,
    ),
    "crm/entities/daily_summary_requested": _op(
        "POST",
        f"{_API}/entities/daily-summary",
        "body_minus_path",
        _setup_daily_summary,
        same=True,
    ),
    "crm/entities/period_summary_requested": _op(
        "POST",
        f"{_API}/entities/period-summary",
        "body_minus_path",
        _setup_period_summary,
        same=True,
    ),
    "crm/tasks/daily_summary_start_requested": _op(
        "POST",
        f"{_API}/tasks/daily-summary",
        "body_minus_path",
        _setup_daily_summary_start,
        same=False,
    ),
    "crm/tasks/period_summary_start_requested": _op(
        "POST",
        f"{_API}/tasks/period-summary",
        "body_minus_path",
        _setup_period_summary_start,
        same=False,
    ),
    "crm/tasks/list_requested": _op(
        "GET", f"{_API}/tasks", "query", _setup_tasks_list,
        same=True, compare="marker_row", marker_field="task_id",
    ),
    "crm/tasks/item_requested": _op(
        "GET", f"{_API}/tasks/{{task_id}}", "none", _setup_task_item, same=True,
    ),
    "crm/tasks/created_entities_requested": _op(
        "GET",
        f"{_API}/tasks/{{task_id}}/created-entities",
        "none",
        _setup_task_item,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/tasks/knowledge_import_start_requested": _op(
        "POST",
        f"{_API}/tasks/knowledge-import",
        "body_minus_path",
        _setup_knowledge_import,
        same=False,
    ),
    "crm/tasks/review_complete_requested": _op(
        "POST",
        f"{_API}/tasks/{{task_id}}/review-complete",
        "none",
        _setup_task_item,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/tasks/cancel_requested": _op(
        "POST", f"{_API}/tasks/{{task_id}}/cancel", "none", _setup_task_item, same=False,
    ),
    "crm/tasks/rollback_requested": _op(
        "POST",
        f"{_API}/tasks/{{task_id}}/rollback",
        "none",
        _setup_task_missing,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/tasks/retry_requested": _op(
        "POST",
        f"{_API}/tasks/{{task_id}}/retry",
        "none",
        _setup_task_item,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/activity_tasks/create_requested": _op(
        "POST",
        f"{_API}/activity-tasks",
        "body_minus_path",
        _setup_activity_create,
        same=False,
    ),
    "crm/activity_tasks/list_requested": _op(
        "GET", f"{_API}/activity-tasks", "query", _setup_activity_list, same=True,
    ),
    "crm/attachments/list_requested": _op(
        "GET",
        f"{_API}/entities/{{entity_id}}/attachments",
        "none",
        _setup_attachments_list,
        same=True,
    ),
    "crm/attachments/attach_requested": _op(
        "POST",
        f"{_API}/entities/{{entity_id}}/attachments",
        "body_minus_path",
        _setup_attachments_attach,
        same=False,
    ),
    "crm/attachments/remove_requested": _op(
        "DELETE",
        f"{_API}/entities/{{entity_id}}/attachments/{{attachment_id}}",
        "none",
        _setup_attachments_remove,
        same=False,
    ),
    "crm/namespace_integrations/list_requested": _op(
        "GET",
        f"{_API}/namespaces/{{namespace_name}}/integrations",
        "none",
        _setup_integrations_list,
        same=True,
    ),
    "crm/namespace_integrations/authorize_requested": _op(
        "GET",
        f"{_API}/namespaces/{{namespace_name}}/integrations/{{provider_id}}/authorize",
        "query",
        _setup_integration_authorize,
        same=True,
        compare="error_code",
        expect="failed",
    ),
    "crm/namespace_integrations/auto_sync_requested": _op(
        "PATCH",
        f"{_API}/namespaces/{{namespace_name}}/integrations/{{provider_id}}/auto-sync",
        "body_minus_path",
        _setup_integration_auto_sync,
        same=True,
    ),
    "crm/namespace_integrations/auto_note_ai_requested": _op(
        "PATCH",
        f"{_API}/namespaces/{{namespace_name}}/integrations/{{provider_id}}/auto-note-ai-analyze",
        "body_minus_path",
        _setup_integration_auto_note,
        same=True,
    ),
    "crm/namespace_integrations/sync_requested": _op(
        "POST",
        f"{_API}/namespaces/{{namespace_name}}/integrations/{{provider_id}}/sync",
        "none",
        _setup_integration_sync,
        same=False,
    ),
    "crm/namespace_integrations/custom_fields_sync_requested": _op(
        "POST",
        f"{_API}/namespaces/{{namespace_name}}/integrations/{{provider_id}}/custom_fields/sync",
        "none",
        _setup_integration_sync,
        same=False,
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
        path_params[key] = _str_field(payload, key)
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    query_keys = set(rest.query_keys)
    if rest.strategy == "body":
        json_body = payload
        if query_keys:
            query = {
                k: v
                for k, v in payload.items()
                if k in query_keys and k not in path_params and v is not None
            }
    elif rest.strategy == "body_minus_path":
        body = {
            k: v
            for k, v in payload.items()
            if k not in path_params and k not in query_keys and v is not None
        }
        json_body = body if body else None
        if query_keys:
            query = {
                k: v
                for k, v in payload.items()
                if k in query_keys and k not in path_params and v is not None
            }
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


def _error_code(payload: JsonObject) -> str:
    code = payload.get("error_code")
    if isinstance(code, str) and code:
        return code
    raise AssertionError(f"error_code required, got {payload!r}")


def test_every_crm_operation_has_live_case() -> None:
    missing = sorted(set(CRM_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(CRM_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_crm_op_ws_rest_identical(
    canonical_type: str,
    crm_service: None,
    realtime_service: None,
    frontend_service: None,
    crm_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_system_user2: dict[str, str],
    auth_token_system: str,
    system_user2_id: str,
    unique_id: str,
) -> None:
    _ = crm_service, realtime_service, frontend_service
    headers = {
        **auth_headers_system,
        "X-Platform-Namespace": _NAMESPACE,
        "Accept-Language": "ru",
    }
    user2_headers = {
        **auth_headers_system_user2,
        "X-Platform-Namespace": _NAMESPACE,
    }
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=crm_client_http,
        headers=headers,
        user2_headers=user2_headers,
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
            client=crm_client_http,
            headers=headers,
            user2_headers=user2_headers,
            unique_id=unique_id,
            suffix="rest",
            system_user2_id=system_user2_id,
        )
        rest_payload = await case.setup(rest_ctx)
        rest_marker = rest_ctx.marker
    rest_result = await _rest_command(
        client=crm_client_http,
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
    if case.compare == "error_code":
        assert _error_code(ws_result) == _error_code(rest_result), (
            f"WS != REST error_code для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )
        return
    assert _normalize(ws_result) == _normalize(rest_result), (
        f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    )
