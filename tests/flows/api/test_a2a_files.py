"""
Тесты работы с файлами через A2A API.

Проверяет:
- FilePart извлекается из Message и сохраняется в tmp
- Информация о файлах добавляется в state["files"]
- В content сообщения добавляются [FILE]...[/FILE] теги
"""

import base64
import os
import uuid
from typing import Any, Dict

import pytest

from apps.flows.src.container import get_container


def _msg_with_file(
    text: str,
    file_bytes: bytes,
    file_name: str = "test_file.txt",
    mime_type: str = "text/plain",
    context_id: str = None,
) -> Dict[str, Any]:
    """Создаёт A2A Message с текстом и файлом."""
    context_id = context_id or str(uuid.uuid4())
    return {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "contextId": context_id,
        "parts": [
            {"kind": "text", "text": text},
            {
                "kind": "file",
                "file": {
                    "bytes": base64.b64encode(file_bytes).decode("utf-8"),
                    "name": file_name,
                    "mimeType": mime_type,
                },
            },
        ],
    }


def _msg_with_image(
    text: str,
    image_bytes: bytes,
    file_name: str = "image.png",
    context_id: str = None,
) -> Dict[str, Any]:
    """Создаёт A2A Message с текстом и изображением."""
    return _msg_with_file(
        text=text,
        file_bytes=image_bytes,
        file_name=file_name,
        mime_type="image/png",
        context_id=context_id,
    )


