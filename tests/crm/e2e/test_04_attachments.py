"""
Тесты вложений к entities.

User Story: Прикрепление файлов разных форматов к заметкам через RAG сервис.
"""

import asyncio
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str
from tests.crm.e2e.attachment_upload_helpers import upload_and_attach_crm_file


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
    payload = json_object(cast(object, response.json()))
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError("expected ListResponse.items array of attachments")
    return object_list(cast(list[object], items))


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
        note_name = f"Note с txt файлом {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        upload_resp = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=entity_id,
            entity_type="note",
            entity_title=note_name,
            filename="test.txt",
            content=b"Test content for CRM",
            content_type="text/plain",
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
        note_name = f"Note с разными файлами {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
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
            response = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=entity_id,
                entity_type="note",
                entity_title=note_name,
                filename=filename,
                content=content,
                content_type=mime_type,
            )
            assert response.status_code == 200, response.text
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
        task_name = f"Task с вложениями {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": task_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        for i in range(3):
            _ = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=entity_id,
                entity_type="task",
                entity_title=task_name,
                filename=f"doc{i}.txt",
                content=f"Content {i}".encode(),
                content_type="text/plain",
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
        note_name = f"Note для удаления вложения {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        upload_resp = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=entity_id,
            entity_type="note",
            entity_title=note_name,
            filename="remove_me.txt",
            content=b"To be removed",
            content_type="text/plain",
        )
        document_id = _document_id(upload_resp)

        delete_resp = await crm_client.delete(
            f"/crm/api/v1/entities/{entity_id}/attachments/{document_id}",
            headers=auth_headers_system,
        )
        assert delete_resp.status_code == 204

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
        note_name = f"Note {unique_id}"
        entity_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        entity_id = _entity_id(entity_resp)

        upload_resp = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=entity_id,
            entity_type="note",
            entity_title=note_name,
            filename="important.txt",
            content=b"Important data",
            content_type="text/plain",
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
        note_name = f"Note {unique_id}"
        note_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "note",
            "name": note_name,
        }, headers=auth_headers_system)
        note_id = _entity_id(note_resp)

        task_name = f"Task {unique_id}"
        task_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": task_name,
        }, headers=auth_headers_system)
        task_id = _entity_id(task_resp)

        note_upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="note_file.txt",
            content=b"Note attachment",
            content_type="text/plain",
        )
        assert note_upload.status_code == 200

        task_upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=task_id,
            entity_type="task",
            entity_title=task_name,
            filename="task_file.txt",
            content=b"Task attachment",
            content_type="text/plain",
        )
        assert task_upload.status_code == 200

        note_get = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        task_get = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)

        assert len(_attachment_ids(_http_json(note_get))) >= 1
        assert len(_attachment_ids(_http_json(task_get))) >= 1
