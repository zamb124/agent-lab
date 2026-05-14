"""
Тесты вложений к entities.

User Story: Прикрепление файлов разных форматов к заметкам через RAG сервис.
"""

import asyncio

import pytest


class TestAttachments:
    """Работа с вложениями через AttachmentService"""

    @pytest.mark.asyncio
    async def test_upload_txt_file(self, crm_client, unique_id, auth_headers_system):
        """Загрузка текстового файла"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note с txt файлом {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]

        files = {"file": ("test.txt", b"Test content for CRM", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files
        , headers=auth_headers_system)
        assert upload_resp.status_code == 200

        result = upload_resp.json()
        assert "document_id" in result
        document_id = result["document_id"]

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = get_resp.json()
        assert document_id in entity["attachment_ids"]

    @pytest.mark.asyncio
    @pytest.mark.real_taskiq
    async def test_upload_multiple_formats(self, crm_client, unique_id, auth_headers_system):
        """Загрузка файлов разных форматов (PDF, DOCX, изображения)"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note с разными файлами {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]

        tag = unique_id.encode("utf-8")
        files_to_upload = [
            ("document.pdf", b"%PDF-1.4 fake pdf content " + tag, "application/pdf"),
            ("image.png", b"\x89PNG\r\n\x1a\n fake png " + tag, "image/png"),
            ("data.docx", b"PK fake docx content " + tag, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ]

        uploaded_ids = []
        for filename, content, mime_type in files_to_upload:
            files = {"file": (filename, content, mime_type)}
            response = await crm_client.post(
                f"/crm/api/v1/entities/{entity_id}/attachments",
                files=files
            , headers=auth_headers_system)
            assert response.status_code == 200
            uploaded_ids.append(response.json()["document_id"])

            await asyncio.sleep(0.5)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = get_resp.json()

        for doc_id in uploaded_ids:
            assert doc_id in entity["attachment_ids"]

        assert len(entity["attachment_ids"]) >= len(files_to_upload)

    @pytest.mark.asyncio
    async def test_list_attachments(self, crm_client, unique_id, auth_headers_system):
        """Получение списка вложений entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task с вложениями {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]

        for i in range(3):
            files = {"file": (f"doc{i}.txt", f"Content {i}".encode(), "text/plain")}
            await crm_client.post(f"/crm/api/v1/entities/{entity_id}/attachments", files=files, headers=auth_headers_system)

        list_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}/attachments", headers=auth_headers_system)
        assert list_resp.status_code == 200

        attachments = list_resp.json()
        assert len(attachments) >= 3

        for attachment in attachments:
            assert "document_id" in attachment
            assert "filename" in attachment or "name" in attachment

    @pytest.mark.asyncio
    async def test_delete_attachment(self, crm_client, unique_id, auth_headers_system):
        """Удаление вложения"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note для удаления вложения {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]

        files = {"file": ("remove_me.txt", b"To be removed", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files
        , headers=auth_headers_system)
        document_id = upload_resp.json()["document_id"]

        delete_resp = await crm_client.delete(
            f"/crm/api/v1/entities/{entity_id}/attachments/{document_id}"
        , headers=auth_headers_system)
        assert delete_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = get_resp.json()
        assert document_id not in entity["attachment_ids"]

    @pytest.mark.asyncio
    async def test_attachments_survive_entity_update(self, crm_client, unique_id, auth_headers_system):
        """Вложения сохраняются при обновлении entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        entity_id = entity_resp.json()["entity_id"]

        files = {"file": ("important.txt", b"Important data", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files
        , headers=auth_headers_system)
        document_id = upload_resp.json()["document_id"]

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity_id}", json={
            "name": f"Обновленная Note {unique_id}",
            "description": "Новое описание"
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = get_resp.json()
        assert document_id in entity["attachment_ids"]

    @pytest.mark.asyncio
    async def test_multiple_entities_same_attachment_type(self, crm_client, unique_id, auth_headers_system):
        """Разные entities могут иметь вложения"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}"
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        task_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task {unique_id}"
        }, headers=auth_headers_system)
        task_id = task_resp.json()["entity_id"]

        files_note = {"file": ("note_file.txt", b"Note attachment", "text/plain")}
        note_upload = await crm_client.post(f"/crm/api/v1/entities/{note_id}/attachments", files=files_note, headers=auth_headers_system)
        assert note_upload.status_code == 200

        files_task = {"file": ("task_file.txt", b"Task attachment", "text/plain")}
        task_upload = await crm_client.post(f"/crm/api/v1/entities/{task_id}/attachments", files=files_task, headers=auth_headers_system)
        assert task_upload.status_code == 200

        note_get = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        task_get = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)

        assert len(note_get.json()["attachment_ids"]) >= 1
        assert len(task_get.json()["attachment_ids"]) >= 1

