"""
Тесты запросов доступа к entities.

User Story: Запросы доступа к чужим/скрытым entities.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _access_request_id(response: Response) -> str:
    return object_str(
        _http_json(response).get("access_request_id"),
        field="access_request_id",
    )


class TestAccessRequests:
    """Запросы доступа к entities"""

    @pytest.mark.asyncio
    async def test_request_access_to_entity(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Запрос доступа к скрытой entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Private note {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": f"Нужен доступ для работы над проектом {unique_id}",
        }, headers=auth_headers_system)
        assert request_resp.status_code == 200

        request = _http_json(request_resp)
        assert "access_request_id" in request
        assert "request_id" not in request
        assert object_str(request.get("status"), field="status") == "pending"
        assert object_str(request.get("resource_id"), field="resource_id") == entity_id

    @pytest.mark.asyncio
    async def test_approve_access_request(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Владелец одобряет запрос доступа"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": "Прошу доступ",
        }, headers=auth_headers_system)
        access_request_id = _access_request_id(request_resp)

        approve_resp = await crm_client.put(
            f"/crm/api/v1/access-requests/{access_request_id}",
            json={"status": "approved"},
            headers=auth_headers_system,
        )
        assert approve_resp.status_code == 200

        get_resp = await crm_client.get(
            f"/crm/api/v1/access-requests/{access_request_id}",
            headers=auth_headers_system,
        )
        request = _http_json(get_resp)
        assert object_str(request.get("status"), field="status") == "approved"

    @pytest.mark.asyncio
    async def test_reject_access_request(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Владелец отклоняет запрос"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": "Запрос",
        }, headers=auth_headers_system)
        access_request_id = _access_request_id(request_resp)

        reject_resp = await crm_client.put(
            f"/crm/api/v1/access-requests/{access_request_id}",
            json={"status": "rejected"},
            headers=auth_headers_system,
        )
        assert reject_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_pending_requests(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Список запросов на рассмотрении"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        _ = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": f"Запрос {unique_id}",
        }, headers=auth_headers_system)

        list_resp = await crm_client.get(
            "/crm/api/v1/access-requests?status=pending",
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200

        requests = object_list(_http_json(list_resp).get("items"))
        pending: list[dict[str, object]] = []
        for request_row in requests:
            message_value = request_row.get("message")
            if isinstance(message_value, str) and unique_id in message_value:
                pending.append(request_row)
        assert len(pending) >= 1
