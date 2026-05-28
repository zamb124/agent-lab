"""
Слияние двух сущностей: перенос связей на survivor, удаление source.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

pytestmark = pytest.mark.timeout(20, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _relationship_rows(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("relationships"))


class TestEntityMerge:
    @pytest.mark.asyncio
    async def test_merge_rewires_relationships_to_survivor(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        a_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeA {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert a_resp.status_code == 200
        a_id = _entity_id(a_resp)

        b_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeB {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert b_resp.status_code == 200
        b_id = _entity_id(b_resp)

        x_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeX {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert x_resp.status_code == 200
        x_id = _entity_id(x_resp)

        rel_resp = await crm_client.post(
            "/crm/api/v1/relationships/",
            json={
                "source_entity_id": b_id,
                "target_entity_id": x_id,
                "relationship_type": "mentions",
            },
            headers=auth_headers_system,
        )
        assert rel_resp.status_code == 200

        merge_resp = await crm_client.post(
            "/crm/api/v1/entities/merge",
            json={
                "survivor_entity_id": a_id,
                "source_entity_id": b_id,
                "scalar_choices": {"name": "survivor"},
                "attribute_choices": {},
            },
            headers=auth_headers_system,
        )
        assert merge_resp.status_code == 200, merge_resp.text
        payload = _http_json(merge_resp)
        entity = object_dict(payload.get("entity"), field="entity")
        assert object_str(entity.get("entity_id"), field="entity_id") == a_id
        assert object_str(entity.get("name"), field="name") == f"MergeA {unique_id}"
        assert object_str(payload.get("merged_from_entity_id"), field="merged_from_entity_id") == b_id

        gone = await crm_client.get(f"/crm/api/v1/entities/{b_id}", headers=auth_headers_system)
        assert gone.status_code == 404

        rels_a = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/relationships",
            headers=auth_headers_system,
        )
        assert rels_a.status_code == 200
        rel_list = _relationship_rows(rels_a)
        targets_from_a: set[str] = set()
        for rel_row in rel_list:
            source_id = object_str(rel_row.get("source_entity_id"), field="source_entity_id")
            if source_id == a_id:
                targets_from_a.add(
                    object_str(rel_row.get("target_entity_id"), field="target_entity_id")
                )
        assert x_id in targets_from_a

    @pytest.mark.asyncio
    async def test_merge_allows_different_entity_type_survivor_type_kept(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        contact_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeContact {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert contact_resp.status_code == 200
        contact_id = _entity_id(contact_resp)

        task_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "task",
                "name": f"MergeTask {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert task_resp.status_code == 200
        task_id = _entity_id(task_resp)

        merge_resp = await crm_client.post(
            "/crm/api/v1/entities/merge",
            json={
                "survivor_entity_id": contact_id,
                "source_entity_id": task_id,
                "scalar_choices": {"name": "survivor"},
                "attribute_choices": {},
            },
            headers=auth_headers_system,
        )
        assert merge_resp.status_code == 200, merge_resp.text
        payload = _http_json(merge_resp)
        entity = object_dict(payload.get("entity"), field="entity")
        assert object_str(entity.get("entity_id"), field="entity_id") == contact_id
        assert object_str(entity.get("entity_type"), field="entity_type") == "contact"
        assert object_str(payload.get("merged_from_entity_id"), field="merged_from_entity_id") == task_id

        gone = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)
        assert gone.status_code == 404
