"""
Тесты работы с файлами через A2A API.

Проверяет:
- FilePart извлекается в память, персистится в S3 на API (file_id + url в state)
- В content сообщения добавляются [FILE]...[/FILE] теги
"""

import base64
import uuid
from typing import Any, Dict

import pytest

from apps.flows.src.container import get_container
from core.files.file_ref import FileRef


def _msg_with_file(
    text: str,
    file_bytes: bytes,
    file_name: str = "test_file.txt",
    mime_type: str = "text/plain",
    context_id: str | None = None,
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
    context_id: str | None = None,
) -> Dict[str, Any]:
    """Создаёт A2A Message с текстом и изображением."""
    return _msg_with_file(
        text=text,
        file_bytes=image_bytes,
        file_name=file_name,
        mime_type="image/png",
        context_id=context_id,
    )


def _state_files(state: object) -> list[FileRef]:
    if not hasattr(state, "files"):
        raise TypeError("state must expose typed files")
    files = state.files
    if not isinstance(files, list):
        raise TypeError("state.files must be list")
    for item in files:
        if not isinstance(item, FileRef):
            raise TypeError("state.files[] must be FileRef")
    return files


class TestA2AFilesHandling:
    """Тесты обработки файлов в A2A сообщениях."""

    @pytest.fixture
    async def flow_id(self, client):
        """Использует стабильный flow для A2A e2e."""
        _ = client
        return "example_react"

    @pytest.mark.asyncio
    async def test_file_saved_and_in_state(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """
        Проверяет что файл из FilePart:
        1. Персистится (S3 + FileRecord), в state — file_id и url
        2. Запись в БД файлов находится по file_id
        """
        mock_llm_with_queue([{"type": "text", "content": "I received your file"}])

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

        workflow_runtime = get_container().workflow_runtime
        session_id = f"{flow_id}:{context_id}"
        state = await workflow_runtime.get_state(session_id)

        assert state is not None, "State should exist after message"
        files = _state_files(state)
        assert len(files) > 0, "State should have at least one file"

        file_info = files[0]
        assert file_info.original_name == "document.txt"
        assert file_info.content_type == "text/plain"
        assert file_info.file_size == len(test_content)
        assert file_info.file_id is not None
        assert file_info.url is not None
        assert "/api/v1/files/download/" in file_info.url
        stored = await get_container().file_processor.get_file_record(file_info.file_id)
        assert stored is not None
        assert stored.file_size == len(test_content)

    @pytest.mark.asyncio
    async def test_file_with_uri_reuses_existing_file_record(
        self,
        client,
        flow_id,
        mock_llm_with_queue,
        sync_tools,
        auth_headers_system,
    ):
        """FileWithUri из chat upload остаётся тем же FileRecord, без повторной записи bytes."""
        mock_llm_with_queue([{"type": "text", "content": "I received your linked file"}])

        upload = await client.post(
            "/flows/api/v1/files/",
            headers=auth_headers_system,
            files={"file": ("linked.csv", b"a,b\n1,2\n", "text/csv")},
            data={"public": "false"},
        )
        assert upload.status_code == 200, upload.text
        uploaded = upload.json()
        file_id = uploaded["file_id"]
        uri = uploaded["url"]
        context_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=auth_headers_system,
            json={
                "jsonrpc": "2.0",
                "id": "test-file-uri-1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "contextId": context_id,
                        "parts": [
                            {"kind": "text", "text": "Use this uploaded file"},
                            {
                                "kind": "file",
                                "file": {
                                    "uri": uri,
                                    "name": "ignored-client-name.csv",
                                    "mimeType": "text/csv",
                                },
                            },
                        ],
                    }
                },
            },
        )

        assert resp.status_code == 200
        state = await get_container().workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None
        files = _state_files(state)
        assert len(files) == 1
        file_info = files[0]
        assert file_info.file_id == file_id
        assert file_info.original_name == "linked.csv"
        assert file_info.url == uri
        assert file_info.content_type == "text/csv"
        assert file_info.file_size == len(b"a,b\n1,2\n")

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

        workflow_runtime = get_container().workflow_runtime
        session_id = f"{flow_id}:{context_id}"
        state = await workflow_runtime.get_state(session_id)

        assert state is not None
        content = state.get("content", "")

        assert "[FILE]" in content, f"Content should have [FILE] tag, got: {content}"
        assert "[/FILE]" in content, f"Content should have [/FILE] tag, got: {content}"
        assert "screenshot.png" in content, f"Content should have filename, got: {content}"
        assert "image/png" in content, f"Content should have content_type, got: {content}"
        assert "/api/v1/files/download/" in content

    @pytest.mark.asyncio
    async def test_multiple_files(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Проверяет обработку нескольких файлов в одном сообщении."""
        mock_llm_with_queue([{"type": "text", "content": "Multiple files received"}])

        context_id = str(uuid.uuid4())
        file1_content = b"First file content"
        file2_content = b"Second file content"

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

        workflow_runtime = get_container().workflow_runtime
        session_id = f"{flow_id}:{context_id}"
        state = await workflow_runtime.get_state(session_id)

        assert state is not None
        files = _state_files(state)
        assert len(files) == 2, f"Should have 2 files, got: {files}"

        file_names = [f.original_name for f in files]
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names
        for file_info in files:
            assert file_info.file_id is not None, "Each persisted file should have file_id"

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

        workflow_runtime = get_container().workflow_runtime
        session_id = f"{flow_id}:{context_id}"
        state = await workflow_runtime.get_state(session_id)

        assert state is not None
        assert _state_files(state) == [], "Files should be empty list"
        assert "[FILE]" not in state.get("content", "")


class TestIncomingA2aFilesUnit:
    """Unit-тесты извлечения и форматирования A2A-вложений без диска."""

    def test_extract_incoming_bytes_in_memory(self):
        """FileWithBytes декодируется в память, без записи файла."""
        from a2a.types import FilePart, FileWithBytes, Message, Part, Role, TextPart

        from apps.flows.src.files.handler import extract_incoming_a2a_files

        file_content = b"Test binary content"
        message = Message(
            message_id=str(uuid.uuid4()),
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

        incoming = extract_incoming_a2a_files(message)

        assert len(incoming) == 1
        one = incoming[0]
        assert one.original_name == "test.bin"
        assert one.content_type == "application/octet-stream"
        assert one.file_size == len(file_content)
        assert one.data == file_content
        assert one.uri is None

    def test_format_a2a_files_content(self):
        """Форматирование записей state.files в текст для агента."""
        from apps.flows.src.files.handler import format_a2a_files_content

        files_data = [
            FileRef(
                original_name="doc.pdf",
                url="/flows/api/v1/files/download/file_abc",
                content_type="application/pdf",
                file_size=1024,
                file_id="file_abc",
            ),
            FileRef(
                original_name="ref.png",
                url="https://cdn.example.com/ref.png",
                content_type="image/png",
                file_size=0,
            ),
        ]

        formatted = format_a2a_files_content(files_data)

        assert "[FILE]" in formatted
        assert "[/FILE]" in formatted
        assert "doc.pdf" in formatted
        assert "ref.png" in formatted
        assert "/flows/api/v1/files/download/file_abc" in formatted
        assert "https://cdn.example.com/ref.png" in formatted
        assert "application/pdf" in formatted
        assert "image/png" in formatted
