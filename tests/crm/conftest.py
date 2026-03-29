"""
CRM-специфичные фикстуры.

Основные фикстуры теперь в tests/fixtures/:
- crm_client (ASGI transport) - из tests/fixtures/clients.py
- crm_service (реальный HTTP) - из tests/fixtures/services.py
- crm_client_http (HTTP к реальному сервису) - из tests/fixtures/clients.py

Здесь остаются только CRM-специфичные утилиты.
"""

import pytest
import pytest_asyncio


_CUSTOM_ENTITY_TYPES = [
    {"type_id": "contact", "name": "Контакт"},
    {"type_id": "organization", "name": "Организация"},
    {"type_id": "project", "name": "Проект"},
]


async def _ensure_entity_type(
    crm_client,
    headers: dict,
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
    crm_client,
    headers: dict,
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


@pytest_asyncio.fixture(autouse=True)
async def ensure_crm_test_entity_types(
    crm_client,
    auth_headers_system,
    auth_headers_company2,
    unique_id,
):
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
    yield


@pytest.fixture
def crm_container():
    """
    CRM Container для прямого доступа к сервисам.
    
    Используется ТОЛЬКО если нужен прямой доступ к репозиториям/сервисам.
    Для E2E тестов используй crm_client!
    """
    from apps.crm.container import get_crm_container
    return get_crm_container()

