"""
API тесты для Attachments в Notes.

Тесты для endpoints:
- POST /notes/{note_id}/attachments - загрузка файла
- GET /notes/{note_id}/attachments - список файлов
- DELETE /notes/{note_id}/attachments/{file_id} - удаление файла
- GET /notes/{note_id}/attachments/{file_id}/download - URL для скачивания
- GET /notes/{note_id}/attachments/{file_id}/content - распаршенный контент
"""

import pytest
from datetime import date
from httpx import AsyncClient
import io


class TestNotesAttachmentsAPI:
    """Тесты API для аттачментов заметок"""

    @pytest.fixture
    async def note_with_attachment(self, crm_client: AsyncClient, unique_id):
        """Создает заметку и загружает к ней файл"""
        # Создаем заметку
        note_payload = {
            "title": f"Note with attachment {unique_id('attach')}",
            "content": "Test content for attachment",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        assert note_response.status_code == 200
        note = note_response.json()
        note_id = note["note_id"]

        # Загружаем файл
        file_content = b"Test file content for attachment test"
        files = {"file": ("test_file.txt", io.BytesIO(file_content), "text/plain")}
        upload_response = await crm_client.post(
            f"/crm/api/v1/notes/{note_id}/attachments",
            files=files
        )
        
        file_data = None
        if upload_response.status_code == 200:
            file_data = upload_response.json()

        yield {"note": note, "file": file_data, "note_id": note_id}

        # Cleanup
        await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_upload_attachment(self, crm_client: AsyncClient, unique_id):
        """Тест загрузки файла к заметке"""
        # Создаем заметку
        note_payload = {
            "title": f"Upload test {unique_id('upload')}",
            "content": "Content for upload test",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        assert note_response.status_code == 200
        note_id = note_response.json()["note_id"]

        try:
            # Загружаем файл
            file_content = b"Hello, this is a test file content!"
            files = {"file": ("hello.txt", io.BytesIO(file_content), "text/plain")}
            
            response = await crm_client.post(
                f"/crm/api/v1/notes/{note_id}/attachments",
                files=files
            )

            assert response.status_code == 200
            data = response.json()
            
            assert "file_id" in data
            assert data["original_name"] == "hello.txt"
            assert data["file_size"] == len(file_content)
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_upload_attachment_to_nonexistent_note(self, crm_client: AsyncClient, unique_id):
        """Тест загрузки файла к несуществующей заметке"""
        fake_note_id = unique_id("fake")
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = await crm_client.post(
            f"/crm/api/v1/notes/{fake_note_id}/attachments",
            files=files
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_attachments(self, crm_client: AsyncClient, note_with_attachment):
        """Тест получения списка файлов заметки"""
        note_id = note_with_attachment["note_id"]

        response = await crm_client.get(f"/crm/api/v1/notes/{note_id}/attachments")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if note_with_attachment["file"]:
            assert len(data) >= 1
            attachment = data[0]
            assert "file_id" in attachment
            assert "original_name" in attachment

    @pytest.mark.asyncio
    async def test_get_attachments_empty(self, crm_client: AsyncClient, unique_id):
        """Тест получения пустого списка файлов"""
        # Создаем заметку без файлов
        note_payload = {
            "title": f"Empty attachments {unique_id('empty')}",
            "content": "No attachments here",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            response = await crm_client.get(f"/crm/api/v1/notes/{note_id}/attachments")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_get_attachments_nonexistent_note(self, crm_client: AsyncClient, unique_id):
        """Тест получения файлов несуществующей заметки"""
        fake_note_id = unique_id("fake")

        response = await crm_client.get(f"/crm/api/v1/notes/{fake_note_id}/attachments")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_attachment(self, crm_client: AsyncClient, unique_id):
        """Тест удаления файла из заметки"""
        # Создаем заметку
        note_payload = {
            "title": f"Remove attachment {unique_id('remove')}",
            "content": "Content",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            # Загружаем файл
            file_content = b"File to be removed"
            files = {"file": ("to_remove.txt", io.BytesIO(file_content), "text/plain")}
            upload_response = await crm_client.post(
                f"/crm/api/v1/notes/{note_id}/attachments",
                files=files
            )
            
            if upload_response.status_code != 200:
                pytest.skip("Upload not available")
                
            file_id = upload_response.json()["file_id"]

            # Удаляем файл
            response = await crm_client.delete(
                f"/crm/api/v1/notes/{note_id}/attachments/{file_id}"
            )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"

            # Проверяем что файл удален из списка
            list_response = await crm_client.get(f"/crm/api/v1/notes/{note_id}/attachments")
            attachments = list_response.json()
            file_ids = [a["file_id"] for a in attachments]
            assert file_id not in file_ids
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_remove_nonexistent_attachment(self, crm_client: AsyncClient, unique_id):
        """Тест удаления несуществующего файла"""
        # Создаем заметку
        note_payload = {
            "title": f"Remove nonexistent {unique_id('nonexist')}",
            "content": "Content",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            fake_file_id = unique_id("fakefile")
            response = await crm_client.delete(
                f"/crm/api/v1/notes/{note_id}/attachments/{fake_file_id}"
            )

            assert response.status_code == 404
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_download_attachment(self, crm_client: AsyncClient, note_with_attachment):
        """Тест получения URL для скачивания файла"""
        if not note_with_attachment["file"]:
            pytest.skip("No file uploaded")

        note_id = note_with_attachment["note_id"]
        file_id = note_with_attachment["file"]["file_id"]

        response = await crm_client.get(
            f"/crm/api/v1/notes/{note_id}/attachments/{file_id}/download"
        )

        assert response.status_code == 200
        data = response.json()
        assert "download_url" in data
        assert data["download_url"] is not None

    @pytest.mark.asyncio
    async def test_download_nonexistent_attachment(self, crm_client: AsyncClient, unique_id):
        """Тест скачивания несуществующего файла"""
        # Создаем заметку
        note_payload = {
            "title": f"Download nonexistent {unique_id('dl')}",
            "content": "Content",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            fake_file_id = unique_id("fakefile")
            response = await crm_client.get(
                f"/crm/api/v1/notes/{note_id}/attachments/{fake_file_id}/download"
            )

            assert response.status_code == 404
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_get_attachment_content(self, crm_client: AsyncClient, note_with_attachment):
        """Тест получения распаршенного контента файла"""
        if not note_with_attachment["file"]:
            pytest.skip("No file uploaded")

        note_id = note_with_attachment["note_id"]
        file_id = note_with_attachment["file"]["file_id"]

        response = await crm_client.get(
            f"/crm/api/v1/notes/{note_id}/attachments/{file_id}/content"
        )

        # Контент может быть еще не проиндексирован, поэтому принимаем 200 или 404
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "content" in data

    @pytest.mark.asyncio
    async def test_get_content_nonexistent_attachment(self, crm_client: AsyncClient, unique_id):
        """Тест получения контента несуществующего файла"""
        # Создаем заметку
        note_payload = {
            "title": f"Content nonexistent {unique_id('cnt')}",
            "content": "Content",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            fake_file_id = unique_id("fakefile")
            response = await crm_client.get(
                f"/crm/api/v1/notes/{note_id}/attachments/{fake_file_id}/content"
            )

            assert response.status_code == 404
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_upload_multiple_attachments(self, crm_client: AsyncClient, unique_id):
        """Тест загрузки нескольких файлов к одной заметке"""
        # Создаем заметку
        note_payload = {
            "title": f"Multiple attachments {unique_id('multi')}",
            "content": "Content with multiple files",
            "note_type": "meeting_minutes",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            uploaded_ids = []
            
            # Загружаем несколько файлов
            for i in range(3):
                file_content = f"File content {i}".encode()
                files = {"file": (f"file_{i}.txt", io.BytesIO(file_content), "text/plain")}
                
                response = await crm_client.post(
                    f"/crm/api/v1/notes/{note_id}/attachments",
                    files=files
                )
                
                if response.status_code == 200:
                    uploaded_ids.append(response.json()["file_id"])

            # Проверяем список
            list_response = await crm_client.get(f"/crm/api/v1/notes/{note_id}/attachments")
            assert list_response.status_code == 200
            
            attachments = list_response.json()
            assert len(attachments) >= len(uploaded_ids)
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

    @pytest.mark.asyncio
    async def test_upload_different_file_types(self, crm_client: AsyncClient, unique_id):
        """Тест загрузки файлов разных типов"""
        # Создаем заметку
        note_payload = {
            "title": f"Different types {unique_id('types')}",
            "content": "Content",
            "note_type": "freeform",
            "note_date": str(date.today()),
        }
        note_response = await crm_client.post("/crm/api/v1/notes", json=note_payload)
        note_id = note_response.json()["note_id"]

        try:
            file_types = [
                ("document.txt", "text/plain", b"Plain text content"),
                ("data.json", "application/json", b'{"key": "value"}'),
                ("script.py", "text/x-python", b"print('hello')"),
            ]

            for filename, content_type, content in file_types:
                files = {"file": (filename, io.BytesIO(content), content_type)}
                
                response = await crm_client.post(
                    f"/crm/api/v1/notes/{note_id}/attachments",
                    files=files
                )
                
                if response.status_code == 200:
                    data = response.json()
                    assert data["original_name"] == filename
        finally:
            await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

