"""Хелперы CRM activity-tasks для UI E2E Networkle Tasks."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

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


def _crm_client(origin: str, auth_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
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
