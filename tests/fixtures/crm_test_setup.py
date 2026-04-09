"""
Подготовка CRM для E2E: namespace g_{unique_id} и типы contact/organization/project.

Вызывается из фикстуры crm_client, без getfixturevalue внутри async autouse.
"""

from __future__ import annotations

import asyncio
from typing import Any

from httpx import AsyncClient

_CUSTOM_ENTITY_TYPES: list[dict[str, str]] = [
    {"type_id": "note", "name": "Заметка"},
    {"type_id": "meeting", "name": "Встреча"},
    {"type_id": "call", "name": "Звонок"},
    {"type_id": "task", "name": "Задача"},
    {"type_id": "contact", "name": "Контакт"},
    {"type_id": "organization", "name": "Организация"},
    {"type_id": "project", "name": "Проект"},
]


async def _ensure_entity_type(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    type_id: str,
    type_name: str,
    namespace_id: str,
    *,
    max_retries: int = 5,
) -> None:
    for attempt in range(max_retries):
        response = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=headers,
        )
        if response.status_code == 200:
            namespace_ids = response.json().get("namespace_ids") or []
            if namespace_id in namespace_ids and "default" in namespace_ids:
                return
            add_response = await crm_client.post(
                f"/crm/api/v1/entity-types/{type_id}/namespaces",
                json={"namespace_ids": ["default", namespace_id]},
                headers=headers,
            )
            if add_response.status_code == 200:
                return
            await asyncio.sleep(0.05 * (attempt + 1))
            continue
        if response.status_code != 404:
            raise AssertionError(
                f"Не удалось проверить entity type '{type_id}': "
                f"{response.status_code} {response.text}"
            )
        create_response = await crm_client.post(
            "/crm/api/v1/entity-types",
            json={
                "type_id": type_id,
                "name": type_name,
                "namespace_ids": ["default", namespace_id],
            },
            headers=headers,
        )
        if create_response.status_code == 200:
            return
        if create_response.status_code == 409:
            continue
        raise AssertionError(
            f"Не удалось создать entity type '{type_id}': "
            f"{create_response.status_code} {create_response.text}"
        )
    raise AssertionError(
        f"Не удалось обеспечить namespace '{namespace_id}' для entity type '{type_id}' "
        f"после {max_retries} попыток (concurrent xdist race)"
    )


async def _ensure_namespace(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    namespace_id: str,
) -> None:
    response = await crm_client.post(
        "/crm/api/v1/namespaces",
        json={
            "name": namespace_id,
            "description": f"Test namespace {namespace_id}",
            "template_id": "sales",
        },
        headers=headers,
    )
    if response.status_code in (201, 409):
        return
    raise AssertionError(
        f"Не удалось создать namespace '{namespace_id}': "
        f"{response.status_code} {response.text}"
    )


async def ensure_crm_per_test_namespace_and_types(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, Any],
    auth_headers_company2: dict[str, Any],
) -> None:
    namespace_id = f"g_{unique_id}"
    await _ensure_namespace(crm_client, auth_headers_system, namespace_id)
    await _ensure_namespace(crm_client, auth_headers_company2, namespace_id)

    for item in _CUSTOM_ENTITY_TYPES:
        await _ensure_entity_type(
            crm_client=crm_client,
            headers=auth_headers_system,
            type_id=item["type_id"],
            type_name=item["name"],
            namespace_id=namespace_id,
        )
        await _ensure_entity_type(
            crm_client=crm_client,
            headers=auth_headers_company2,
            type_id=item["type_id"],
            type_name=item["name"],
            namespace_id=namespace_id,
        )


async def wait_for_crm_semantic_search_hit(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    *,
    query: str,
    entity_type: str,
    namespace: str = "default",
    max_attempts: int = 60,
    delay_sec: float = 0.15,
) -> None:
    """Ждём, пока только что созданная сущность попадёт в pgvector (дедуп в analyze)."""
    for attempt in range(max_attempts):
        response = await crm_client.get(
            "/crm/api/v1/entities/search",
            params={
                "query": query,
                "entity_type": entity_type,
                "namespace": namespace,
                "limit": 5,
            },
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(
                f"search: {response.status_code} {response.text} (attempt {attempt})"
            )
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if len(items) > 0:
            return
        await asyncio.sleep(delay_sec)
    raise AssertionError(
        f"семантический поиск не увидел {entity_type!r} query={query!r} "
        f"за {max_attempts * delay_sec:.1f}s"
    )


async def wait_daily_summary_rebuild_done(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    *,
    date_str: str,
    namespace: str | None = None,
    max_attempts: int = 100,
    delay_sec: float = 0.1,
) -> dict[str, Any]:
    """Ждём снятия revalidating, чтобы CRM worker не забирал mock LLM следующего теста."""
    body: dict[str, Any] = {"date": date_str}
    if namespace is not None:
        body["namespace"] = namespace
    last: dict[str, Any] = {}
    for _ in range(max_attempts):
        response = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json=body,
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(f"daily-summary: {response.status_code} {response.text}")
        last = response.json()
        if last.get("revalidating") is not True:
            return last
        await asyncio.sleep(delay_sec)
    raise AssertionError(
        f"daily-summary: revalidating не снят для {date_str!r}: {last!r}"
    )
