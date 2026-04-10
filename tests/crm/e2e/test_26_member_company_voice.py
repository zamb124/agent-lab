"""
Тесты системных типов member/company/namespace, флага is_voice_target и person entity.

Покрывает:
- Наличие и флаги системных типов member, company, namespace
- CRUD флага is_voice_target через API entity types
- Валидация голоса: только типы с is_voice_target=True допустимы
- Кастомный тип с is_voice_target=True как голос заметки
- person-entity/self возвращает member
- Namespace template roundtrip для is_voice_target
"""

import pytest


def _find_outgoing(rels: list, *, source_id: str, rel_type: str) -> dict | None:
    for r in rels:
        if not isinstance(r, dict):
            continue
        if r.get("source_entity_id") == source_id and r.get("relationship_type") == rel_type:
            return r
    return None


@pytest.mark.timeout(120)
class TestSystemTypesFlags:
    """Флаги is_voice_target, extractable, is_context_anchor на системных типах."""

    @pytest.mark.asyncio
    async def test_system_types_include_member_company_namespace(
        self, crm_client, auth_headers_system
    ):
        resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert resp.status_code == 200

        types_by_id = {t["type_id"]: t for t in resp.json()}

        for type_id in ("member", "company", "namespace"):
            assert type_id in types_by_id, f"Системный тип {type_id!r} отсутствует"
            t = types_by_id[type_id]
            assert t["is_system"] is True
            assert t["extractable"] is False
            assert t["is_context_anchor"] is False
            assert "*" in t["namespace_ids"]

    @pytest.mark.asyncio
    async def test_member_and_contact_are_voice_targets(
        self, crm_client, auth_headers_system
    ):
        resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert resp.status_code == 200

        types_by_id = {t["type_id"]: t for t in resp.json()}
        assert types_by_id["member"]["is_voice_target"] is True
        assert types_by_id["contact"]["is_voice_target"] is True

    @pytest.mark.asyncio
    async def test_non_voice_types_have_flag_false(
        self, crm_client, auth_headers_system
    ):
        resp = await crm_client.get("/crm/api/v1/entity-types/", headers=auth_headers_system)
        assert resp.status_code == 200

        types_by_id = {t["type_id"]: t for t in resp.json()}
        for type_id in ("note", "task", "namespace", "company"):
            assert types_by_id[type_id]["is_voice_target"] is False, (
                f"Тип {type_id!r} не должен быть голосом"
            )


@pytest.mark.timeout(120)
class TestVoiceTargetAPI:
    """CRUD флага is_voice_target через API entity types."""

    @pytest.mark.asyncio
    async def test_create_entity_type_with_voice_target_flag(
        self, crm_client, auth_headers_system, unique_id
    ):
        type_id = f"vt_create_{unique_id}"
        resp = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Тип-голос",
                "namespace_ids": ["default"],
                "is_voice_target": True,
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_voice_target"] is True

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["is_voice_target"] is True

    @pytest.mark.asyncio
    async def test_update_entity_type_voice_target_flag(
        self, crm_client, auth_headers_system, unique_id
    ):
        type_id = f"vt_upd_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Тип без голоса",
                "namespace_ids": ["default"],
                "is_voice_target": False,
            },
            headers=auth_headers_system,
        )

        upd_resp = await crm_client.put(
            f"/crm/api/v1/entity-types/{type_id}",
            json={"is_voice_target": True},
            headers=auth_headers_system,
        )
        assert upd_resp.status_code == 200
        assert upd_resp.json()["is_voice_target"] is True

        get_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
        )
        assert get_resp.json()["is_voice_target"] is True

    @pytest.mark.asyncio
    async def test_voice_entity_must_have_voice_target_flag(
        self, crm_client, auth_headers_system, unique_id
    ):
        """Тип без is_voice_target=True не может быть голосом заметки."""
        type_id = f"novt_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Не голос",
                "namespace_ids": ["default"],
                "is_voice_target": False,
            },
            headers=auth_headers_system,
        )

        ent_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Сущность {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert ent_resp.status_code == 200
        ent_id = ent_resp.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка {unique_id}",
                "namespace": "default",
                "voice_entity_id": ent_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_custom_voice_target_type_accepted(
        self, crm_client, auth_headers_system, unique_id
    ):
        """Кастомный тип с is_voice_target=True допустим как голос заметки."""
        type_id = f"custom_vt_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "name": "Кастомный голос",
                "namespace_ids": ["default"],
                "is_voice_target": True,
            },
            headers=auth_headers_system,
        )

        voice_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": type_id,
                "name": f"Голос {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert voice_resp.status_code == 200
        voice_id = voice_resp.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка {unique_id}",
                "namespace": "default",
                "voice_entity_id": voice_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200
        note_id = note_resp.json()["entity_id"]

        rel_resp = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/relationships",
            headers=auth_headers_system,
        )
        assert rel_resp.status_code == 200
        rels = rel_resp.json().get("relationships") or []
        v = _find_outgoing(rels, source_id=note_id, rel_type="note_voice")
        assert v is not None
        assert v["target_entity_id"] == voice_id


