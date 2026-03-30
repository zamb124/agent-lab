"""
Тесты гранулярной editability namespace.

Проверяет все сценарии безопасного редактирования пространств:
- добавление типов всегда разрешено
- удаление используемых типов запрещено
- удаление неиспользуемых типов разрешено
- редактирование prompt/description/name типа всегда разрешено
- type_id неизменяем
- описание namespace можно менять всегда
"""

import pytest


async def _create_namespace_with_types(crm_client, headers, unique_id, type_ids):
    """Хелпер: создает шаблон, типы и namespace."""
    template_id = f"tmpl_{unique_id}"
    namespace_name = f"ns_{unique_id}"

    resp = await crm_client.post("/crm/api/v1/namespaces/templates", json={
        "template_id": template_id,
        "name": f"Template {unique_id}",
    }, headers=headers)
    assert resp.status_code == 201

    for tid in type_ids:
        resp = await crm_client.post(f"/crm/api/v1/namespaces/templates/{template_id}/types", json={
            "type_id": tid,
            "name": f"Type {tid}",
            "required_fields": {"field": {"type": "string"}},
            "optional_fields": {},
            "namespace_ids": [],
        }, headers=headers)
        assert resp.status_code == 201

    resp = await crm_client.post("/crm/api/v1/namespaces", json={
        "name": namespace_name,
        "description": f"Namespace {unique_id}",
        "template_id": template_id,
    }, headers=headers)
    assert resp.status_code == 201

    return namespace_name, template_id


class TestNamespaceEditabilityEmpty:
    """Editability для пустого namespace (без сущностей)"""

    @pytest.mark.asyncio
    async def test_empty_namespace_all_types_removable(self, crm_client, unique_id, auth_headers_system):
        """В пустом namespace все типы можно убрать"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        editability = resp.json()

        assert editability["entity_count"] == 0
        assert editability["has_entities"] is False
        assert editability["can_add_types"] is True
        assert editability["can_update_allowed_types"] is True
        assert editability["locked_type_ids"] == []
        assert type_a in editability["removable_type_ids"]
        assert type_b in editability["removable_type_ids"]
        assert type_a in editability["current_allowed_type_ids"]
        assert type_b in editability["current_allowed_type_ids"]

    @pytest.mark.asyncio
    async def test_empty_namespace_can_remove_all_types(self, crm_client, unique_id, auth_headers_system):
        """В пустом namespace можно убрать все типы"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": []},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        assert types_resp.status_code == 200
        assert len(types_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_empty_namespace_description_always_editable(self, crm_client, unique_id, auth_headers_system):
        """Описание пустого namespace всегда можно менять"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"description": "Обновленное описание"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Обновленное описание"


class TestNamespaceEditabilityWithEntities:
    """Editability когда в namespace есть сущности"""

    @pytest.mark.asyncio
    async def test_used_type_locked_unused_removable(self, crm_client, unique_id, auth_headers_system):
        """Тип с сущностями залочен, тип без сущностей можно убрать"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        editability = resp.json()

        assert editability["entity_count"] >= 1
        assert editability["has_entities"] is True
        assert editability["can_add_types"] is True
        assert type_used in editability["locked_type_ids"]
        assert type_unused in editability["removable_type_ids"]
        assert type_used not in editability["removable_type_ids"]
        assert type_unused not in editability["locked_type_ids"]

    @pytest.mark.asyncio
    async def test_cannot_remove_used_type(self, crm_client, unique_id, auth_headers_system):
        """422 при попытке убрать тип с сущностями"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_unused]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        assert type_used in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_can_remove_unused_type_when_entities_exist(self, crm_client, unique_id, auth_headers_system):
        """Можно убрать неиспользуемый тип, даже если в namespace есть сущности другого типа"""
        type_used = f"used_{unique_id}"
        type_unused = f"unused_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_unused],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_used]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = [t["type_id"] for t in types_resp.json()]
        assert type_used in type_ids
        assert type_unused not in type_ids

    @pytest.mark.asyncio
    async def test_can_add_new_type_when_entities_exist(self, crm_client, unique_id, auth_headers_system):
        """Можно добавить новый тип в namespace с сущностями"""
        type_existing = f"exist_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_existing],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_existing,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        extra_type_id = f"extra_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": extra_type_id,
            "name": "Extra Type",
            "namespace_ids": ["default"],
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_existing, extra_type_id]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = [t["type_id"] for t in types_resp.json()]
        assert type_existing in type_ids
        assert extra_type_id in type_ids

    @pytest.mark.asyncio
    async def test_description_editable_with_entities(self, crm_client, unique_id, auth_headers_system):
        """Описание namespace можно менять при наличии сущностей"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_a,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"description": "Новое описание с сущностями"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Новое описание с сущностями"

    @pytest.mark.asyncio
    async def test_cannot_remove_multiple_used_types(self, crm_client, unique_id, auth_headers_system):
        """422 при попытке убрать несколько используемых типов"""
        type_a = f"a_{unique_id}"
        type_b = f"b_{unique_id}"
        type_c = f"c_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b, type_c],
        )

        for tid in [type_a, type_b]:
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": tid,
                "name": f"Entity {tid}",
                "namespace": namespace_name,
            }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_c]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_and_remove_simultaneously(self, crm_client, unique_id, auth_headers_system):
        """Можно одновременно добавить новый тип и убрать неиспользуемый"""
        type_used = f"used_{unique_id}"
        type_removable = f"rmv_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_used, type_removable],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_used,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        type_added = f"added_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_added,
            "name": "Added Type",
            "namespace_ids": ["default"],
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_used, type_added]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = [t["type_id"] for t in types_resp.json()]
        assert type_used in type_ids
        assert type_added in type_ids
        assert type_removable not in type_ids


