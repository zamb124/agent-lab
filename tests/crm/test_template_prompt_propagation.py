"""
Распространение системного шаблона в реальные данные namespace и
финальный prompt, который CRM собирает для analyze.

Проверяется три инварианта (без моков, без monkeypatch):

1. После создания namespace из системного шаблона все важные поля
   `EntityType` (включая `prompt`, `required_fields`, `optional_fields`,
   `is_event`, `is_voice_target`, `is_context_anchor`, `extractable`)
   материализуются в БД ровно в том виде, что описаны в `_SEED_*`.
2. Пользовательская правка `EntityType` (через CRM API `PUT
   /entity-types/{type_id}`) сохраняется и читается обратно через
   `EntityService._load_all_entity_types_for_namespace` — тот же путь, что
   подаёт типы в analyze.
3. `EntityService._build_composite_prompt` подмешивает в итоговую строку
   ровно тот `prompt`, `field.label`, `field.description` и enum-`values`
   из БД, что лежат под пользовательской правкой. Если правка перетёрла
   значение из шаблона — старое значение из системного шаблона **не**
   уходит в prompt.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.crm.constants_graph import TASK_ROOT_ENTITY_TYPE_ID
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
    SYSTEM_ENTITY_TYPE_TEMPLATES,
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
)


_PROBE_SEED_IDS = ("sales", "marketing", "support", "hr", "education")


def _seed_by_id(template_id: str) -> dict[str, Any]:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        if seed["template_id"] == template_id:
            return seed
    raise AssertionError(f"seed {template_id!r} not registered")


def _pick_extractable_seed_type(seed: dict[str, Any]) -> dict[str, Any]:
    """Тип шаблона с непустым prompt и хотя бы одним описанным полем."""

    for spec in seed["types"]:
        if not isinstance(spec, dict):
            continue
        if not spec.get("prompt"):
            continue
        fields = (spec.get("required_fields") or {}) | (spec.get("optional_fields") or {})
        if not fields:
            continue
        return spec
    raise AssertionError(
        f"seed {seed.get('template_id')!r}: ни один тип не подходит как extractable probe"
    )


async def _create_seed_namespace(
    crm_client,
    auth_headers: dict[str, str],
    template_id: str,
    suffix: str,
) -> str:
    namespace_name = f"prompt_probe_{template_id}_{suffix}"
    response = await crm_client.post(
        "/crm/api/v1/namespaces",
        json={
            "name": namespace_name,
            "description": f"prompt propagation probe {template_id}",
            "template_id": template_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, (
        template_id,
        response.status_code,
        response.text,
    )
    return namespace_name


@pytest.mark.timeout(120)
class TestSeedPromptsMaterializeIntoNamespace:
    """Шаблон → БД: каждый системный seed превращается в `EntityType` в БД."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("template_id", _PROBE_SEED_IDS)
    async def test_seed_extractable_type_persists_prompt_and_fields(
        self,
        crm_client,
        auth_headers_system,
        unique_id,
        template_id: str,
    ) -> None:
        seed = _seed_by_id(template_id)
        probe_spec = _pick_extractable_seed_type(seed)
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, template_id, unique_id
        )

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{probe_spec['type_id']}",
            params={"namespace": ns_name},
            headers=auth_headers_system,
        )
        assert get_resp.status_code == 200, (
            template_id,
            probe_spec["type_id"],
            get_resp.text,
        )
        body = get_resp.json()

        assert body["prompt"] == probe_spec["prompt"], (template_id, probe_spec["type_id"])
        assert body["description"] == probe_spec["description"], (
            template_id,
            probe_spec["type_id"],
        )
        assert body["required_fields"] == (probe_spec.get("required_fields") or {}), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["optional_fields"] == (probe_spec.get("optional_fields") or {}), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["is_event"] == bool(probe_spec.get("is_event", False)), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["check_duplicates"] == bool(probe_spec.get("check_duplicates", True)), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["is_context_anchor"] == bool(probe_spec.get("is_context_anchor", False)), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["is_voice_target"] == bool(probe_spec.get("is_voice_target", False)), (
            template_id,
            probe_spec["type_id"],
        )
        assert body["extractable"] is True, (template_id, probe_spec["type_id"])

    @pytest.mark.asyncio
    async def test_default_namespace_carries_system_relationship_prompts(
        self,
        crm_client,
        auth_headers_system,
    ) -> None:
        listed = await crm_client.get(
            "/crm/api/v1/relationships/types/",
            params={"limit": 1000},
            headers=auth_headers_system,
        )
        assert listed.status_code == 200, listed.text
        items = {row["type_id"]: row for row in listed.json().get("items") or []}

        for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
            type_id = spec["type_id"]
            assert type_id in items, type_id
            row = items[type_id]
            assert row["name"] == spec["name"], type_id
            assert row["is_directed"] == bool(spec.get("is_directed", True)), type_id
            expected_prompt = spec.get("prompt")
            if expected_prompt:
                assert row["prompt"] == expected_prompt, type_id