@pytest.mark.timeout(120)
class TestPersonEntityMember:
    """person-entity/self возвращает member."""

    @pytest.mark.asyncio
    async def test_person_entity_self_returns_member(
        self, crm_client, auth_headers_system, unique_id
    ):
        await crm_client.put(
            "/crm/api/auth/me",
            json={
                "first_name": "Тестимя",
                "last_name": f"Тестфам{unique_id}",
            },
            headers=auth_headers_system,
        )
        resp = await crm_client.get(
            "/crm/api/v1/entities/person-entity/self",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_type"] == "member"
        assert "entity_id" in body
        assert body["namespace"] == "default"

    @pytest.mark.asyncio
    async def test_member_voice_on_note(
        self, crm_client, auth_headers_system, unique_id
    ):
        """member-сущность платформенного юзера может быть голосом заметки."""
        await crm_client.put(
            "/crm/api/auth/me",
            json={
                "first_name": "Автор",
                "last_name": f"Голос{unique_id}",
            },
            headers=auth_headers_system,
        )
        person_resp = await crm_client.get(
            "/crm/api/v1/entities/person-entity/self",
            headers=auth_headers_system,
        )
        assert person_resp.status_code == 200
        member_id = person_resp.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка от member {unique_id}",
                "namespace": "default",
                "voice_entity_id": member_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200
        note_id = note_resp.json()["entity_id"]

        rel_resp = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/relationships",
            headers=auth_headers_system,
        )
        assert rel_resp.status_code == 200
        rels = rel_resp.json().get("relationships") or []
        v = _find_outgoing(rels, source_id=note_id, rel_type="note_voice")
        assert v is not None
        assert v["target_entity_id"] == member_id


@pytest.mark.timeout(120)
class TestNamespaceTemplateVoiceTarget:
    """Namespace template roundtrip для is_voice_target."""

    @pytest.mark.asyncio
    async def test_namespace_template_type_voice_target_roundtrip(
        self, crm_client, auth_headers_system, unique_id
    ):
        template_id = f"tmpl_vt_{unique_id}"
        r = await crm_client.post(
            "/crm/api/v1/namespaces/templates",
            json={
                "template_id": template_id,
                "name": f"Tpl VT {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        type_id = f"speaker_{unique_id}"
        r = await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": type_id,
                "name": "Спикер",
                "required_fields": {},
                "optional_fields": {},
                "namespace_ids": [],
                "is_voice_target": True,
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201
        assert r.json()["is_voice_target"] is True

        details_resp = await crm_client.get(
            f"/crm/api/v1/namespaces/templates/{template_id}",
            headers=auth_headers_system,
        )
        assert details_resp.status_code == 200
        details = details_resp.json()
        speaker_type = next(
            (t for t in details["types"] if t["type_id"] == type_id),
            None,
        )
        assert speaker_type is not None
        assert speaker_type["is_voice_target"] is True

    @pytest.mark.asyncio
    async def test_namespace_from_template_materializes_voice_target(
        self, crm_client, auth_headers_system, unique_id
    ):
        """Тип с is_voice_target=True из шаблона материализуется в EntityType."""
        template_id = f"tmpl_mat_vt_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/namespaces/templates",
            json={"template_id": template_id, "name": f"Mat {unique_id}"},
            headers=auth_headers_system,
        )

        type_id = f"narrator_{unique_id}"
        await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": type_id,
                "name": "Рассказчик",
                "required_fields": {},
                "optional_fields": {},
                "namespace_ids": [],
                "is_voice_target": True,
            },
            headers=auth_headers_system,
        )

        ns_name = f"ns_mat_vt_{unique_id}"
        r = await crm_client.post(
            "/crm/api/v1/namespaces",
            json={
                "name": ns_name,
                "description": "voice target materialization",
                "template_id": template_id,
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        et_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/{type_id}",
            headers=auth_headers_system,
        )
        assert et_resp.status_code == 200
        assert et_resp.json()["is_voice_target"] is True
