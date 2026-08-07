"""E2E platform_event filters: catalog → API validate → Redis index → dispatch.

Без monkeypatch / unittest.mock. Единственный допустимый мок платформы — MockLLM
(для TriggerExecutor → process_flow). Redis/Postgres/ASGI — реальные.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from enum import StrEnum

import pytest
from pydantic import BaseModel, Field

from apps.crm.services import crm_entity_events as _crm_entity_events
from apps.flows.src.models import FlowConfig, TriggerType
from apps.flows.src.services.platform_event_consumer import PlatformEventConsumerService
from apps.flows.src.triggers.handlers.platform_event import (
    dispatch_platform_event_triggers,
    platform_event_trigger_index_key,
    platform_event_trigger_index_member,
    platform_event_trigger_run_id,
)
from core.events import (
    PLATFORM_EVENT_CATALOG_KEY,
    PlatformEvent,
    PlatformEventCatalogEntry,
    publish_domain_event,
    register_platform_event,
    store_registered_platform_events,
)
from core.events.redis_client import events_redis_client
from core.types import require_json_object
from core.worktracker import events as _worktracker_events
from core.worktracker.events import WORK_ITEM_COMMENT_CREATED

_ = (_crm_entity_events, _worktracker_events)


async def _await_completed_state(container, session_id: str, *, timeout_sec: float = 20.0):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await container.workflow_runtime.get_state(session_id)
        if last_state is not None and last_state.terminal_task_state == "completed":
            return last_state
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"session {session_id!r} not completed in {timeout_sec}s; "
        f"terminal={getattr(last_state, 'terminal_task_state', None)!r}"
    )


async def _reset_platform_event_index(container, event_type: str) -> None:
    """Drop shared Redis index so leftover flows from prior runs cannot fire."""
    _ = await container.redis_client.delete(platform_event_trigger_index_key(event_type))


@pytest.fixture(autouse=True)
async def _isolate_platform_event_indexes(container) -> AsyncIterator[None]:
    """
    Index is global per event_type. Prior failed runs leave members for deleted-or-orphaned
    flows that still exist in DB; absolute fired-count asserts then flake.
    """
    for event_type in ("crm/entity/created", WORK_ITEM_COMMENT_CREATED):
        await _reset_platform_event_index(container, event_type)
    yield
    for event_type in ("crm/entity/created", WORK_ITEM_COMMENT_CREATED):
        await _reset_platform_event_index(container, event_type)


async def _ensure_catalog_in_redis() -> None:
    await store_registered_platform_events()


@pytest.mark.asyncio
async def test_catalog_api_returns_filter_fields_for_real_events(
    app, client, unique_id: str
) -> None:
    """GET catalog: crm + comment_created отдают leaf paths / enum для UI."""
    _ = app
    _ = unique_id
    await _ensure_catalog_in_redis()

    response = await client.get("/flows/api/v1/platform-events/catalog")
    assert response.status_code == 200
    body = require_json_object(response.json(), "catalog response")
    items = body["items"]
    assert isinstance(items, list)
    by_type = {
        require_json_object(item, "catalog item")["event_type"]: require_json_object(
            item, "catalog item"
        )
        for item in items
        if isinstance(item, dict)
    }

    crm = by_type["crm/entity/created"]
    crm_fields = {
        require_json_object(field, "filter field")["path"]: require_json_object(
            field, "filter field"
        )
        for field in crm["filter_fields"]
        if isinstance(field, dict)
    }
    assert "entity_type" in crm_fields
    assert crm_fields["entity_type"]["value_kind"] == "string"
    assert "contains" in crm_fields["entity_type"]["ops"]
    assert "tags" in crm_fields

    comment = by_type[WORK_ITEM_COMMENT_CREATED]
    comment_fields = {
        require_json_object(field, "filter field")["path"]: require_json_object(
            field, "filter field"
        )
        for field in comment["filter_fields"]
        if isinstance(field, dict)
    }
    role = comment_fields["comment.role"]
    assert role["value_kind"] == "enum"
    assert role["enum_values"] == ["operator", "user", "system", "agent"]
    assert role["ops"] == ["eq", "ne"]

    created = by_type["worktracker/work_item/created"]
    created_paths = {
        require_json_object(field, "filter field")["path"]
        for field in created["filter_fields"]
        if isinstance(field, dict)
    }
    assert "work_item.kind" in created_paths
    assert "work_item.assignment.assignee_kind" in created_paths
    assert "work_item.created_by.actor_kind" in created_paths


@pytest.mark.asyncio
async def test_catalog_redis_auto_heal_missing_filter_fields(
    app, client, unique_id: str
) -> None:
    """Старый dump без filter_fields → load/API пересчитывает из payload_schema."""
    _ = app
    event_type = f"test/heal_{unique_id.replace('-', '_')}/created"

    class HealPayload(BaseModel):
        heal_id: str
        active: bool = True

    register_platform_event(event_type, HealPayload, description="heal probe")
    schema = HealPayload.model_json_schema()
    stale = PlatformEventCatalogEntry(
        event_type=event_type,
        description="stale dump",
        payload_schema=schema,
        filter_fields=[],
    )
    redis = events_redis_client()
    _ = await redis.hset(PLATFORM_EVENT_CATALOG_KEY, mapping={event_type: stale.model_dump_json()})

    response = await client.get("/flows/api/v1/platform-events/catalog")
    assert response.status_code == 200
    body = require_json_object(response.json(), "catalog response")
    entry = next(
        require_json_object(item, "catalog item")
        for item in body["items"]
        if isinstance(item, dict)
        and require_json_object(item, "catalog item")["event_type"] == event_type
    )
    paths = {
        require_json_object(field, "filter field")["path"]
        for field in entry["filter_fields"]
        if isinstance(field, dict)
    }
    assert "heal_id" in paths
    assert "active" in paths


@pytest.mark.asyncio
async def test_new_registered_event_appears_in_catalog_api_with_filter_fields(
    app, client, unique_id: str
) -> None:
    """register_platform_event + store → catalog API без правок UI."""
    _ = app
    event_type = f"test/auto_{unique_id.replace('-', '_')}/happened"

    class Kind(StrEnum):
        ALPHA = "alpha"
        BETA = "beta"

    class Nested(BaseModel):
        role: Kind
        score: int = 0

    class AutoPayload(BaseModel):
        title: str
        nested: Nested
        tags: list[str] = Field(default_factory=list)
        files: list[Nested] = Field(default_factory=list)

    register_platform_event(event_type, AutoPayload, description="auto probe")
    await store_registered_platform_events()

    response = await client.get("/flows/api/v1/platform-events/catalog")
    assert response.status_code == 200
    body = require_json_object(response.json(), "catalog response")
    entry = next(
        require_json_object(item, "catalog item")
        for item in body["items"]
        if isinstance(item, dict)
        and require_json_object(item, "catalog item")["event_type"] == event_type
    )
    by_path = {
        require_json_object(field, "filter field")["path"]: require_json_object(
            field, "filter field"
        )
        for field in entry["filter_fields"]
        if isinstance(field, dict)
    }
    assert by_path["title"]["value_kind"] == "string"
    assert by_path["nested.role"]["value_kind"] == "enum"
    assert by_path["nested.role"]["enum_values"] == ["alpha", "beta"]
    assert by_path["nested.score"]["value_kind"] == "integer"
    assert by_path["tags"]["ops"] == ["eq", "ne", "contains"]
    assert "files" not in by_path
    assert "files.role" not in by_path


@pytest.mark.asyncio
async def test_create_platform_event_trigger_rejects_bad_filters_with_400(
    app, client, container, unique_id: str
) -> None:
    """Неизвестный path / bad op / bad enum / wrong type → HTTP 400, триггер не создан."""
    await _ensure_catalog_in_redis()
    flow_id = f"pe_bad_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Bad Filters",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    cases: list[tuple[str, dict[str, object]]] = [
        (
            "unknown path",
            {
                "event_type": "crm/entity/created",
                "filters": [{"path": "not_a_field", "op": "eq", "value": "x"}],
            },
        ),
        (
            "bad op for enum",
            {
                "event_type": WORK_ITEM_COMMENT_CREATED,
                "filters": [
                    {"path": "comment.role", "op": "contains", "value": "operator"}
                ],
            },
        ),
        (
            "bad enum value",
            {
                "event_type": WORK_ITEM_COMMENT_CREATED,
                "filters": [
                    {"path": "comment.role", "op": "eq", "value": "not_a_role"}
                ],
            },
        ),
        (
            "wrong value type",
            {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": 123}],
            },
        ),
    ]

    for label, config in cases:
        response = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": f"bad_{label.replace(' ', '_')}",
                "name": label,
                "type": "platform_event",
                "enabled": True,
                "config": config,
                "output_mapping": {"content": "@const:ok"},
            },
        )
        assert response.status_code == 400, f"{label}: {response.text}"
        saved = await container.flow_repository.get(flow_id)
        assert saved is not None
        assert f"bad_{label.replace(' ', '_')}" not in saved.triggers

    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_create_platform_event_trigger_accepts_catalog_filters(
    app, client, container, unique_id: str
) -> None:
    """Валидные filters → 200, ACTIVE, член Redis SET индекса."""
    await _ensure_catalog_in_redis()
    flow_id = f"pe_ok_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE OK Filters",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM task created",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [
                    {"path": "entity_type", "op": "eq", "value": "task"},
                    {"path": "tags", "op": "contains", "value": "vip"},
                    {"path": "status", "op": "ne", "value": "archived"},
                ],
            },
            "output_mapping": {"content": "@const:matched"},
        },
    )
    assert response.status_code == 200, response.text
    body = require_json_object(response.json(), "create trigger")
    assert body["status"] == "active"
    assert body["type"] == TriggerType.PLATFORM_EVENT.value

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    indexed = await container.redis_client.smembers(
        platform_event_trigger_index_key("crm/entity/created")
    )
    assert member in indexed

    await container.flow_repository.delete(flow_id)
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )


@pytest.mark.asyncio
async def test_dispatch_eq_ne_contains_and_and_filters(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """dispatch: match → fired; mismatch → 0; eq/ne/contains AND; empty filters → fire."""
    _ = app
    mock_llm_with_queue(["ok"] * 10)
    await _ensure_catalog_in_redis()

    flow_id = f"pe_dispatch_{unique_id}"
    trigger_match = "match_filters"
    trigger_empty = "always"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Dispatch",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    create_match = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_match,
            "name": "Filtered",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [
                    {"path": "entity_type", "op": "eq", "value": "task"},
                    {"path": "status", "op": "ne", "value": "archived"},
                    {"path": "tags", "op": "contains", "value": "vip"},
                    {"path": "name", "op": "contains", "value": "lead"},
                ],
            },
            "output_mapping": {"content": "@const:filtered"},
        },
    )
    assert create_match.status_code == 200, create_match.text

    create_empty = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_empty,
            "name": "Always",
            "type": "platform_event",
            "enabled": True,
            "config": {"event_type": "crm/entity/created", "filters": []},
            "output_mapping": {"content": "@const:always"},
        },
    )
    assert create_empty.status_code == 200, create_empty.text

    matching = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"e_{unique_id}",
            "entity_type": "task",
            "entity_subtype": None,
            "namespace": "default",
            "name": "hot lead",
            "status": "open",
            "tags": ["vip", "b2b"],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    fired_match = await dispatch_platform_event_triggers(
        container=container, event=matching
    )
    assert fired_match == 2

    mismatch = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"e2_{unique_id}",
            "entity_type": "note",
            "entity_subtype": None,
            "namespace": "default",
            "name": "hot lead",
            "status": "open",
            "tags": ["vip"],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    fired_mismatch = await dispatch_platform_event_triggers(
        container=container, event=mismatch
    )
    assert fired_mismatch == 1

    for trigger_id in (trigger_match, trigger_empty):
        member = platform_event_trigger_index_member(
            company_id="system", flow_id=flow_id, trigger_id=trigger_id
        )
        _ = await container.redis_client.srem(
            platform_event_trigger_index_key("crm/entity/created"), member
        )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_dispatch_enum_filter_on_comment_role(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """comment.role enum: operator матчит, user — нет."""
    _ = app
    mock_llm_with_queue(["ok", "ok"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_role_{unique_id}"
    trigger_id = "on_operator_comment"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Role",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "Operator comments",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": WORK_ITEM_COMMENT_CREATED,
                "filters": [
                    {"path": "comment.role", "op": "eq", "value": "operator"}
                ],
            },
            "output_mapping": {"content": "@const:operator"},
        },
    )
    assert created.status_code == 200, created.text

    hit = PlatformEvent(
        type=WORK_ITEM_COMMENT_CREATED,
        company_id="system",
        payload={
            "work_item_id": f"wi_{unique_id}",
            "comment": {
                "comment_id": f"c_{unique_id}",
                "work_item_id": f"wi_{unique_id}",
                "company_id": "system",
                "author": {"actor_kind": "user", "user_id": f"u_{unique_id}"},
                "role": "operator",
                "text": "hello",
                "files": [],
                "created_at": "2026-01-01T00:00:00Z",
            },
        },
    )
    assert (
        await dispatch_platform_event_triggers(container=container, event=hit)
    ) == 1

    miss_comment = require_json_object(hit.payload, "hit payload")
    comment = require_json_object(miss_comment["comment"], "comment")
    miss = PlatformEvent(
        type=WORK_ITEM_COMMENT_CREATED,
        company_id="system",
        payload={
            **miss_comment,
            "comment": {**comment, "role": "user"},
        },
    )
    assert (
        await dispatch_platform_event_triggers(container=container, event=miss)
    ) == 0

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key(WORK_ITEM_COMMENT_CREATED), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_publish_domain_event_then_dispatch_uses_same_payload_contract(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """Реальный publish_domain_event + тот же payload в dispatch с catalog filter."""
    _ = app
    mock_llm_with_queue(["ok"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_pub_{unique_id}"
    trigger_id = "on_person"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Publish",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "Person created",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [
                    {"path": "entity_type", "op": "eq", "value": "person"}
                ],
            },
            "output_mapping": {"content": "@const:person"},
        },
    )
    assert created.status_code == 200, created.text

    payload = {
        "entity_id": f"person_{unique_id}",
        "entity_type": "person",
        "entity_subtype": None,
        "namespace": "default",
        "name": f"Person {unique_id}",
        "status": "active",
        "tags": [],
        "actor_user_id": f"user_{unique_id}",
    }
    await publish_domain_event(
        "crm/entity/created",
        payload,
        company_id="system",
        actor_user_id=f"user_{unique_id}",
    )
    event = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload=payload,
    )
    fired = await dispatch_platform_event_triggers(container=container, event=event)
    assert fired == 1

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_update_platform_event_trigger_rejects_bad_filters_with_400(
    app, client, container, unique_id: str
) -> None:
    await _ensure_catalog_in_redis()
    flow_id = f"pe_put_bad_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE PUT Bad",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "task"}],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert created.status_code == 200, created.text

    updated = await client.put(
        f"/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}",
        json={
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "not_a_field", "op": "eq", "value": "x"}],
            }
        },
    )
    assert updated.status_code == 400, updated.text

    get_resp = await client.get(f"/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}")
    assert get_resp.status_code == 200
    body = require_json_object(get_resp.json(), "get trigger")
    config = require_json_object(body["config"], "trigger config")
    filters = config["filters"]
    assert isinstance(filters, list) and len(filters) == 1
    first = require_json_object(filters[0], "filter")
    assert first["path"] == "entity_type"

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_update_platform_event_trigger_accepts_valid_filter_change(
    app, client, container, unique_id: str
) -> None:
    await _ensure_catalog_in_redis()
    flow_id = f"pe_put_ok_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE PUT OK",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "task"}],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert created.status_code == 200, created.text

    updated = await client.put(
        f"/flows/api/v1/flows/{flow_id}/triggers/{trigger_id}",
        json={
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "person"}],
            }
        },
    )
    assert updated.status_code == 200, updated.text
    body = require_json_object(updated.json(), "update trigger")
    assert body["status"] == "active"
    config = require_json_object(body["config"], "trigger config")
    filters = config["filters"]
    assert isinstance(filters, list)
    first = require_json_object(filters[0], "filter")
    assert first["value"] == "person"

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    indexed = await container.redis_client.smembers(
        platform_event_trigger_index_key("crm/entity/created")
    )
    assert member in indexed

    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_create_rejects_filters_when_catalog_has_empty_filter_fields(
    app, client, container, unique_id: str
) -> None:
    event_type = f"test/noleaf_{unique_id.replace('-', '_').lower()}/created"

    class NestedOnly(BaseModel):
        role: str

    class NoLeafPayload(BaseModel):
        files: list[NestedOnly] = Field(default_factory=list)

    register_platform_event(event_type, NoLeafPayload, description="No leaves.")
    await store_registered_platform_events()

    flow_id = f"pe_noleaf_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE No Leaf",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": "bad",
            "name": "Bad",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": event_type,
                "filters": [{"path": "files", "op": "eq", "value": "x"}],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert response.status_code == 400, response.text
    assert "no filterable fields" in response.text
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_create_accepts_boolean_integer_number_filters_and_dispatch(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    mock_llm_with_queue(["ok", "ok"])
    event_type = f"test/nums_{unique_id.replace('-', '_').lower()}/changed"

    class NumPayload(BaseModel):
        flag: bool = False
        score: int = 0
        ratio: float = 0.0

    register_platform_event(event_type, NumPayload, description="Numeric probe.")
    await store_registered_platform_events()

    flow_id = f"pe_nums_{unique_id}"
    trigger_id = "on_nums"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Nums",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "Nums",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": event_type,
                "filters": [
                    {"path": "flag", "op": "eq", "value": True},
                    {"path": "score", "op": "eq", "value": 7},
                    {"path": "ratio", "op": "eq", "value": 1.25},
                ],
            },
            "output_mapping": {"content": "@const:nums"},
        },
    )
    assert created.status_code == 200, created.text

    hit = PlatformEvent(
        type=event_type,
        company_id="system",
        payload={"flag": True, "score": 7, "ratio": 1.25},
    )
    assert (
        await dispatch_platform_event_triggers(container=container, event=hit)
    ) == 1

    miss = PlatformEvent(
        type=event_type,
        company_id="system",
        payload={"flag": True, "score": 7, "ratio": 0.5},
    )
    assert (
        await dispatch_platform_event_triggers(container=container, event=miss)
    ) == 0

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key(event_type), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_create_uses_in_process_catalog_when_redis_entry_missing(
    app, client, container, unique_id: str
) -> None:
    event_type = f"test/fallback_{unique_id.replace('-', '_').lower()}/happened"

    class FallbackPayload(BaseModel):
        title: str

    register_platform_event(event_type, FallbackPayload, description="Fallback.")
    redis = events_redis_client()
    _ = await redis.hdel(PLATFORM_EVENT_CATALOG_KEY, event_type)

    flow_id = f"pe_fb_{unique_id}"
    trigger_id = "on_fallback"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Fallback",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "Fallback",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": event_type,
                "filters": [{"path": "title", "op": "eq", "value": "ok"}],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert created.status_code == 200, created.text

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key(event_type), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_create_rejects_unknown_event_type_not_in_catalog(
    app, client, container, unique_id: str
) -> None:
    await _ensure_catalog_in_redis()
    flow_id = f"pe_unknown_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Unknown",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": "unknown",
            "name": "Unknown",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": f"test/unknown_{unique_id.replace('-', '_').lower()}/gone",
                "filters": [],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert response.status_code == 400, response.text
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_dispatch_persists_completed_state(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """platform_event_trigger_run_id → session_id → completed + mapping."""
    _ = app
    mock_llm_with_queue(["PE completed"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_done_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Completed",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "person"}],
            },
            "output_mapping": {
                "content": "payload.name",
                "context.entity_id": "payload.entity_id",
            },
        },
    )
    assert created.status_code == 200, created.text

    event = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"person_{unique_id}",
            "entity_type": "person",
            "entity_subtype": None,
            "namespace": "default",
            "name": f"Person {unique_id}",
            "status": "active",
            "tags": [],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    fired = await dispatch_platform_event_triggers(container=container, event=event)
    assert fired == 1

    run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
    session_id = f"{flow_id}:{run_id}"
    state = await _await_completed_state(container, session_id)
    assert state.content == f"Person {unique_id}"
    assert state.triggers[trigger_id].context["entity_id"] == f"person_{unique_id}"
    assert state.response == "PE completed"

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_dispatch_idempotent_same_run_id(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """Два dispatch одного event → один session_id (deterministic run_id)."""
    _ = app
    mock_llm_with_queue(["PE once", "PE twice should not matter"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_idem_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Idem",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert created.status_code == 200, created.text

    event = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"e_{unique_id}",
            "entity_type": "task",
            "entity_subtype": None,
            "namespace": "default",
            "name": "Task",
            "status": "active",
            "tags": [],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    assert await dispatch_platform_event_triggers(container=container, event=event) == 1
    run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
    session_id = f"{flow_id}:{run_id}"
    state1 = await _await_completed_state(container, session_id)

    assert await dispatch_platform_event_triggers(container=container, event=event) == 1
    state2 = await container.workflow_runtime.get_state(session_id)
    assert state2 is not None
    assert state2.session_id == state1.session_id
    assert state2.terminal_task_state == "completed"

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_handle_event_fires_triggers(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """PlatformEventConsumerService.handle_event → completed (без XREADGROUP)."""
    _ = app
    mock_llm_with_queue(["From handle_event"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_handle_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Handle",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "organization"}],
            },
            "output_mapping": {"content": "payload.name"},
        },
    )
    assert created.status_code == 200, created.text

    event = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"org_{unique_id}",
            "entity_type": "organization",
            "entity_subtype": None,
            "namespace": "default",
            "name": f"Org {unique_id}",
            "status": "active",
            "tags": [],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    consumer = PlatformEventConsumerService(
        container=container,
        employee_inbox_service=container.employee_inbox_service,
    )
    await consumer.handle_event(event)

    run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
    state = await _await_completed_state(container, f"{flow_id}:{run_id}")
    assert state.content == f"Org {unique_id}"
    assert state.response == "From handle_event"

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_filter_mismatch_no_state(
    app, client, container, unique_id: str, mock_llm_with_queue
) -> None:
    """Filter miss → fired==0, state отсутствует."""
    _ = app
    mock_llm_with_queue(["should not run"])
    await _ensure_catalog_in_redis()

    flow_id = f"pe_miss_{unique_id}"
    trigger_id = "on_entity"
    agent = FlowConfig(
        flow_id=flow_id,
        name="PE Miss",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await container.flow_repository.set(agent)

    created = await client.post(
        f"/flows/api/v1/flows/{flow_id}/triggers",
        json={
            "trigger_id": trigger_id,
            "name": "CRM",
            "type": "platform_event",
            "enabled": True,
            "config": {
                "event_type": "crm/entity/created",
                "filters": [{"path": "entity_type", "op": "eq", "value": "person"}],
            },
            "output_mapping": {"content": "@const:ok"},
        },
    )
    assert created.status_code == 200, created.text

    event = PlatformEvent(
        type="crm/entity/created",
        company_id="system",
        payload={
            "entity_id": f"task_{unique_id}",
            "entity_type": "task",
            "entity_subtype": None,
            "namespace": "default",
            "name": "Task",
            "status": "active",
            "tags": [],
            "actor_user_id": f"user_{unique_id}",
        },
    )
    assert await dispatch_platform_event_triggers(container=container, event=event) == 0
    run_id = platform_event_trigger_run_id(event.event_id, trigger_id)
    state = await container.workflow_runtime.get_state(f"{flow_id}:{run_id}")
    assert state is None

    member = platform_event_trigger_index_member(
        company_id="system", flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        platform_event_trigger_index_key("crm/entity/created"), member
    )
    await container.flow_repository.delete(flow_id)
