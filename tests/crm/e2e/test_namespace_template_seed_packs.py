"""
E2E проверка системных seed-пакетов NAMESPACE_TEMPLATE_SEEDS.

Для каждого пакета: создание пространства из шаблона через публичный CRM
API, проверка состава типов и стадий task-доски (как из default, так и
из preset, если он задан в seed).
"""

from __future__ import annotations

import re
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.services.task_board_presets import TASK_ENTITY_TYPE
from apps.crm.system_templates import NAMESPACE_TEMPLATE_SEEDS, NamespaceTemplateSeed
from tests.crm.e2e._json_helpers import (
    json_object,
    object_dict,
    object_list,
    object_str,
    optional_object_dict,
)


def _seed_template_ids() -> list[str]:
    return [seed["template_id"] for seed in NAMESPACE_TEMPLATE_SEEDS]


def _seed_by_id(template_id: str) -> NamespaceTemplateSeed:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        if seed["template_id"] == template_id:
            return seed
    raise AssertionError(f"seed `{template_id}` not found")


def _ns_safe(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "x"


def _response_json_object(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _stage_ids(stages_raw: object) -> list[str]:
    return [
        object_str(stage.get("id"), field="stage.id")
        for stage in object_list(stages_raw)
        if isinstance(stage.get("id"), str)
    ]


@pytest.mark.timeout(120)
class TestNamespaceTemplateSeedPacks:
    """Применение системного шаблона к новому пространству."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _seed_template_ids())
    async def test_create_namespace_applies_seed_types_and_presets(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict[str, str],
        unique_id: str,
        template_id: str,
    ) -> None:
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
        body = _response_json_object(create_resp)
        assert body.get("name") == ns_name

        crm_settings = object_dict(body.get("crm_settings"), field="crm_settings")
        presets = optional_object_dict(crm_settings.get("pipeline_stage_presets"))
        seed_crm = optional_object_dict(seed.get("crm_settings"))
        expected_presets = optional_object_dict(seed_crm.get("pipeline_stage_presets"))

        for board_key, expected_raw in expected_presets.items():
            if not isinstance(expected_raw, dict):
                continue
            actual_raw = presets.get(board_key)
            assert actual_raw is not None, (template_id, board_key)
            actual = object_dict(actual_raw, field=f"presets[{board_key}]")
            expected = object_dict(cast(object, expected_raw), field=f"expected_presets[{board_key}]")
            actual_stage_ids = _stage_ids(actual.get("stages"))
            expected_stage_ids = _stage_ids(expected.get("stages"))
            assert actual_stage_ids == expected_stage_ids, (
                template_id,
                board_key,
                actual_stage_ids,
                expected_stage_ids,
            )

        seed_type_ids = {spec["type_id"] for spec in seed["types"]}
        listed = await crm_client.get(
            "/crm/api/v1/entity-types",
            params={"namespace": ns_name, "limit": 1000},
            headers=auth_headers_system,
        )
        assert listed.status_code == 200, (template_id, listed.status_code, listed.text)
        listed_body = _response_json_object(listed)
        items = object_list(listed_body.get("items"))
        ns_type_ids = {object_str(item.get("type_id"), field="type_id") for item in items}
        missing_types = seed_type_ids - ns_type_ids
        assert not missing_types, (template_id, sorted(missing_types))

        for board_key in expected_presets:
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
            stages_body = _response_json_object(stages_resp)
            assert stages_body.get("board_key") == board_key, (template_id, board_key)
            actual_ids = _stage_ids(stages_body.get("stages"))
            expected_board = optional_object_dict(expected_presets.get(board_key))
            expected_ids = _stage_ids(expected_board.get("stages"))
            assert actual_ids == expected_ids, (
                template_id,
                board_key,
                actual_ids,
                expected_ids,
            )
