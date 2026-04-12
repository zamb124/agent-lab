"""
Слияние двух сущностей: перенос связей на survivor, удаление source.
"""

import pytest

pytestmark = pytest.mark.timeout(20, func_only=True)


class TestEntityMerge:
    @pytest.mark.asyncio
    async def test_merge_rewires_relationships_to_survivor(
        self,
        crm_client,
        unique_id,
        auth_headers_system,
    ):
        a_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeA {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert a_resp.status_code == 200
        a_id = a_resp.json()["entity_id"]

        b_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeB {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert b_resp.status_code == 200
        b_id = b_resp.json()["entity_id"]

        x_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeX {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert x_resp.status_code == 200
        x_id = x_resp.json()["entity_id"]

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
        payload = merge_resp.json()
        assert payload["entity"]["entity_id"] == a_id
        assert payload["entity"]["name"] == f"MergeA {unique_id}"
        assert payload["merged_from_entity_id"] == b_id

        gone = await crm_client.get(f"/crm/api/v1/entities/{b_id}", headers=auth_headers_system)
        assert gone.status_code == 404

        rels_a = await crm_client.get(
            f"/crm/api/v1/entities/{a_id}/relationships",
            headers=auth_headers_system,
        )
        assert rels_a.status_code == 200
        rel_list = rels_a.json()["relationships"]
        targets_from_a = {r["target_entity_id"] for r in rel_list if r["source_entity_id"] == a_id}
        assert x_id in targets_from_a

    @pytest.mark.asyncio
    async def test_merge_allows_different_entity_type_survivor_type_kept(
        self,
        crm_client,
        unique_id,
        auth_headers_system,
    ):
        contact_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"MergeContact {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert contact_resp.status_code == 200
        contact_id = contact_resp.json()["entity_id"]

        task_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "task",
                "name": f"MergeTask {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert task_resp.status_code == 200
        task_id = task_resp.json()["entity_id"]

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
        payload = merge_resp.json()
        assert payload["entity"]["entity_id"] == contact_id
        assert payload["entity"]["entity_type"] == "contact"
        assert payload["merged_from_entity_id"] == task_id

        gone = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)
        assert gone.status_code == 404