class TestEntityTypeImmutability:
    """type_id неизменяем, но prompt/description/name можно менять"""

    @pytest.mark.asyncio
    async def test_can_update_prompt_and_description(self, crm_client, unique_id, auth_headers_system):
        """Prompt и описание типа можно менять через PUT /entity-types/{type_id}"""
        type_id = f"editable_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Тестовый тип",
            "prompt": "Старый промпт",
            "description": "Старое описание",
        }, headers=auth_headers_system)

        resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "prompt": "Новый промпт для AI-извлечения",
            "description": "Новое описание типа",
        }, headers=auth_headers_system)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["prompt"] == "Новый промпт для AI-извлечения"
        assert updated["description"] == "Новое описание типа"
        assert updated["type_id"] == type_id

    @pytest.mark.asyncio
    async def test_can_update_name_icon_color(self, crm_client, unique_id, auth_headers_system):
        """Название, иконку и цвет можно менять"""
        type_id = f"visual_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Старое название",
            "icon": "folder",
            "color": "#000000",
        }, headers=auth_headers_system)

        resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "name": "Обновленное название",
            "icon": "star",
            "color": "#FF5722",
        }, headers=auth_headers_system)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Обновленное название"
        assert updated["icon"] == "star"
        assert updated["color"] == "#FF5722"

    @pytest.mark.asyncio
    async def test_can_update_required_optional_fields(self, crm_client, unique_id, auth_headers_system):
        """Схему полей можно менять"""
        type_id = f"schema_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Schema Type",
            "required_fields": {"old_field": {"type": "string"}},
            "optional_fields": {},
        }, headers=auth_headers_system)

        resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "required_fields": {"new_field": {"type": "number", "label": "Число"}},
            "optional_fields": {"extra": {"type": "string", "label": "Доп"}},
        }, headers=auth_headers_system)
        assert resp.status_code == 200
        updated = resp.json()
        assert "new_field" in updated["required_fields"]
        assert "extra" in updated["optional_fields"]

    @pytest.mark.asyncio
    async def test_type_id_not_changeable_via_path(self, crm_client, unique_id, auth_headers_system):
        """type_id определяется path-параметром и не меняется"""
        type_id = f"immutable_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "Immutable ID",
        }, headers=auth_headers_system)

        resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "name": "Changed Name Only",
        }, headers=auth_headers_system)
        assert resp.status_code == 200
        assert resp.json()["type_id"] == type_id

    @pytest.mark.asyncio
    async def test_can_update_type_with_existing_entities(self, crm_client, unique_id, auth_headers_system):
        """Метаданные типа можно менять даже если есть сущности этого типа"""
        type_id = f"inuse_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_id,
            "name": "In Use Type",
            "prompt": "Старый промпт",
        }, headers=auth_headers_system)

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_id,
            "name": f"Entity {unique_id}",
        }, headers=auth_headers_system)

        resp = await crm_client.put(f"/crm/api/v1/entity-types/{type_id}", json={
            "name": "Updated In Use Type",
            "prompt": "Обновленный промпт для типа с данными",
            "description": "Тип с данными, описание обновлено",
        }, headers=auth_headers_system)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Updated In Use Type"
        assert updated["prompt"] == "Обновленный промпт для типа с данными"
        assert updated["type_id"] == type_id


