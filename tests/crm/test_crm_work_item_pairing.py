"""
Строгие интеграционные тесты пары CRM-узел задачи ↔ WorkItem(crm_activity).

Без моков и monkeypatch: реальный Postgres (platform_crm + platform_worktracker),
реальный Redis (publish events / notify), реальный CRM-контейнер и ядро worktracker.

Инвариант cutover: CRM `entity_type=task` остаётся графовым узлом (имя/описание/
атрибуты/связи), а вся work-семантика (state/priority/assignee/срок/доска) живёт
в парном `WorkItem(kind=crm_activity)` со связью 1:1 через `CrmEntityLink`.

Покрываются happy- и unhappy-сценарии:
- маппинг `CrmWorkItemService` (priority/board_status/assignees/due) — все ветки;
- создание/обновление/удаление/слияние CRM-задачи синхронизирует WorkItem 1:1;
- CRM API задачи не содержит work-полей;
- не-task сущности не получают WorkItem;
- межсервисная гибкость: WorkItem CRM-задачи переназначается на агента/очередь.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.services.crm_work_item_service import CrmTaskWorkSeed
from core.worktracker.models import (
    AgentAssignment,
    CrmEntityLink,
    QueueAssignment,
    UnassignedAssignment,
    UsersAssignment,
    WorkItemKind,
    WorkItemPriority,
    WorkItemState,
)

pytestmark = pytest.mark.asyncio


def _http_json(response: Response) -> dict[str, object]:
    body = cast(object, response.json())
    if not isinstance(body, dict):
        raise AssertionError(f"ожидался JSON-объект, получено {type(body)}")
    return cast(dict[str, object], body)


def _entity_id(response: Response) -> str:
    value = _http_json(response).get("entity_id")
    if not isinstance(value, str) or not value:
        raise AssertionError("в ответе нет entity_id")
    return value


# ======================= Часть A: маппинг CrmWorkItemService =======================
# Не требует CRM-узла: сервис пишет только в platform_worktracker.


async def test_sync_creates_paired_work_item_with_link(app, crm_container, unique_id):
    svc = crm_container.crm_work_item_service
    entity_id = f"ent_{unique_id}"
    item = await svc.sync_for_task(
        company_id="system",
        entity_id=entity_id,
        namespace=f"ns-{unique_id}",
        title=f"CRM task {unique_id}",
        description="desc",
        seed=CrmTaskWorkSeed(),
    )
    assert item.kind is WorkItemKind.CRM_ACTIVITY
    assert item.state is WorkItemState.OPEN
    assert item.priority is WorkItemPriority.NORMAL
    assert isinstance(item.assignment, UnassignedAssignment)
    assert item.blocking is False
    crm_links = [link for link in item.links if isinstance(link, CrmEntityLink)]
    assert len(crm_links) == 1
    assert crm_links[0].entity_id == entity_id


@pytest.mark.parametrize(
    ("priority_in", "expected"),
    [
        ("low", WorkItemPriority.LOW),
        ("normal", WorkItemPriority.NORMAL),
        ("medium", WorkItemPriority.NORMAL),
        ("high", WorkItemPriority.HIGH),
        ("urgent", WorkItemPriority.URGENT),
        ("weird-value", WorkItemPriority.NORMAL),
        (None, WorkItemPriority.NORMAL),
    ],
)
async def test_sync_priority_mapping(app, crm_container, unique_id, priority_in, expected):
    svc = crm_container.crm_work_item_service
    item = await svc.sync_for_task(
        company_id="system",
        entity_id=f"ent_prio_{priority_in}_{unique_id}",
        namespace=f"ns-{unique_id}",
        title="t",
        seed=CrmTaskWorkSeed(priority=priority_in),
    )
    assert item.priority is expected


@pytest.mark.parametrize(
    ("status_in", "expected"),
    [
        ("todo", WorkItemState.OPEN),
        ("open", WorkItemState.OPEN),
        ("backlog", WorkItemState.OPEN),
        ("in_progress", WorkItemState.IN_PROGRESS),
        ("doing", WorkItemState.IN_PROGRESS),
        ("review", WorkItemState.IN_PROGRESS),
        ("blocked", WorkItemState.BLOCKED),
        ("done", WorkItemState.DONE),
        ("completed", WorkItemState.DONE),
        ("cancelled", WorkItemState.CANCELLED),
        ("custom-stage", WorkItemState.OPEN),
        (None, WorkItemState.OPEN),
    ],
)
async def test_sync_board_status_to_state_mapping(app, crm_container, unique_id, status_in, expected):
    svc = crm_container.crm_work_item_service
    item = await svc.sync_for_task(
        company_id="system",
        entity_id=f"ent_st_{status_in}_{unique_id}",
        namespace=f"ns-{unique_id}",
        title="t",
        seed=CrmTaskWorkSeed(board_status=status_in),
    )
    assert item.state is expected


async def test_sync_assignees_and_due(app, crm_container, unique_id):
    svc = crm_container.crm_work_item_service
    due = date.today() + timedelta(days=3)
    item = await svc.sync_for_task(
        company_id="system",
        entity_id=f"ent_assign_{unique_id}",
        namespace=f"ns-{unique_id}",
        title="t",
        seed=CrmTaskWorkSeed(assignees=["u1", "u2"], due_date=due),
    )
    assert isinstance(item.assignment, UsersAssignment)
    assert item.assignment.user_ids == ["u1", "u2"]
    assert item.due_date is not None
    assert item.due_date.date() == due


async def test_sync_is_idempotent_one_to_one(app, crm_container, unique_id):
    svc = crm_container.crm_work_item_service
    entity_id = f"ent_idem_{unique_id}"
    first = await svc.sync_for_task(
        company_id="system",
        entity_id=entity_id,
        namespace=f"ns-{unique_id}",
        title="t1",
        seed=CrmTaskWorkSeed(priority="low", board_status="todo"),
    )
    second = await svc.sync_for_task(
        company_id="system",
        entity_id=entity_id,
        namespace=f"ns-{unique_id}",
        title="t2",
        seed=CrmTaskWorkSeed(priority="urgent", assignees=["u9"], board_status="in_progress"),
    )
    assert first.work_item_id == second.work_item_id
    assert second.title == "t2"
    assert second.priority is WorkItemPriority.URGENT
    assert isinstance(second.assignment, UsersAssignment)
    assert second.state is WorkItemState.IN_PROGRESS
    fetched = await svc.get_for_task(company_id="system", entity_id=entity_id)
    assert fetched is not None
    assert fetched.work_item_id == first.work_item_id


async def test_delete_for_task_removes_work_item(app, crm_container, unique_id):
    svc = crm_container.crm_work_item_service
    entity_id = f"ent_del_{unique_id}"
    _ = await svc.sync_for_task(
        company_id="system",
        entity_id=entity_id,
        namespace=f"ns-{unique_id}",
        title="t",
        seed=CrmTaskWorkSeed(),
    )
    assert await svc.get_for_task(company_id="system", entity_id=entity_id) is not None
    await svc.delete_for_task(company_id="system", entity_id=entity_id)
    assert await svc.get_for_task(company_id="system", entity_id=entity_id) is None


async def test_delete_for_task_missing_is_noop(app, crm_container, unique_id):
    svc = crm_container.crm_work_item_service
    # Удаление несуществующей пары не падает.
    await svc.delete_for_task(company_id="system", entity_id=f"absent_{unique_id}")


async def test_reassign_crm_work_item_to_agent_and_queue(app, crm_container, unique_id):
    """CRM-задачу можно перевести на агента или очередь (межсервисная гибкость)."""
    crm_svc = crm_container.crm_work_item_service
    wi_svc = crm_container.work_item_service
    entity_id = f"ent_reassign_{unique_id}"
    item = await crm_svc.sync_for_task(
        company_id="system",
        entity_id=entity_id,
        namespace=f"ns-{unique_id}",
        title="t",
        seed=CrmTaskWorkSeed(assignees=["u1"]),
    )
    to_agent = await wi_svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=AgentAssignment(flow_id=f"flow_{unique_id}"),
    )
    assert isinstance(to_agent.assignment, AgentAssignment)
    assert to_agent.kind is WorkItemKind.CRM_ACTIVITY

    queue = await wi_svc.create_queue(company_id="system", name="Q", slug=f"crm-q-{unique_id}")
    to_queue = await wi_svc.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
    )
    assert isinstance(to_queue.assignment, QueueAssignment)


# ======================= Часть B: пара через CRM API (HTTP) =======================


async def test_create_task_via_api_pairs_work_item(crm_client: AsyncClient, unique_id, auth_headers_system):
    namespace = f"g_{unique_id}"
    resp = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"API task {unique_id}", "namespace": namespace},
        headers=auth_headers_system,
    )
    assert resp.status_code == 200
    entity_id = _entity_id(resp)

    item = await _get_crm_container().work_item_service.find_by_crm_entity("system", entity_id)
    assert item is not None
    assert item.kind is WorkItemKind.CRM_ACTIVITY
    assert item.namespace == namespace
    assert item.state is WorkItemState.OPEN
    crm_links = [link for link in item.links if isinstance(link, CrmEntityLink)]
    assert len(crm_links) == 1 and crm_links[0].entity_id == entity_id


async def test_task_api_response_has_no_work_fields(crm_client: AsyncClient, unique_id, auth_headers_system):
    resp = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"clean task {unique_id}", "namespace": f"g_{unique_id}"},
        headers=auth_headers_system,
    )
    assert resp.status_code == 200
    body = _http_json(resp)
    assert "priority" not in body
    assert "due_date" not in body
    assert "assignees" not in body


async def test_note_entity_has_no_paired_work_item(crm_client: AsyncClient, unique_id, auth_headers_system):
    resp = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "note", "name": f"note {unique_id}", "namespace": f"g_{unique_id}"},
        headers=auth_headers_system,
    )
    assert resp.status_code == 200
    entity_id = _entity_id(resp)
    item = await _get_crm_container().work_item_service.find_by_crm_entity("system", entity_id)
    assert item is None


async def test_update_task_name_syncs_work_item_title(crm_client: AsyncClient, unique_id, auth_headers_system):
    create = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"orig {unique_id}", "namespace": f"g_{unique_id}"},
        headers=auth_headers_system,
    )
    entity_id = _entity_id(create)
    upd = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}",
        json={"name": f"renamed {unique_id}"},
        headers=auth_headers_system,
    )
    assert upd.status_code == 200
    item = await _get_crm_container().work_item_service.find_by_crm_entity("system", entity_id)
    assert item is not None
    assert item.title == f"renamed {unique_id}"


async def test_update_task_board_status_moves_work_item(crm_client: AsyncClient, unique_id, auth_headers_system):
    create = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"st {unique_id}", "namespace": f"g_{unique_id}"},
        headers=auth_headers_system,
    )
    entity_id = _entity_id(create)
    upd = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}",
        json={"attributes": {"status": "done"}},
        headers=auth_headers_system,
    )
    assert upd.status_code == 200
    # Канбан-статус не остаётся на CRM-узле.
    body = _http_json(upd)
    attrs = body.get("attributes")
    assert isinstance(attrs, dict)
    assert "status" not in attrs
    item = await _get_crm_container().work_item_service.find_by_crm_entity("system", entity_id)
    assert item is not None
    assert item.state is WorkItemState.DONE


async def test_delete_task_removes_paired_work_item(crm_client: AsyncClient, unique_id, auth_headers_system):
    create = await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"del {unique_id}", "namespace": f"g_{unique_id}"},
        headers=auth_headers_system,
    )
    entity_id = _entity_id(create)
    wi_svc = _get_crm_container().work_item_service
    assert await wi_svc.find_by_crm_entity("system", entity_id) is not None
    delete = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
    assert delete.status_code in (200, 204)
    assert await wi_svc.find_by_crm_entity("system", entity_id) is None


async def test_merge_tasks_keeps_survivor_work_item(crm_client: AsyncClient, unique_id, auth_headers_system):
    namespace = f"g_{unique_id}"
    survivor = _entity_id(await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"dup {unique_id}", "namespace": namespace},
        headers=auth_headers_system,
    ))
    source = _entity_id(await crm_client.post(
        "/crm/api/v1/entities/",
        json={"entity_type": "task", "name": f"dup {unique_id}", "namespace": namespace},
        headers=auth_headers_system,
    ))
    wi_svc = _get_crm_container().work_item_service
    assert await wi_svc.find_by_crm_entity("system", survivor) is not None
    assert await wi_svc.find_by_crm_entity("system", source) is not None

    merge = await crm_client.post(
        "/crm/api/v1/entities/merge",
        json={"survivor_entity_id": survivor, "source_entity_id": source},
        headers=auth_headers_system,
    )
    assert merge.status_code == 200
    assert await wi_svc.find_by_crm_entity("system", survivor) is not None
    assert await wi_svc.find_by_crm_entity("system", source) is None


def _get_crm_container():
    from apps.crm.container import get_crm_container

    return get_crm_container()
