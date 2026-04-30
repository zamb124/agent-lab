"""
E2E проверка системных seed-пакетов NAMESPACE_TEMPLATE_SEEDS.

Для каждого пакета: создание пространства из шаблона через публичный CRM
API, проверка состава типов и стадий task-доски (как из default, так и
из preset, если он задан в seed).
"""

import re

import pytest

from apps.crm.services.task_board_presets import TASK_ENTITY_TYPE
from apps.crm.system_templates import NAMESPACE_TEMPLATE_SEEDS


def _seed_template_ids() -> list[str]:
    return [seed["template_id"] for seed in NAMESPACE_TEMPLATE_SEEDS]


def _seed_by_id(template_id: str) -> dict:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        if seed["template_id"] == template_id:
            return seed
    raise AssertionError(f"seed `{template_id}` not found")


def _ns_safe(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "x"


@pytest.mark.timeout(120)
class TestNamespaceTemplateSeedPacks:
    """Применение системного шаблона к новому пространству."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _seed_template_ids())
    async def test_create_namespace_applies_seed_types_and_presets(
        self,
        crm_client,
        auth_headers_system,
        unique_id,
        template_id: str,
    ):
        seed = _seed_by_id(template_id)
        ns_name = f"seed_{_ns_safe(template_id)}_{unique_id}"

        create_resp = await crm_client.post(
            "/crm/api/v1/namespaces",
            json={
                "name": ns_name,
                "description": f"E2E seed pack {template_id}",
                "template_id": template_id,
            },
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 201, (
            template_id,
            create_resp.status_code,
            create_resp.text,
        )
        body = create_resp.json()
        assert body["name"] == ns_name

        crm_settings = body.get("crm_settings")
        assert crm_settings is not None, template_id
        presets = crm_settings.get("pipeline_stage_presets") or {}
        expected_presets = (seed.get("crm_settings") or {}).get(
            "pipeline_stage_presets"
        ) or {}
        for board_key, expected in expected_presets.items():
            actual = presets.get(board_key)
            assert actual is not None, (template_id, board_key)
            actual_stage_ids = [stage["id"] for stage in actual["stages"]]
            expected_stage_ids = [stage["id"] for stage in expected["stages"]]
            assert actual_stage_ids == expected_stage_ids, (
                template_id,
                board_key,
                actual_stage_ids,
                expected_stage_ids,
            )

        seed_type_ids = {t["type_id"] for t in seed["types"] if isinstance(t, dict)}
        listed = await crm_client.get(
            "/crm/api/v1/entity-types",
            params={"namespace": ns_name, "limit": 1000},
            headers=auth_headers_system,
        )
        assert listed.status_code == 200, (template_id, listed.status_code, listed.text)
        items = listed.json().get("items") or []
        ns_type_ids = {item["type_id"] for item in items if isinstance(item, dict)}
        missing_types = seed_type_ids - ns_type_ids
        assert not missing_types, (template_id, sorted(missing_types))

        for board_key in expected_presets.keys():
            if board_key == TASK_ENTITY_TYPE:
                stages_resp = await crm_client.get(
                    f"/crm/api/v1/namespaces/{ns_name}/task-board-stages",
                    headers=auth_headers_system,
                )
            else:
                subtype = board_key.split(":", 1)[1]
                stages_resp = await crm_client.get(
                    f"/crm/api/v1/namespaces/{ns_name}/task-board-stages",
                    params={"entity_subtype": subtype},
                    headers=auth_headers_system,
                )
            assert stages_resp.status_code == 200, (
                template_id,
                board_key,
                stages_resp.status_code,
                stages_resp.text,
            )
            stages_body = stages_resp.json()
            assert stages_body["board_key"] == board_key, (template_id, board_key)
            actual_ids = [stage["id"] for stage in stages_body["stages"]]
            expected_ids = [stage["id"] for stage in expected_presets[board_key]["stages"]]
            assert actual_ids == expected_ids, (
                template_id,
                board_key,
                actual_ids,
                expected_ids,
            )
