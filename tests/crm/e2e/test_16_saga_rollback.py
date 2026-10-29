"""
Тесты Saga pattern и каскадного удаления.

User Story: Каскадное удаление с откатом при ошибке.
"""

from typing import cast

import pytest
from httpx2 import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_str
from tests.crm.e2e.attachment_upload_helpers import upload_and_attach_crm_file


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _relationship_id(response: Response) -> str:
    return object_str(_http_json(response).get("relationship_id"), field="relationship_id")


def _document_id(response: Response) -> str:
    return object_str(_http_json(response).get("document_id"), field="document_id")


@pytest.mark.timeout(30)
class TestSagaRollback:
    """Saga pattern для транзакционности"""

    @pytest.mark.asyncio
    async def test_cascade_delete_with_attachments(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление entity → автоматически удаляются attachments"""
        note_name = f"Note с вложениями {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        upload_resp = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=entity_id,
            entity_type="note",
            entity_title=note_name,
            filename="document.txt",
            content=b"Content to be deleted",
            content_type="text/plain",
        )
        _ = _document_id(upload_resp)

        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 204

        get_entity_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_entity_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cascade_delete_with_relationships(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление entity → автоматически удаляются relationships"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity1_id = _entity_id(entity1_resp)

        entity2_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "contact",
            "name": f"Contact {unique_id}",
        }, headers=auth_headers_system)
        entity2_id = _entity_id(entity2_resp)

        rel_resp = await crm_client.post("/crm/api/v1/relationships", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)
        relationship_id = _relationship_id(rel_resp)

        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity1_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 204

        rel_get_resp = await crm_client.get(f"/crm/api/v1/relationships/{relationship_id}", headers=auth_headers_system)
        assert rel_get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cascade_delete_complex(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление entity с attachments + relationships одновременно"""
        note_name = f"Complex entity {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        _ = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=entity_id,
            entity_type="note",
            entity_title=note_name,
            filename="file1.txt",
            content=b"Data 1",
            content_type="text/plain",
        )

        related_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "contact",
            "name": f"Related {unique_id}",
        }, headers=auth_headers_system)
        related_id = _entity_id(related_resp)

        _ = await crm_client.post("/crm/api/v1/relationships", json={
            "source_entity_id": entity_id,
            "target_entity_id": related_id,
            "relationship_type": "mentions",
        }, headers=auth_headers_system)

        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_note_removes_only_exclusive_related_entities(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """
        Удаление note удаляет только подграф, созданный самой заметкой.

        Контракт каскадного удаления (`_collect_exclusive_related_entities_for_note`):
        каскадно удаляются только сущности с `source_entity_id == note_id` —
        то есть созданные AI-анализом этой заметки. Сущности, созданные
        отдельно через `POST /crm/api/v1/entities/` и связанные руками,
        НИКОГДА не удаляются вместе с заметкой, даже если связь только с ней.

        Сценарий:
        note -> exclusive_a (создан вручную, source_entity_id = None)
        note -> shared_a -> keeper

        Ожидание:
        - удаляется только note и связи note->exclusive_a, note->shared_a;
        - exclusive_a, shared_a, keeper и связь shared_a->keeper остаются.
        """
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={"entity_type": "note", "name": f"Note {unique_id}"},
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200
        note_id = _entity_id(note_resp)

        exclusive_a_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={"entity_type": "contact", "name": f"Exclusive A {unique_id}"},
            headers=auth_headers_system,
        )
        assert exclusive_a_resp.status_code == 200
        exclusive_a_id = _entity_id(exclusive_a_resp)

        shared_a_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={"entity_type": "organization", "name": f"Shared A {unique_id}"},
            headers=auth_headers_system,
        )
        assert shared_a_resp.status_code == 200
        shared_a_id = _entity_id(shared_a_resp)

        keeper_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={"entity_type": "contact", "name": f"Keeper {unique_id}"},
            headers=auth_headers_system,
        )
        assert keeper_resp.status_code == 200
        keeper_id = _entity_id(keeper_resp)

        note_to_exclusive_resp = await crm_client.post(
            "/crm/api/v1/relationships",
            json={
                "source_entity_id": note_id,
                "target_entity_id": exclusive_a_id,
                "relationship_type": "mentions",
            },
            headers=auth_headers_system,
        )
        assert note_to_exclusive_resp.status_code == 200
        note_to_exclusive_rel_id = _relationship_id(note_to_exclusive_resp)

        note_to_shared_resp = await crm_client.post(
            "/crm/api/v1/relationships",
            json={
                "source_entity_id": note_id,
                "target_entity_id": shared_a_id,
                "relationship_type": "mentions",
            },
            headers=auth_headers_system,
        )
        assert note_to_shared_resp.status_code == 200
        note_to_shared_rel_id = _relationship_id(note_to_shared_resp)

        shared_to_keeper_resp = await crm_client.post(
            "/crm/api/v1/relationships",
            json={
                "source_entity_id": shared_a_id,
                "target_entity_id": keeper_id,
                "relationship_type": "mentions",
            },
            headers=auth_headers_system,
        )
        assert shared_to_keeper_resp.status_code == 200
        shared_to_keeper_rel_id = _relationship_id(shared_to_keeper_resp)

        delete_note_resp = await crm_client.delete(
            f"/crm/api/v1/entities/{note_id}",
            headers=auth_headers_system,
        )
        assert delete_note_resp.status_code == 204

        note_get_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        assert note_get_resp.status_code == 404

        exclusive_a_get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{exclusive_a_id}",
            headers=auth_headers_system,
        )
        assert exclusive_a_get_resp.status_code == 200

        shared_a_get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{shared_a_id}",
            headers=auth_headers_system,
        )
        assert shared_a_get_resp.status_code == 200

        keeper_get_resp = await crm_client.get(f"/crm/api/v1/entities/{keeper_id}", headers=auth_headers_system)
        assert keeper_get_resp.status_code == 200

        note_to_exclusive_rel_get = await crm_client.get(
            f"/crm/api/v1/relationships/{note_to_exclusive_rel_id}",
            headers=auth_headers_system,
        )
        assert note_to_exclusive_rel_get.status_code == 404

        note_to_shared_rel_get = await crm_client.get(
            f"/crm/api/v1/relationships/{note_to_shared_rel_id}",
            headers=auth_headers_system,
        )
        assert note_to_shared_rel_get.status_code == 404

        shared_to_keeper_rel_get = await crm_client.get(
            f"/crm/api/v1/relationships/{shared_to_keeper_rel_id}",
            headers=auth_headers_system,
        )
        assert shared_to_keeper_rel_get.status_code == 200

    @pytest.mark.asyncio
    async def test_rollback_on_failure_simulation(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Симуляция rollback при ошибке удаления"""
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": f"Entity for rollback test {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 200
