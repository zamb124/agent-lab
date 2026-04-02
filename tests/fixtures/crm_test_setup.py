"""
Подготовка CRM для E2E: namespace g_{unique_id} и типы contact/organization/project.

Вызывается из фикстуры crm_client, без getfixturevalue внутри async autouse.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_CUSTOM_ENTITY_TYPES: list[dict[str, str]] = [
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
) -> None:
    response = await crm_client.get(
        f"/crm/api/v1/entity-types/{type_id}",
        headers=headers,
    )
    if response.status_code == 200:
        entity_type = response.json()
        namespace_ids = entity_type.get("namespace_ids") or []
        updated_namespace_ids = list(namespace_ids)
        if "default" not in updated_namespace_ids:
            updated_namespace_ids.append("default")
        if namespace_id not in updated_namespace_ids:
            updated_namespace_ids.append(namespace_id)
        if updated_namespace_ids != namespace_ids:
            update_response = await crm_client.put(
                f"/crm/api/v1/entity-types/{type_id}",
                json={"namespace_ids": updated_namespace_ids},
                headers=headers,
            )
            if update_response.status_code != 200:
                raise AssertionError(
                    f"Не удалось обновить entity type '{type_id}': "
                    f"{update_response.status_code} {update_response.text}"
                )
        return
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
    if create_response.status_code != 200:
        raise AssertionError(
            f"Не удалось создать entity type '{type_id}': "
            f"{create_response.status_code} {create_response.text}"
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
