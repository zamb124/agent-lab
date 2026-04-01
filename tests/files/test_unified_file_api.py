"""
Интеграционные тесты единого файлового API платформы.

Проверяет что все три эндпоинта (upload/download/metadata) работают
одинаково во всех сервисах, FileRecord создаётся в shared DB,
avatar_url валидируется, кросс-сервисное скачивание работает.

Требует: MinIO запущен (docker-compose-dev.yaml), S3 настроен.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

# Тестовое изображение из репозитория
_TEST_IMAGE_PATH = Path(__file__).parent.parent / "2026-01-11 11.43.21.jpg"


def _skip_if_s3_disabled() -> None:
    """Пропускает тест если S3 не настроен или недоступен."""
    from core.files.s3_client import S3ClientFactory
    try:
        S3ClientFactory.create_default_client()
    except ValueError as e:
        pytest.skip(f"S3 не настроен: {e}")
    except Exception as e:
        pytest.skip(f"S3 недоступен: {e}")


# ==============================================================================
# Sync — загрузка и скачивание
# ==============================================================================

@pytest.mark.asyncio
async def test_sync_upload_returns_file_response(sync_client, auth_headers_system):
    """POST /sync/api/v1/files/ возвращает FileResponse с платформенным URL."""
    _skip_if_s3_disabled()

    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("readme.txt", io.BytesIO(b"hello platform"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert "file_id" in data
    assert data["original_name"] == "readme.txt"
    assert data["content_type"] == "text/plain"
    assert data["file_size"] == 14
    assert data["is_public"] is True
    assert data["url"].startswith("/sync/api/v1/files/download/")
    assert data["checksum"] is not None


@pytest.mark.asyncio
async def test_sync_upload_real_jpeg_image(sync_client, auth_headers_system):
    """Загрузка реального JPEG — content_type определяется по имени файла."""
    _skip_if_s3_disabled()
    if not _TEST_IMAGE_PATH.exists():
        pytest.skip("Тестовое изображение не найдено")

    image_data = _TEST_IMAGE_PATH.read_bytes()
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": (_TEST_IMAGE_PATH.name, io.BytesIO(image_data), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["content_type"] == "image/jpeg"
    assert data["file_size"] == len(image_data)
    assert data["url"].startswith("/sync/api/v1/files/download/")


@pytest.mark.asyncio
async def test_sync_download_returns_original_content(sync_client, auth_headers_system):
    """Загрузка файла, затем скачивание — содержимое совпадает."""
    _skip_if_s3_disabled()

    content = b"round-trip content check"
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("data.bin", io.BytesIO(content), "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    dl = await sync_client.get(
        f"/sync/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == content
    assert dl.headers["content-type"] == "application/octet-stream"
    assert dl.headers.get("accept-ranges", "").lower() == "bytes"
    assert dl.headers.get("content-length") == str(len(content))


@pytest.mark.asyncio
async def test_sync_download_partial_content_range(sync_client, auth_headers_system):
    """GET с Range — 206, фрагмент и Content-Range (нужно Safari/iOS для <audio>)."""
    _skip_if_s3_disabled()

    content = b"abcdefgh"
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("slice.bin", io.BytesIO(content), "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    headers = {**auth_headers_system, "Range": "bytes=2-4"}
    dl = await sync_client.get(
        f"/sync/api/v1/files/download/{file_id}",
        headers=headers,
    )
    assert dl.status_code == 206, dl.text
    assert dl.content == b"cde"
    assert dl.headers.get("accept-ranges", "").lower() == "bytes"
    cr = dl.headers.get("content-range", "")
    assert cr == "bytes 2-4/8"
    assert dl.headers.get("content-length") == "3"


@pytest.mark.asyncio
async def test_sync_download_image_round_trip(sync_client, auth_headers_system):
    """Загрузка и скачивание реального JPEG — байты идентичны."""
    _skip_if_s3_disabled()
    if not _TEST_IMAGE_PATH.exists():
        pytest.skip("Тестовое изображение не найдено")

    image_data = _TEST_IMAGE_PATH.read_bytes()
    upload = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": (_TEST_IMAGE_PATH.name, io.BytesIO(image_data), "image/jpeg")},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    download = await sync_client.get(
        f"/sync/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert download.status_code == 200
    assert download.content == image_data
    assert "image/jpeg" in download.headers["content-type"]


@pytest.mark.asyncio
async def test_sync_metadata_endpoint(sync_client, auth_headers_system):
    """GET /sync/api/v1/files/{file_id} возвращает FileResponse без скачивания."""
    _skip_if_s3_disabled()

    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("meta.txt", io.BytesIO(b"meta check"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    uploaded = r.json()
    file_id = uploaded["file_id"]

    meta = await sync_client.get(
        f"/sync/api/v1/files/{file_id}",
        headers=auth_headers_system,
    )
    assert meta.status_code == 200, meta.text
    data = meta.json()

    assert data["file_id"] == file_id
    assert data["original_name"] == "meta.txt"
    assert data["content_type"] == "text/plain"
    assert data["url"] == uploaded["url"]


@pytest.mark.asyncio
async def test_sync_upload_creates_file_record_in_shared_db(
    sync_client, auth_headers_system, mock_context
):
    """FileRecord создаётся в shared DB — доступен через container.file_repository."""
    _skip_if_s3_disabled()

    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("check.txt", io.BytesIO(b"db record"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    from core.context import set_context, clear_context
    from apps.sync.container import get_sync_container
    set_context(mock_context)
    try:
        container = get_sync_container()
        record = await container.file_repository.get(file_id)
    finally:
        clear_context()

    assert record is not None
    assert record.file_id == file_id
    assert record.original_name == "check.txt"
    assert record.is_public is True
    assert record.download_url is not None
    assert record.download_url.startswith("/sync/api/v1/files/download/")


@pytest.mark.asyncio
async def test_sync_download_404_for_unknown_file(sync_client, auth_headers_system):
    """Скачивание несуществующего файла → 404."""
    _skip_if_s3_disabled()
    r = await sync_client.get(
        "/sync/api/v1/files/download/nonexistent_file_id_xyz",
        headers=auth_headers_system,
    )
    assert r.status_code == 404


# ==============================================================================
# Cross-service — файл загруженный в sync скачивается через agents
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_service_download_via_agents(
    sync_client, flows_client, auth_headers_system
):
    """
    Файл, загруженный в sync, доступен для скачивания через agents.
    Оба сервиса читают из одного shared DB (FileRecord).
    """
    _skip_if_s3_disabled()

    content = b"cross-service payload"
    upload = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("cross.bin", io.BytesIO(content), "application/octet-stream")},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    dl = await flows_client.get(
        f"/flows/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == content


# ==============================================================================
# avatar_url валидация
# ==============================================================================

def test_avatar_url_pydantic_rejects_external_url():
    """SpaceUpdate и ChannelUpdate отвергают прямые S3 URL на уровне Pydantic."""
    from pydantic import ValidationError
    from apps.sync.models.spaces import SpaceUpdate
    from apps.sync.models.channels import ChannelUpdate

    for Model in (SpaceUpdate, ChannelUpdate):
        with pytest.raises(ValidationError) as exc_info:
            Model(avatar_url="http://127.0.0.1:19001/test-bucket/files/img.jpg")
        assert "относительным URL" in str(exc_info.value)

        with pytest.raises(ValidationError):
            Model(avatar_url="https://external.cdn.com/img.jpg")


def test_avatar_url_pydantic_accepts_relative_url():
    """SpaceUpdate и ChannelUpdate принимают относительные platform URL."""
    from apps.sync.models.spaces import SpaceUpdate
    from apps.sync.models.channels import ChannelUpdate

    for Model in (SpaceUpdate, ChannelUpdate):
        m = Model(avatar_url="/sync/api/v1/files/download/file_abc123")
        assert m.avatar_url == "/sync/api/v1/files/download/file_abc123"

        m_none = Model(avatar_url=None)
        assert m_none.avatar_url is None


# ==============================================================================
# RAG — документ загружается через FileProcessor
# ==============================================================================

@pytest.mark.asyncio
async def test_rag_upload_includes_file_response(rag_client, auth_headers_system):
    """POST /rag/api/v1/namespaces/{id}/documents возвращает file: FileResponse."""
    _skip_if_s3_disabled()

    ns = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": f"test-ns-unified"},
        headers=auth_headers_system,
    )
    if ns.status_code not in (200, 201):
        pytest.skip(f"Создание namespace недоступно: {ns.status_code}")
    namespace_id = ns.json()["name"]

    content = b"Document content for unified file test."
    r = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
        files={"file": ("doc.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 202, r.text
    data = r.json()

    assert "document_id" in data
    assert "task_id" in data
    assert data["status"] == "pending"

    assert "file" in data, "DocumentUploadResponse должен содержать file: FileResponse"
    file_info = data["file"]
    assert "file_id" in file_info
    assert file_info["file_id"] == data["document_id"]
    assert file_info["url"].startswith("/rag/api/v1/files/download/")
    assert file_info["original_name"] == "doc.txt"


@pytest.mark.asyncio
async def test_rag_upload_creates_file_record_in_shared_db(
    rag_client, auth_headers_system, mock_context
):
    """FileRecord создаётся в shared DB при загрузке RAG документа."""
    _skip_if_s3_disabled()

    ns = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": "test-ns-record-check"},
        headers=auth_headers_system,
    )
    if ns.status_code not in (200, 201):
        pytest.skip(f"Создание namespace недоступно: {ns.status_code}")
    namespace_id = ns.json()["name"]

    content = b"FileRecord creation check"
    r = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
        files={"file": ("record_check.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 202, r.text
    document_id = r.json()["document_id"]

    from core.context import set_context, clear_context
    from apps.rag.container import get_rag_container
    set_context(mock_context)
    try:
        container = get_rag_container()
        record = await container.file_repository.get(document_id)
    finally:
        clear_context()

    assert record is not None, "FileRecord должен существовать в shared DB после загрузки документа"
    assert record.file_id == document_id
    assert record.download_url is not None
    assert record.download_url.startswith("/rag/api/v1/files/download/")


@pytest.mark.asyncio
async def test_rag_download_via_rag_file_router(rag_client, auth_headers_system):
    """Загруженный в RAG документ скачивается через стандартный файловый роутер."""
    _skip_if_s3_disabled()

    ns = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": "test-ns-download"},
        headers=auth_headers_system,
    )
    if ns.status_code not in (200, 201):
        pytest.skip(f"Создание namespace недоступно: {ns.status_code}")
    namespace_id = ns.json()["name"]

    content = b"Downloadable document content"
    r = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
        files={"file": ("download_me.txt", io.BytesIO(content), "text/plain")},
    )
    assert r.status_code == 202, r.text
    document_id = r.json()["document_id"]

    dl = await rag_client.get(
        f"/rag/api/v1/files/download/{document_id}",
        headers=auth_headers_system,
    )
    assert dl.status_code == 200, dl.text
    assert dl.content == content


# ==============================================================================
# Валидация загрузки
# ==============================================================================

@pytest.mark.asyncio
async def test_upload_empty_file_rejected(sync_client, auth_headers_system):
    """Пустой файл → 400."""
    _skip_if_s3_disabled()
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert r.status_code == 400
    assert "Пустой" in r.json()["detail"]


@pytest.mark.asyncio
async def test_upload_without_s3_returns_503(auth_headers_system, monkeypatch):
    """Если S3 отключён — 503."""
    monkeypatch.setenv("S3__ENABLED", "false")

    import core.config.base as config_base
    config_base._settings_instance = None

    from apps.sync.main import app
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.post(
            "/sync/api/v1/files/",
            headers=auth_headers_system,
            files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
        )
    assert r.status_code == 503
    assert "S3" in r.json()["detail"]

    config_base._settings_instance = None


@pytest.mark.asyncio
async def test_frontend_upload_uses_unified_files_endpoint(frontend_client, auth_headers_system):
    """Frontend (api_version=None) тоже должен иметь /frontend/api/v1/files/*."""
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("frontend.txt", io.BytesIO(b"frontend payload"), "text/plain")},
    )
    assert r.status_code in {200, 503}, r.text
    if r.status_code == 200:
        data = r.json()
        assert data["url"].startswith("/frontend/api/v1/files/download/")


async def _assert_upload_endpoint_exists(client, service_prefix: str, auth_headers_system) -> None:
    response = await client.post(
        f"{service_prefix}/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("contract.txt", io.BytesIO(b"contract"), "text/plain")},
    )
    assert response.status_code != 404, response.text


@pytest.mark.asyncio
async def test_frontend_has_unified_files_upload_endpoint(frontend_client, auth_headers_system):
    await _assert_upload_endpoint_exists(frontend_client, "/frontend", auth_headers_system)


@pytest.mark.asyncio
async def test_sync_has_unified_files_upload_endpoint(sync_client, auth_headers_system):
    await _assert_upload_endpoint_exists(sync_client, "/sync", auth_headers_system)


@pytest.mark.asyncio
async def test_crm_has_unified_files_upload_endpoint(crm_client, auth_headers_system):
    await _assert_upload_endpoint_exists(crm_client, "/crm", auth_headers_system)


@pytest.mark.asyncio
async def test_rag_has_unified_files_upload_endpoint(rag_client, auth_headers_system):
    await _assert_upload_endpoint_exists(rag_client, "/rag", auth_headers_system)


@pytest.mark.asyncio
async def test_flows_has_unified_files_upload_endpoint(flows_client, auth_headers_system):
    await _assert_upload_endpoint_exists(flows_client, "/flows", auth_headers_system)