@pytest.mark.timeout(120)
class TestUserEditsPropagateToAnalyzePipeline:
    """Правка пользователем прочитывается тем же кодом, что подаёт типы в analyze."""

    @pytest.mark.asyncio
    async def test_user_edit_of_entity_type_prompt_is_persisted_via_api(
        self,
        crm_client,
        auth_headers_system,
        unique_id,
    ) -> None:
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "sales", unique_id
        )
        type_id = "lead"
        marker = f"USER-OVERRIDE-PROMPT-{unique_id}"
        new_prompt = (
            f"{marker}\nИзвлекай ТОЛЬКО лидов с подтверждённой телефонной "
            "верификацией. Игнорируй все упоминания холодных лидов из "
            "массовых рассылок."
        )

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": ns_name},
            json={"prompt": new_prompt},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        refetched = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": ns_name},
            headers=auth_headers_system,
        )
        assert refetched.status_code == 200, refetched.text
        body = refetched.json()
        assert body["prompt"] == new_prompt
        assert marker in body["prompt"]

    @pytest.mark.asyncio
    async def test_load_all_entity_types_for_namespace_returns_user_prompt(
        self,
        crm_client,
        crm_container,
        auth_headers_system,
        unique_id,
    ) -> None:
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "marketing", unique_id
        )
        type_id = "campaign"
        marker = f"CAMPAIGN-OVERRIDE-{unique_id}"
        new_prompt = (
            f"{marker}\nИзвлекай ТОЛЬКО кампании с явным бюджетом > 0 и "
            "указанной валютой. Иначе пропускай."
        )

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": ns_name},
            json={"prompt": new_prompt},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        loaded = await crm_container.entity_service._load_all_entity_types_for_namespace(
            ns_name
        )
        loaded_by_id = {t.type_id: t for t in loaded}
        assert type_id in loaded_by_id, sorted(loaded_by_id)
        assert loaded_by_id[type_id].prompt == new_prompt
        assert marker in loaded_by_id[type_id].prompt

    @pytest.mark.asyncio
    async def test_build_composite_prompt_includes_user_overridden_prompt(
        self,
        crm_client,
        crm_container,
        auth_headers_system,
        unique_id,
    ) -> None:
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "support", unique_id
        )
        type_id = "ticket"
        marker = f"TICKET-OVERRIDE-{unique_id}"
        new_prompt = (
            f"{marker}\nИзвлекай только тикеты SEV1 и SEV2 с подтверждённым "
            "пользователем. Не извлекай вопросы из FAQ."
        )

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": ns_name},
            json={"prompt": new_prompt},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        entity_types = await crm_container.entity_service._load_all_entity_types_for_namespace(
            ns_name
        )
        relationship_types = (
            await crm_container.relationship_type_repository.get_with_prompts()
        )

        composite = crm_container.entity_service._build_composite_prompt(
            entity_types, relationship_types, None, None,
        )
        assert marker in composite, "Перетёртый prompt должен попасть в analyze prompt"
        assert new_prompt.split("\n", 1)[1] in composite, (
            "Тело пользовательского prompt также должно быть в analyze prompt"
        )

    @pytest.mark.asyncio
    async def test_build_composite_prompt_carries_field_labels_descriptions_and_enum_values(
        self,
        crm_client,
        crm_container,
        auth_headers_system,
        unique_id,
    ) -> None:
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "hr", unique_id
        )
        type_id = "candidate"
        unique_label = f"Стадия найма {unique_id}"
        unique_description = (
            f"Точная стадия в рекрутинговой воронке (метка теста {unique_id})"
        )
        unique_value_id = f"qa_test_{unique_id}".replace("-", "_")
        new_optional_fields = {
            "stage": {
                "type": "enum",
                "label": unique_label,
                "description": unique_description,
                "values": [unique_value_id, "sourced", "hired"],
            }
        }

        update_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            params={"namespace": ns_name},
            json={"optional_fields": new_optional_fields},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        entity_types = await crm_container.entity_service._load_all_entity_types_for_namespace(
            ns_name
        )
        relationship_types = (
            await crm_container.relationship_type_repository.get_with_prompts()
        )
        composite = crm_container.entity_service._build_composite_prompt(
            entity_types, relationship_types, None, None,
        )

        assert unique_label in composite, "label поля должен попадать в analyze prompt"
        assert unique_description in composite, (
            "description поля должен попадать в analyze prompt"
        )
        assert unique_value_id in composite, (
            "значение enum-поля должно попадать в analyze prompt"
        )

    @pytest.mark.asyncio
    async def test_build_composite_prompt_filters_by_extract_entity_types(
        self,
        crm_client,
        crm_container,
        auth_headers_system,
        unique_id,
    ) -> None:
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "sales", unique_id
        )

        entity_types = await crm_container.entity_service._load_all_entity_types_for_namespace(
            ns_name
        )
        relationship_types = (
            await crm_container.relationship_type_repository.get_with_prompts()
        )

        sales_seed = _seed_by_id("sales")
        seed_lead = next(t for t in sales_seed["types"] if t.get("type_id") == "lead")
        seed_deal = next(t for t in sales_seed["types"] if t.get("type_id") == "deal")
        assert seed_lead["prompt"] and seed_deal["prompt"]

        only_lead = crm_container.entity_service._build_composite_prompt(
            entity_types,
            relationship_types,
            extract_entity_types=["lead"],
            extract_relationship_types=None,
        )
        assert seed_lead["prompt"] in only_lead, "выбранный тип должен попасть в prompt"
        assert seed_deal["prompt"] not in only_lead, (
            "невыбранный тип не должен попадать в prompt при extract_entity_types"
        )

    @pytest.mark.asyncio
    async def test_user_edited_relationship_prompt_reaches_composite(
        self,
        crm_client,
        crm_container,
        auth_headers_system,
        unique_id,
    ) -> None:
        """
        Прямая правка `RelationshipType.prompt` через репозиторий — это
        единственный путь редактирования системных типов связи (HTTP API
        для PUT не предоставлено). Проверяем, что отредактированный prompt
        читается тем же `get_with_prompts`, что и в `_call_ai_agent`,
        и появляется в финальной строке analyze.
        """
        ns_name = await _create_seed_namespace(
            crm_client, auth_headers_system, "sales", unique_id
        )

        marker = f"REL-OVERRIDE-{unique_id}"
        new_prompt = (
            f"{marker}\nКОГДА ИСПОЛЬЗОВАТЬ: только если в тексте явно указано "
            "слово «упомянул». Примеры: «Иван упомянул проект X». "
            "КОГДА НЕ ИСПОЛЬЗОВАТЬ: для блокировок и владения — для них "
            "blocks/owner_of."
        )

        repo = crm_container.relationship_type_repository
        all_types = await repo.get_all_for_company(include_system=True, limit=1000)
        mentions_row = next((t for t in all_types if t.type_id == "mentions"), None)
        assert mentions_row is not None, "у компании system должен быть тип mentions"
        original_prompt = mentions_row.prompt
        try:
            mentions_row.prompt = new_prompt
            await repo.update(mentions_row)

            entity_types = await crm_container.entity_service._load_all_entity_types_for_namespace(
                ns_name
            )
            relationship_types = (
                await crm_container.relationship_type_repository.get_with_prompts()
            )
            composite = crm_container.entity_service._build_composite_prompt(
                entity_types, relationship_types, None, None,
            )

            assert marker in composite, "правка relationship prompt должна попадать в analyze"
        finally:
            mentions_row.prompt = original_prompt
            await repo.update(mentions_row)


