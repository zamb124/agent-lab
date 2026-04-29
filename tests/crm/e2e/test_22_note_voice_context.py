"""
Тесты голоса заметки (note_voice), якоря контекста (in_context), персоны и crm_settings namespace.

Покрывает новый функционал и регрессию: создание заметки без полей voice/context по-прежнему допустимо.
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
class TestNoteVoiceAndContext:
    """Рёбра note_voice / in_context и валидация целей."""

    @pytest.mark.asyncio
    async def test_relationship_types_include_note_voice_and_in_context(
        self, crm_client, auth_headers_system
    ):
        resp = await crm_client.get(
            "/crm/api/v1/relationships/types/",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        types = resp.json()["items"]
        ids = {t["type_id"] for t in types if isinstance(t, dict) and "type_id" in t}
        assert "note_voice" in ids
        assert "in_context" in ids

    @pytest.mark.asyncio
    async def test_person_entity_self_returns_member(self, crm_client, auth_headers_system, unique_id):
        await crm_client.put(
            "/crm/api/auth/me",
            json={
                "first_name": "Персона",
                "last_name": f"Тест{unique_id}",
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
    async def test_create_note_with_voice_and_context_edges(
        self, crm_client, auth_headers_system, unique_id
    ):
        await crm_client.put(
            "/crm/api/auth/me",
            json={
                "first_name": "Автор",
                "last_name": f"Заметки{unique_id}",
            },
            headers=auth_headers_system,
        )

        anchor_type_id = f"anchor_ctx_{unique_id}"
        ct = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": anchor_type_id,
                "name": "Тестовый якорь",
                "namespace": "default",
                "is_context_anchor": True,
            },
            headers=auth_headers_system,
        )
        assert ct.status_code == 200

        voice_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"Голос {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert voice_resp.status_code == 200
        voice_id = voice_resp.json()["entity_id"]

        anchor_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": anchor_type_id,
                "name": f"Якорь {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert anchor_resp.status_code == 200
        anchor_id = anchor_resp.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка {unique_id}",
                "namespace": "default",
                "voice_entity_id": voice_id,
                "context_entity_id": anchor_id,
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

        c = _find_outgoing(rels, source_id=note_id, rel_type="in_context")
        assert c is not None
        assert c["target_entity_id"] == anchor_id

    @pytest.mark.asyncio
    async def test_voice_rejects_non_voice_target_type(self, crm_client, auth_headers_system, unique_id):
        """note не имеет is_voice_target=True, поэтому не может быть голосом."""
        wrong = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Не голос {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert wrong.status_code == 200
        wrong_id = wrong.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка {unique_id}",
                "namespace": "default",
                "voice_entity_id": wrong_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_context_must_be_anchor_type(
        self, crm_client, auth_headers_system, unique_id
    ):
        plain = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "contact",
                "name": f"Не якорь {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert plain.status_code == 200
        plain_id = plain.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Заметка {unique_id}",
                "namespace": "default",
                "context_entity_id": plain_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 422

    @pytest.mark.asyncio
    async def test_note_minimal_create_succeeds(
        self, crm_client, auth_headers_system, unique_id
    ):
        """Регрессия: минимальное создание заметки (как test_01) без полей voice/context."""
        resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Простая заметка {unique_id}",
                "description": "без голоса/контекста в теле запроса",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_type"] == "note"
        assert "entity_id" in body

    @pytest.mark.asyncio
    async def test_namespace_crm_settings_roundtrip(self, crm_client, auth_headers_system, unique_id):
        template_id = f"tmpl_crmset_{unique_id}"
        r = await crm_client.post(
            "/crm/api/v1/namespaces/templates",
            json={
                "template_id": template_id,
                "name": f"Tpl {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        r = await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": f"lead_{unique_id}",
                "name": "Лид",
                "required_fields": {"s": {"type": "string"}},
                "optional_fields": {},
                "namespace_ids": [],
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        ns_name = f"ns_crm_{unique_id}"
        r = await crm_client.post(
            "/crm/api/v1/namespaces",
            json={
                "name": ns_name,
                "description": "crm settings test",
                "template_id": template_id,
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        r = await crm_client.put(
            f"/crm/api/v1/namespaces/{ns_name}",
            json={
                "crm_settings": {
                    "show_note_voice_ui": False,
                    "default_note_voice": "none",
                    "default_context_entity_id": None,
                },
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("crm_settings") is not None
        cs = body["crm_settings"]
        assert cs["show_note_voice_ui"] is False
        assert cs["default_note_voice"] == "none"

        listed = await crm_client.get(
            "/crm/api/v1/namespaces",
            headers=auth_headers_system,
        )
        assert listed.status_code == 200
        namespaces = listed.json().get("items") or []
        match = next((n for n in namespaces if n.get("name") == ns_name), None)
        assert match is not None
        assert match.get("crm_settings") is not None
        assert match["crm_settings"]["default_note_voice"] == "none"

    @pytest.mark.asyncio
    async def test_note_in_namespace_with_default_voice_none_has_no_note_voice_edge(
        self, crm_client, auth_headers_system, unique_id
    ):
        template_id = f"tmpl_nonvoice_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/namespaces/templates",
            json={"template_id": template_id, "name": f"T{unique_id}"},
            headers=auth_headers_system,
        )
        await crm_client.post(
            f"/crm/api/v1/namespaces/templates/{template_id}/types",
            json={
                "type_id": f"lead_nv_{unique_id}",
                "name": "Лид",
                "required_fields": {"s": {"type": "string"}},
                "optional_fields": {},
                "namespace_ids": [],
            },
            headers=auth_headers_system,
        )
        ns_name = f"ns_nv_{unique_id}"
        r = await crm_client.post(
            "/crm/api/v1/namespaces",
            json={
                "name": ns_name,
                "description": "d",
                "template_id": template_id,
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 201

        lead_tid = f"lead_nv_{unique_id}"
        r = await crm_client.put(
            f"/crm/api/v1/namespaces/{ns_name}",
            json={
                "allowed_type_ids": ["note", lead_tid, "namespace"],
                "crm_settings": {
                    "show_note_voice_ui": True,
                    "default_note_voice": "none",
                    "default_context_entity_id": None,
                },
            },
            headers=auth_headers_system,
        )
        assert r.status_code == 200

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"NV {unique_id}",
                "namespace": ns_name,
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
        assert v is None

    @pytest.mark.asyncio
    async def test_update_note_clears_context_when_null_in_payload(
        self, crm_client, auth_headers_system, unique_id
    ):
        anchor_type_id = f"anchor_upd_{unique_id}"
        await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": anchor_type_id,
                "name": "Якорь upd",
                "namespace": "default",
                "is_context_anchor": True,
            },
            headers=auth_headers_system,
        )
        anchor_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": anchor_type_id,
                "name": f"A {unique_id}",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        anchor_id = anchor_resp.json()["entity_id"]

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": f"Upd {unique_id}",
                "namespace": "default",
                "context_entity_id": anchor_id,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200
        note_id = note_resp.json()["entity_id"]

        rel1 = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/relationships",
            headers=auth_headers_system,
        )
        rels1 = rel1.json().get("relationships") or []
        assert _find_outgoing(rels1, source_id=note_id, rel_type="in_context") is not None

        upd = await crm_client.put(
            f"/crm/api/v1/entities/{note_id}",
            json={
                "context_entity_id": None,
            },
            headers=auth_headers_system,
        )
        assert upd.status_code == 200

        rel2 = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/relationships",
            headers=auth_headers_system,
        )
        rels2 = rel2.json().get("relationships") or []
        assert _find_outgoing(rels2, source_id=note_id, rel_type="in_context") is None