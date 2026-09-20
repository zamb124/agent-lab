"""
Networkle Tasks: строгие интеграционные сценарии новой архитектуры.

Source of truth work-полей — WorkItem(kind=crm_activity).
CRM-узел entity_type=task — граф/AI. Создание пары — POST /crm/api/v1/activity-tasks.
Мутации work — /worktracker/api/v1/work-items (как worktracker/work_item_* в UI).

Без моков и monkeypatch: реальный Postgres (CRM + worktracker), Redis, ASGI crm_client
и worktracker_client, реальный DI-контейнер.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import pytest
from httpx import AsyncClient, Response

from core.worktracker.models import (
    CrmEntityLink,
    UsersAssignment,
    WorkItemKind,
    WorkItemPriority,
    WorkItemState,
)
from tests.fixtures.crm_test_setup import (
    ensure_crm_namespace,
    ensure_entity_type_in_namespace,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKTRACKER_WORK_ITEMS = "/worktracker/api/v1/work-items"
ACTIVITY_TASKS = "/crm/api/v1/activity-tasks"


def _ns(unique_id: str) -> str:
    return f"g_{unique_id}"


def _json_object(response: Response) -> dict[str, object]:
    body = cast(object, response.json())
    if not isinstance(body, dict):
        raise AssertionError(f"ожидался JSON-объект, получено {type(body)}")
    return cast(dict[str, object], body)


def _require_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"поле {key!r} должно быть непустой строкой, получено {value!r}")
    return value


def _require_object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise AssertionError(f"поле {key!r} должно быть объектом, получено {type(value)}")
    return cast(dict[str, object], value)


def _require_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise AssertionError(f"поле {key!r} должно быть списком, получено {type(value)}")
    return cast(list[object], value)


async def _create_activity_task(
    crm_client: AsyncClient,
    headers: dict[str, str],
    *,
    title: str,
    namespace: str,
    **extra: object,
) -> dict[str, object]:
    body: dict[str, object] = {"title": title, "namespace": namespace}
    body.update(extra)
    response = await crm_client.post(ACTIVITY_TASKS, json=body, headers=headers)
    assert response.status_code == 200, response.text
    return _json_object(response)


# ---------------------------------------------------------------------------
# Primary create path: POST /activity-tasks
# ---------------------------------------------------------------------------


async def test_activity_task_create_returns_entity_and_work_item_pair(
    crm_client: AsyncClient,
    crm_container,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    namespace = _ns(unique_id)
    due = (date.today() + timedelta(days=5)).isoformat()
    payload = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Native task {unique_id}",
        namespace=namespace,
        description="facade create",
        priority="urgent",
        due_date=due,
        assignees=["assignee_a", "assignee_b"],
        tags=["native", unique_id],
    )

    entity = _require_object(payload, "entity")
    work_item = _require_object(payload, "work_item")

    assert entity.get("entity_type") == "task"
    assert entity.get("name") == f"Native task {unique_id}"
    assert entity.get("description") == "facade create"
    assert entity.get("namespace") == namespace
    assert "priority" not in entity
    assert "due_date" not in entity
    assert "assignees" not in entity
    assert _require_str(entity, "work_item_id") == _require_str(work_item, "work_item_id")

    assert work_item.get("kind") == "crm_activity"
    assert work_item.get("title") == f"Native task {unique_id}"
    assert work_item.get("description") == "facade create"
    assert work_item.get("priority") == "urgent"
    assert work_item.get("state") == "open"
    assert work_item.get("namespace") == namespace

    assignment = _require_object(work_item, "assignment")
    assert assignment.get("assignee_kind") == "users"
    assert assignment.get("user_ids") == ["assignee_a", "assignee_b"]

    entity_id = _require_str(entity, "entity_id")
    persisted = await crm_container.crm_work_item_service.get_for_task(
        company_id="system",
        entity_id=entity_id,
    )
    assert persisted is not None
    assert persisted.work_item_id == work_item["work_item_id"]
    assert persisted.kind is WorkItemKind.CRM_ACTIVITY
    assert persisted.priority is WorkItemPriority.URGENT
    assert isinstance(persisted.assignment, UsersAssignment)
    assert persisted.assignment.user_ids == ["assignee_a", "assignee_b"]
    assert persisted.due_date is not None
    assert persisted.due_date.date() == date.fromisoformat(due)
    crm_links = [link for link in persisted.links if isinstance(link, CrmEntityLink)]
    assert len(crm_links) == 1
    assert crm_links[0].entity_id == entity_id


async def test_activity_task_create_rejects_empty_title(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    response = await crm_client.post(
        ACTIVITY_TASKS,
        json={"title": "", "namespace": _ns(unique_id)},
        headers=auth_headers_system,
    )
    assert response.status_code == 422


async def test_activity_task_create_places_on_task_board(
    crm_client: AsyncClient,
    crm_container,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    namespace = _ns(unique_id)
    payload = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Boarded {unique_id}",
        namespace=namespace,
    )
    work_item = _require_object(payload, "work_item")
    board_id = work_item.get("board_id")
    assert isinstance(board_id, str) and board_id

    board = await crm_container.work_item_service.get_board(
        company_id="system",
        board_id=board_id,
    )
    assert board.board_key == "task"
    assert board.namespace == namespace


async def test_activity_task_create_unknown_subtype_fails_closed(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    """Неизвестный entity_subtype — fail-closed, без угадывания доски."""
    response = await crm_client.post(
        ACTIVITY_TASKS,
        json={
            "title": f"Subtype task {unique_id}",
            "namespace": _ns(unique_id),
            "entity_subtype": f"missing_subtype_{unique_id}",
        },
        headers=auth_headers_system,
    )
    assert response.status_code >= 400


# ---------------------------------------------------------------------------
# List facade: GET /activity-tasks
# ---------------------------------------------------------------------------


async def test_activity_tasks_list_filters_by_namespace_and_state(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    ns_a = _ns(unique_id)
    ns_b = f"g_b_{unique_id}"
    await ensure_crm_namespace(crm_client, auth_headers_system, ns_b)
    await ensure_entity_type_in_namespace(
        crm_client,
        auth_headers_system,
        "task",
        "Задача",
        ns_b,
    )
    a = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"A {unique_id}",
        namespace=ns_a,
    )
    b = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"B {unique_id}",
        namespace=ns_b,
    )
    a_id = _require_str(_require_object(a, "work_item"), "work_item_id")
    b_id = _require_str(_require_object(b, "work_item"), "work_item_id")

    listed_a = await crm_client.get(
        ACTIVITY_TASKS,
        params={"namespace": ns_a, "limit": 50, "offset": 0},
        headers=auth_headers_system,
    )
    assert listed_a.status_code == 200
    page_a = _json_object(listed_a)
    items_a = _require_list(page_a, "items")
    ids_a = {
        row.get("work_item_id")
        for row in items_a
        if isinstance(row, dict)
    }
    assert a_id in ids_a
    assert b_id not in ids_a
    assert isinstance(page_a.get("total"), int)
    assert cast(int, page_a["total"]) >= 1

    entity_a_id = _require_str(_require_object(a, "entity"), "entity_id")
    move_via_entity = await crm_client.put(
        f"/crm/api/v1/entities/{entity_a_id}",
        json={"attributes": {"status": "done"}},
        headers=auth_headers_system,
    )
    assert move_via_entity.status_code == 200

    listed_done = await crm_client.get(
        ACTIVITY_TASKS,
        params={"namespace": ns_a, "state": "done", "limit": 50, "offset": 0},
        headers=auth_headers_system,
    )
    assert listed_done.status_code == 200
    done_ids = {
        row.get("work_item_id")
        for row in _require_list(_json_object(listed_done), "items")
        if isinstance(row, dict)
    }
    assert a_id in done_ids

    listed_open = await crm_client.get(
        ACTIVITY_TASKS,
        params={"namespace": ns_a, "state": "open", "limit": 50, "offset": 0},
        headers=auth_headers_system,
    )
    assert listed_open.status_code == 200
    open_ids = {
        row.get("work_item_id")
        for row in _require_list(_json_object(listed_open), "items")
        if isinstance(row, dict)
    }
    assert a_id not in open_ids


async def test_activity_task_list_empty_namespace_is_empty_page(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    empty_ns = f"g_empty_{unique_id}"
    await ensure_crm_namespace(crm_client, auth_headers_system, empty_ns)
    listed = await crm_client.get(
        ACTIVITY_TASKS,
        params={"namespace": empty_ns, "limit": 20, "offset": 0},
        headers=auth_headers_system,
    )
    assert listed.status_code == 200
    page = _json_object(listed)
    assert page.get("items") == []
    assert page.get("total") == 0
    assert page.get("limit") == 20
    assert page.get("offset") == 0


# ---------------------------------------------------------------------------
# Cross-service: CRM create → worktracker mutate (platform factories path)
# ---------------------------------------------------------------------------


async def test_worktracker_list_sees_crm_activity_from_activity_tasks(
    crm_client: AsyncClient,
    worktracker_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    namespace = _ns(unique_id)
    created = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Visible in WT {unique_id}",
        namespace=namespace,
    )
    work_item_id = _require_str(_require_object(created, "work_item"), "work_item_id")

    listed = await worktracker_client.get(
        WORKTRACKER_WORK_ITEMS,
        params={
            "kind": "crm_activity",
            "namespace": namespace,
            "limit": 50,
            "offset": 0,
        },
    )
    assert listed.status_code == 200
    ids = {
        row.get("work_item_id")
        for row in _require_list(_json_object(listed), "items")
        if isinstance(row, dict)
    }
    assert work_item_id in ids


async def test_worktracker_patch_move_assign_crm_activity(
    crm_client: AsyncClient,
    worktracker_client: AsyncClient,
    crm_container,
    unique_id: str,
    auth_headers_system: dict[str, str],
    system_user_id: str,
) -> None:
    namespace = _ns(unique_id)
    created = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Mutate me {unique_id}",
        namespace=namespace,
        priority="low",
    )
    work_item_id = _require_str(_require_object(created, "work_item"), "work_item_id")
    entity_id = _require_str(_require_object(created, "entity"), "entity_id")

    patched = await worktracker_client.patch(
        f"{WORKTRACKER_WORK_ITEMS}/{work_item_id}",
        json={
            "title": f"Patched {unique_id}",
            "description": "updated from worktracker",
            "priority": "high",
        },
    )
    assert patched.status_code == 200
    patched_body = _json_object(patched)
    assert patched_body.get("title") == f"Patched {unique_id}"
    assert patched_body.get("priority") == "high"
    assert patched_body.get("kind") == "crm_activity"

    moved = await worktracker_client.post(
        f"{WORKTRACKER_WORK_ITEMS}/{work_item_id}/move",
        json={"state": "in_progress"},
    )
    assert moved.status_code == 200
    assert _json_object(moved).get("state") == "in_progress"

    assigned = await worktracker_client.post(
        f"{WORKTRACKER_WORK_ITEMS}/{work_item_id}/assign",
        json={"assignment": {"assignee_kind": "users", "user_ids": [system_user_id]}},
    )
    assert assigned.status_code == 200
    assignment = _require_object(_json_object(assigned), "assignment")
    assert assignment.get("assignee_kind") == "users"
    assert assignment.get("user_ids") == [system_user_id]

    entity_get = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_system,
    )
    assert entity_get.status_code == 200
    entity_body = _json_object(entity_get)
    assert entity_body.get("entity_type") == "task"
    assert entity_body.get("work_item_id") == work_item_id
    assert "priority" not in entity_body

    persisted = await crm_container.work_item_service.get("system", work_item_id)
    assert persisted.title == f"Patched {unique_id}"
    assert persisted.priority is WorkItemPriority.HIGH
    assert persisted.state is WorkItemState.IN_PROGRESS
    assert isinstance(persisted.assignment, UsersAssignment)
    assert persisted.assignment.user_ids == [system_user_id]


async def test_entity_rename_does_not_reset_work_fields(
    crm_client: AsyncClient,
    worktracker_client: AsyncClient,
    crm_container,
    unique_id: str,
    auth_headers_system: dict[str, str],
    system_user_id: str,
) -> None:
    namespace = _ns(unique_id)
    created = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Before rename {unique_id}",
        namespace=namespace,
        priority="high",
        assignees=[system_user_id],
    )
    entity_id = _require_str(_require_object(created, "entity"), "entity_id")
    work_item_id = _require_str(_require_object(created, "work_item"), "work_item_id")

    moved = await worktracker_client.post(
        f"{WORKTRACKER_WORK_ITEMS}/{work_item_id}/move",
        json={"state": "blocked"},
    )
    assert moved.status_code == 200

    renamed = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}",
        json={"name": f"After rename {unique_id}"},
        headers=auth_headers_system,
    )
    assert renamed.status_code == 200
    assert _json_object(renamed).get("name") == f"After rename {unique_id}"

    item = await crm_container.work_item_service.get("system", work_item_id)
    assert item.title == f"After rename {unique_id}"
    assert item.priority is WorkItemPriority.HIGH
    assert item.state is WorkItemState.BLOCKED
    assert isinstance(item.assignment, UsersAssignment)
    assert item.assignment.user_ids == [system_user_id]


# ---------------------------------------------------------------------------
# Graph secondary path + delete cascade
# ---------------------------------------------------------------------------


async def test_entities_create_task_still_pairs_and_enriches_work_item_id(
    crm_client: AsyncClient,
    crm_container,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    namespace = _ns(unique_id)
    create = await crm_client.post(
        "/crm/api/v1/entities/",
        json={
            "entity_type": "task",
            "name": f"Graph path {unique_id}",
            "namespace": namespace,
        },
        headers=auth_headers_system,
    )
    assert create.status_code == 200
    body = _json_object(create)
    entity_id = _require_str(body, "entity_id")
    work_item_id = _require_str(body, "work_item_id")

    item = await crm_container.work_item_service.find_by_crm_entity("system", entity_id)
    assert item is not None
    assert item.work_item_id == work_item_id
    assert item.kind is WorkItemKind.CRM_ACTIVITY
    assert item.board_id is not None
    board = await crm_container.work_item_service.get_board(
        company_id="system",
        board_id=item.board_id,
    )
    assert board.board_key == "task"


async def test_delete_activity_task_entity_removes_work_item(
    crm_client: AsyncClient,
    worktracker_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    created = await _create_activity_task(
        crm_client,
        auth_headers_system,
        title=f"Delete me {unique_id}",
        namespace=_ns(unique_id),
    )
    entity_id = _require_str(_require_object(created, "entity"), "entity_id")
    work_item_id = _require_str(_require_object(created, "work_item"), "work_item_id")

    delete = await crm_client.delete(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_system,
    )
    assert delete.status_code in (200, 204)

    missing = await worktracker_client.get(f"{WORKTRACKER_WORK_ITEMS}/{work_item_id}")
    assert missing.status_code == 404