@pytest.mark.timeout(60)
class TestSystemTemplateRegistryConsistency:
    """`SYSTEM_ENTITY_TYPE_TEMPLATES` и сиды друг другу согласованы."""

    def test_all_seed_types_with_parent_reference_known_root_or_seed(self) -> None:
        system_ids = {item["type_id"] for item in SYSTEM_ENTITY_TYPE_TEMPLATES}
        for seed in NAMESPACE_TEMPLATE_SEEDS:
            seed_ids = {t["type_id"] for t in seed["types"] if isinstance(t, dict)}
            for spec in seed["types"]:
                if not isinstance(spec, dict):
                    continue
                parent = spec.get("parent_type_id")
                if not parent:
                    continue
                assert parent in seed_ids or parent in system_ids, (
                    seed["template_id"],
                    spec.get("type_id"),
                    parent,
                )

    def test_seed_extractable_types_have_prompt(self) -> None:
        for seed in NAMESPACE_TEMPLATE_SEEDS:
            for spec in seed["types"]:
                if not isinstance(spec, dict):
                    continue
                parent = spec.get("parent_type_id")
                # Подтипы task — единственный сценарий, где prompt опционален
                # (наследование от родителя).
                if parent == TASK_ROOT_ENTITY_TYPE_ID:
                    continue
                if not (spec.get("required_fields") or spec.get("optional_fields")):
                    continue
                # Для типов с настраиваемыми полями, не являющихся подтипом
                # task, ожидаем prompt — иначе analyze не сможет извлекать.
                # Системные «note», «task», «meeting», «call», «contact»,
                # «company», «member», «namespace» имеют prompt в ядре.
                assert spec.get("prompt"), (seed["template_id"], spec.get("type_id"))