class TestA2AFilesHandling:
    """Тесты обработки файлов в A2A сообщениях."""

    @pytest.fixture
    async def flow_id(self, client):
        """Получает ID первого доступного flow."""
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        if not agents:
            pytest.skip("No flows available")
        return agents[0]["url"].split("/flows/")[-1]

    @pytest.mark.asyncio
    async def test_file_saved_and_in_state(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """
        Проверяет что файл из FilePart:
        1. Сохраняется в tmp директорию
        2. Информация добавляется в state["files"]
        """
        mock_llm_with_queue([{"type": "text", "content": "I received your file"}])

        # Создаём тестовый файл
        test_content = b"Test file content for A2A"
        context_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-file-1",
                "method": "message/send",
                "params": {
                    "message": _msg_with_file(
                        text="Process this file",
                        file_bytes=test_content,
                        file_name="document.txt",
                        mime_type="text/plain",
                        context_id=context_id,
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data, f"Expected result, got: {data}"

        # Проверяем state
        state_manager = get_container().state_manager
        session_id = f"{flow_id}:{context_id}"
        state = await state_manager.get_state(session_id)

        assert state is not None, "State should exist after message"
        assert "files" in state, "State should have files"
        assert len(state["files"]) > 0, "State should have at least one file"

        # Проверяем структуру файла
        file_info = state["files"][0]
        assert "name" in file_info, "File info should have name"
        assert "path" in file_info, "File info should have path"
        assert "mime_type" in file_info, "File info should have mime_type"
        assert "size" in file_info, "File info should have size"

        assert file_info["name"] == "document.txt"
        assert file_info["mime_type"] == "text/plain"
        assert file_info["size"] == len(test_content)

        # Проверяем что файл реально существует
        assert os.path.exists(file_info["path"]), f"File should exist at {file_info['path']}"

        # Проверяем содержимое файла
        with open(file_info["path"], "rb") as f:
            saved_content = f.read()
        assert saved_content == test_content, "File content should match"

    @pytest.mark.asyncio
    async def test_file_info_in_content(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """
        Проверяет что информация о файле добавляется в content сообщения.
        Агент должен видеть [FILE]...[/FILE] теги.
        """
        mock_llm_with_queue([{"type": "text", "content": "File received"}])

        test_content = b"Image data here"
        context_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-file-2",
                "method": "message/send",
                "params": {
                    "message": _msg_with_image(
                        text="Analyze this image",
                        image_bytes=test_content,
                        file_name="screenshot.png",
                        context_id=context_id,
                    )
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data, f"Expected result, got: {data}"

        # Проверяем state - content должен содержать [FILE] тег
        state_manager = get_container().state_manager
        session_id = f"{flow_id}:{context_id}"
        state = await state_manager.get_state(session_id)

        assert state is not None
        content = state.get("content", "")

        # Проверяем наличие [FILE] тега
        assert "[FILE]" in content, f"Content should have [FILE] tag, got: {content}"
        assert "[/FILE]" in content, f"Content should have [/FILE] tag, got: {content}"
        assert "screenshot.png" in content, f"Content should have filename, got: {content}"
        assert "image/png" in content, f"Content should have mime_type, got: {content}"

    @pytest.mark.asyncio
    async def test_multiple_files(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Проверяет обработку нескольких файлов в одном сообщении."""
        mock_llm_with_queue([{"type": "text", "content": "Multiple files received"}])

        context_id = str(uuid.uuid4())
        file1_content = b"First file content"
        file2_content = b"Second file content"

        # Создаём сообщение с двумя файлами
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "contextId": context_id,
            "parts": [
                {"kind": "text", "text": "Process these files"},
                {
                    "kind": "file",
                    "file": {
                        "bytes": base64.b64encode(file1_content).decode("utf-8"),
                        "name": "file1.txt",
                        "mimeType": "text/plain",
                    },
                },
                {
                    "kind": "file",
                    "file": {
                        "bytes": base64.b64encode(file2_content).decode("utf-8"),
                        "name": "file2.txt",
                        "mimeType": "text/plain",
                    },
                },
            ],
        }

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-file-3",
                "method": "message/send",
                "params": {"message": message},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        # Проверяем state
        state_manager = get_container().state_manager
        session_id = f"{flow_id}:{context_id}"
        state = await state_manager.get_state(session_id)

        assert state is not None
        assert len(state["files"]) == 2, f"Should have 2 files, got: {state['files']}"

        # Проверяем что оба файла сохранены
        file_names = [f["name"] for f in state["files"]]
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names

        # Проверяем content
        content = state.get("content", "")
        assert content.count("[FILE]") == 2, "Content should have 2 [FILE] tags"

    @pytest.mark.asyncio
    async def test_message_without_files(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Проверяет что сообщение без файлов работает как раньше."""
        mock_llm_with_queue([{"type": "text", "content": "Simple response"}])

        context_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-no-file",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "contextId": context_id,
                        "parts": [{"kind": "text", "text": "Hello without files"}],
                    }
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data

        # Проверяем state
        state_manager = get_container().state_manager
        session_id = f"{flow_id}:{context_id}"
        state = await state_manager.get_state(session_id)

        assert state is not None
        # files должен быть пустым списком
        assert state.get("files", []) == [], "Files should be empty list"
        # Content не должен содержать [FILE] тегов
        assert "[FILE]" not in state.get("content", "")


class TestFileHandlerUnit:
    """Unit тесты для FileHandler."""

    def test_extract_and_save_bytes(self, tmp_path):
        """Проверяет извлечение и сохранение файла из FileWithBytes."""
        from a2a.types import FileWithBytes, FilePart, Message, Part, Role, TextPart

        from apps.flows.src.files import FileHandler

        handler = FileHandler(temp_dir=tmp_path)

        # Создаём тестовое сообщение с файлом
        file_content = b"Test binary content"
        message = Message(
            messageId=str(uuid.uuid4()),
            role=Role.user,
            parts=[
                Part(root=TextPart(text="Hello")),
                Part(
                    root=FilePart(
                        file=FileWithBytes(
                            bytes=base64.b64encode(file_content).decode("utf-8"),
                            name="test.bin",
                            mime_type="application/octet-stream",
                        )
                    )
                ),
            ],
        )

        files = handler.extract_and_save(message)

        assert len(files) == 1
        file_info = files[0]

        assert file_info.name == "test.bin"
        assert file_info.mime_type == "application/octet-stream"
        assert file_info.size == len(file_content)
        assert os.path.exists(file_info.path)

        with open(file_info.path, "rb") as f:
            assert f.read() == file_content

    def test_format_files_for_content(self):
        """Проверяет форматирование файлов для content."""
        from apps.flows.src.files.handler import FileHandler, FileInfo

        files = [
            FileInfo(
                name="doc.pdf",
                path="/tmp/abc123_doc.pdf",
                mime_type="application/pdf",
                size=1024,
            ),
            FileInfo(
                name="image.jpg",
                path="/tmp/def456_image.jpg",
                mime_type="image/jpeg",
                size=2048,
            ),
        ]

        formatted = FileHandler.format_files_for_content(files)

        assert "[FILE]" in formatted
        assert "[/FILE]" in formatted
        assert "doc.pdf" in formatted
        assert "image.jpg" in formatted
        assert "/tmp/abc123_doc.pdf" in formatted
        assert "application/pdf" in formatted
        assert "image/jpeg" in formatted

    def test_files_to_state(self):
        """Проверяет конвертацию FileInfo в формат для state."""
        from apps.flows.src.files.handler import FileHandler, FileInfo

        files = [
            FileInfo(
                name="test.txt",
                path="/tmp/test.txt",
                mime_type="text/plain",
                size=100,
            )
        ]

        state_files = FileHandler.files_to_state(files)

        assert len(state_files) == 1
        assert state_files[0]["name"] == "test.txt"
        assert state_files[0]["path"] == "/tmp/test.txt"
        assert state_files[0]["mime_type"] == "text/plain"
        assert state_files[0]["size"] == 100

