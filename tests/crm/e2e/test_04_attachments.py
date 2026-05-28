"""
Тесты вложений к entities.

User Story: Прикрепление файлов разных форматов к заметкам через RAG сервис.
"""

import asyncio
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _document_id(response: Response) -> str:
    return object_str(_http_json(response).get("document_id"), field="document_id")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


def _attachment_ids(entity: dict[str, object]) -> list[str]:
    return _string_list(entity.get("attachment_ids"))


def _attachment_list(response: Response) -> list[dict[str, object]]:
    payload = cast(object, response.json())
    if not isinstance(payload, list):
        raise AssertionError("expected JSON array of attachments")
    return object_list(cast(list[object], payload))


class TestAttachments:
    """Работа с вложениями через AttachmentService"""

    @pytest.mark.asyncio
    async def test_upload_txt_file(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Загрузка текстового файла"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note с txt файлом {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        files = {"file": ("test.txt", b"Test content for CRM", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files,
            headers=auth_headers_system,
        )
        assert upload_resp.status_code == 200

        document_id = _document_id(upload_resp)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = _http_json(get_resp)
        assert document_id in _attachment_ids(entity)

    @pytest.mark.asyncio
    @pytest.mark.real_taskiq
    async def test_upload_multiple_formats(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Загрузка файлов разных форматов (PDF, DOCX, изображения)"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note с разными файлами {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        tag = unique_id.encode("utf-8")
        files_to_upload = [
            ("document.pdf", b"%PDF-1.4 fake pdf content " + tag, "application/pdf"),
            ("image.png", b"\x89PNG\r\n\x1a\n fake png " + tag, "image/png"),
            (
                "data.docx",
                b"PK fake docx content " + tag,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ]

        uploaded_ids: list[str] = []
        for filename, content, mime_type in files_to_upload:
            upload_files = {"file": (filename, content, mime_type)}
            response = await crm_client.post(
                f"/crm/api/v1/entities/{entity_id}/attachments",
                files=upload_files,
                headers=auth_headers_system,
            )
            assert response.status_code == 200
            uploaded_ids.append(_document_id(response))

            await asyncio.sleep(0.5)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = _http_json(get_resp)

        attachment_ids = _attachment_ids(entity)
        for doc_id in uploaded_ids:
            assert doc_id in attachment_ids

        assert len(attachment_ids) >= len(files_to_upload)

    @pytest.mark.asyncio
    async def test_list_attachments(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Получение списка вложений entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task с вложениями {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        for i in range(3):
            upload_files = {"file": (f"doc{i}.txt", f"Content {i}".encode(), "text/plain")}
            _ = await crm_client.post(
                f"/crm/api/v1/entities/{entity_id}/attachments",
                files=upload_files,
                headers=auth_headers_system,
            )

        list_resp = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200

        attachments = _attachment_list(list_resp)
        assert len(attachments) >= 3

        for attachment in attachments:
            assert "document_id" in attachment
            assert "filename" in attachment or "name" in attachment

    @pytest.mark.asyncio
    async def test_delete_attachment(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Удаление вложения"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note для удаления вложения {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        files = {"file": ("remove_me.txt", b"To be removed", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files,
            headers=auth_headers_system,
        )
        document_id = _document_id(upload_resp)

        delete_resp = await crm_client.delete(
            f"/crm/api/v1/entities/{entity_id}/attachments/{document_id}",
            headers=auth_headers_system,
        )
        assert delete_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = _http_json(get_resp)
        assert document_id not in _attachment_ids(entity)

    @pytest.mark.asyncio
    async def test_attachments_survive_entity_update(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Вложения сохраняются при обновлении entity"""
        entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        files = {"file": ("important.txt", b"Important data", "text/plain")}
        upload_resp = await crm_client.post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files=files,
            headers=auth_headers_system,
        )
        document_id = _document_id(upload_resp)

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity_id}", json={
            "name": f"Обновленная Note {unique_id}",
            "description": "Новое описание",
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        entity = _http_json(get_resp)
        assert document_id in _attachment_ids(entity)

    @pytest.mark.asyncio
    async def test_multiple_entities_same_attachment_type(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Разные entities могут иметь вложения"""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Note {unique_id}",
        }, headers=auth_headers_system)
        note_id = _entity_id(note_resp)

        task_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Task {unique_id}",
        }, headers=auth_headers_system)
        task_id = _entity_id(task_resp)

        files_note = {"file": ("note_file.txt", b"Note attachment", "text/plain")}
        note_upload = await crm_client.post(
            f"/crm/api/v1/entities/{note_id}/attachments",
            files=files_note,
            headers=auth_headers_system,
        )
        assert note_upload.status_code == 200

        files_task = {"file": ("task_file.txt", b"Task attachment", "text/plain")}
        task_upload = await crm_client.post(
            f"/crm/api/v1/entities/{task_id}/attachments",
            files=files_task,
            headers=auth_headers_system,
        )
        assert task_upload.status_code == 200

        note_get = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        task_get = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)

        assert len(_attachment_ids(_http_json(note_get))) >= 1
        assert len(_attachment_ids(_http_json(task_get))) >= 1
