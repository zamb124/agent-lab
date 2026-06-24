"""
E2E проверка системных seed-пакетов NAMESPACE_TEMPLATE_SEEDS.

Для каждого пакета: создание пространства из шаблона через публичный CRM API и
проверка состава типов. Канбан-досок/пресетов стадий в CRM больше нет (work-
семантика задач — в ядре WorkItem), поэтому доски здесь не проверяются.
"""

from __future__ import annotations

import re
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.system_templates import NAMESPACE_TEMPLATE_SEEDS, NamespaceTemplateSeed
from tests.crm.e2e._json_helpers import (
    json_object,
    object_list,
    object_str,
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


@pytest.mark.timeout(120)
class TestNamespaceTemplateSeedPacks:
    """Применение системного шаблона к новому пространству."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _seed_template_ids())
    async def test_create_namespace_applies_seed_types(
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