class TestNamespaceEditabilityEdgeCases:
    """Граничные сценарии"""

    @pytest.mark.asyncio
    async def test_unknown_type_ids_rejected(self, crm_client, unique_id, auth_headers_system):
        """422 при передаче несуществующих type_id"""
        type_a = f"alpha_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a],
        )

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_a, "nonexistent_type_xyz"]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 422
        assert "nonexistent_type_xyz" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_editability_reflects_multiple_entity_types(self, crm_client, unique_id, auth_headers_system):
        """locked_type_ids содержит все типы с сущностями"""
        type_a = f"a_{unique_id}"
        type_b = f"b_{unique_id}"
        type_c = f"c_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b, type_c],
        )

        for tid in [type_a, type_c]:
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": tid,
                "name": f"Entity {tid}",
                "namespace": namespace_name,
            }, headers=auth_headers_system)

        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        editability = resp.json()
        assert type_a in editability["locked_type_ids"]
        assert type_c in editability["locked_type_ids"]
        assert type_b in editability["removable_type_ids"]
        assert type_b not in editability["locked_type_ids"]

    @pytest.mark.asyncio
    async def test_keep_locked_types_and_add_new(self, crm_client, unique_id, auth_headers_system):
        """Можно оставить все залоченные типы и добавить новый одним запросом"""
        type_locked = f"locked_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_locked],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_locked,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        type_added = f"new_{unique_id}"
        await crm_client.post("/crm/api/v1/entity-types", json={
            "type_id": type_added,
            "name": "Новый тип",
            "namespace_ids": ["default"],
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={"allowed_type_ids": [type_locked, type_added]},
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

        editability_resp = await crm_client.get(
            f"/crm/api/v1/namespaces/{namespace_name}/editability",
            headers=auth_headers_system,
        )
        editability = editability_resp.json()
        assert type_locked in editability["current_allowed_type_ids"]
        assert type_added in editability["current_allowed_type_ids"]

    @pytest.mark.asyncio
    async def test_nonexistent_namespace_editability_404(self, crm_client, unique_id, auth_headers_system):
        """404 для несуществующего namespace"""
        resp = await crm_client.get(
            f"/crm/api/v1/namespaces/nonexistent_{unique_id}/editability",
            headers=auth_headers_system,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_namespace_update_404(self, crm_client, unique_id, auth_headers_system):
        """404 при обновлении несуществующего namespace"""
        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/nonexistent_{unique_id}",
            json={"description": "test"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_description_and_types_in_single_request(self, crm_client, unique_id, auth_headers_system):
        """Можно менять и описание, и типы одним запросом"""
        type_a = f"alpha_{unique_id}"
        type_b = f"beta_{unique_id}"
        namespace_name, _ = await _create_namespace_with_types(
            crm_client, auth_headers_system, unique_id, [type_a, type_b],
        )

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": type_a,
            "name": f"Entity {unique_id}",
            "namespace": namespace_name,
        }, headers=auth_headers_system)

        resp = await crm_client.put(
            f"/crm/api/v1/namespaces/{namespace_name}",
            json={
                "description": "Комбинированное обновление",
                "allowed_type_ids": [type_a],
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Комбинированное обновление"

        types_resp = await crm_client.get(
            f"/crm/api/v1/entity-types/by-namespace/{namespace_name}",
            headers=auth_headers_system,
        )
        type_ids = [t["type_id"] for t in types_resp.json()]
        assert type_a in type_ids
        assert type_b not in type_ids
