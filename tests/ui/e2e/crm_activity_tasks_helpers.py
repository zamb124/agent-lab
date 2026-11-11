"""Хелперы CRM activity-tasks для UI E2E Networkle Tasks."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx2

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e_worker import ui_e2e_scope_headers

CRM_API_PREFIX = "/crm/api/v1"
_CRM_HTTP_TIMEOUT_SECONDS = 60.0


def crm_api_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if not parsed.hostname:
        raise ValueError(f"Invalid origin for CRM API: {origin!r}")
    crm_port = SERVICE_UI_REGISTRY["crm"].port
    return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{crm_port}"))


def _crm_client(origin: str, auth_token: str) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=crm_api_origin(origin),
        cookies={"auth_token": auth_token},
        headers=ui_e2e_scope_headers(),
        timeout=_CRM_HTTP_TIMEOUT_SECONDS,
    )


async def crm_api_create_activity_task(
    origin: str,
    auth_token: str,
    *,
    title: str,
    namespace: str,
    priority: str = "normal",
) -> dict[str, Any]:
    async with _crm_client(origin, auth_token) as client:
        response = await client.post(
            f"{CRM_API_PREFIX}/activity-tasks",
            json={
                "title": title,
                "namespace": namespace,
                "priority": priority,
            },
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"POST activity-tasks failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError(f"activity-tasks response must be object, got {type(payload)}")
    return payload


async def crm_api_list_activity_tasks(
    origin: str,
    auth_token: str,
    *,
    namespace: str,
) -> list[dict[str, Any]]:
    async with _crm_client(origin, auth_token) as client:
        response = await client.get(
            f"{CRM_API_PREFIX}/activity-tasks",
            params={"namespace": namespace, "limit": 50, "offset": 0},
        )
    if response.status_code >= 400:
        raise AssertionError(
            f"GET activity-tasks failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise AssertionError("activity-tasks list.items must be array")
    return [item for item in items if isinstance(item, dict)]


async def crm_api_ensure_namespace(
    origin: str,
    auth_token: str,
    *,
    namespace: str,
) -> None:
    async with _crm_client(origin, auth_token) as client:
        response = await client.post(
            f"{CRM_API_PREFIX}/namespaces",
            json={
                "name": namespace,
                "description": f"Doc scenario namespace {namespace}",
                "template_id": "sales",
            },
        )
    if response.status_code not in (200, 201, 409):
        raise AssertionError(
            f"POST namespaces failed: {response.status_code} {response.text}"
        )


async def crm_api_ensure_entity_type(
    origin: str,
    auth_token: str,
    *,
    type_id: str,
    name: str,
    namespace: str,
) -> None:
    from tests.fixtures.crm_test_setup import ensure_entity_type_in_namespace

    async with _crm_client(origin, auth_token) as client:
        await ensure_entity_type_in_namespace(
            crm_client=client,
            headers={},
            type_id=type_id,
            type_name=name,
            namespace_id=namespace,
        )


async def crm_api_ensure_relationship_type(
    origin: str,
    auth_token: str,
    *,
    type_id: str,
    name: str,
    is_directed: bool = True,
) -> None:
    async with _crm_client(origin, auth_token) as client:
        response = await client.post(
            f"{CRM_API_PREFIX}/relationships/types/",
            json={
                "type_id": type_id,
                "name": name,
                "is_directed": is_directed,
            },
        )
    if response.status_code not in (200, 201, 409):
        raise AssertionError(
            f"POST relationships/types failed: {response.status_code} {response.text}"
        )


async def crm_api_create_entity(
    origin: str,
    auth_token: str,
    *,
    entity_type: str,
    name: str,
    namespace: str,
    attributes: dict[str, Any] | None = None,
) -> str:
    async with _crm_client(origin, auth_token) as client:
        response = await client.post(
            f"{CRM_API_PREFIX}/entities",
            json={
                "entity_type": entity_type,
                "name": name,
                "namespace": namespace,
                "attributes": attributes or {},
            },
        )
    if response.status_code != 200:
        raise AssertionError(
            f"POST entities failed: {response.status_code} {response.text}"
        )
    entity_id = response.json().get("entity_id")
    if not isinstance(entity_id, str) or not entity_id:
        raise AssertionError("entities response must contain entity_id")
    return entity_id


async def crm_api_list_suggests(
    origin: str,
    auth_token: str,
    *,
    namespace: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {}
    if status:
        params["status"] = status
    async with _crm_client(origin, auth_token) as client:
        response = await client.get(
            f"{CRM_API_PREFIX}/namespaces/{namespace}/suggests",
            params=params,
        )
    if response.status_code != 200:
        raise AssertionError(
            f"GET suggests failed: {response.status_code} {response.text}"
        )
    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise AssertionError("suggests response must contain items array")
    return [item for item in items if isinstance(item, dict)]


async def crm_api_create_relationship(
    origin: str,
    auth_token: str,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    namespace: str,
) -> None:
    async with _crm_client(origin, auth_token) as client:
        response = await client.post(
            f"{CRM_API_PREFIX}/relationships",
            json={
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "relationship_type": relationship_type,
                "namespace": namespace,
                "weight": 1.0,
            },
        )
    if response.status_code != 200:
        raise AssertionError(
            f"POST relationships failed: {response.status_code} {response.text}"
        )
