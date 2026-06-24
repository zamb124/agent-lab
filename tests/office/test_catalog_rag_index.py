"""
Office catalog RAG index: end-to-end сценарии без моков.

Инфраструктура: PostgreSQL, MinIO, rag_service (HTTP :9002), rag_worker (TaskIQ queue rag),
office_client (ASGI), rag_client (ASGI). Все мутации индекса — через real TaskIQ worker.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from urllib.parse import quote

import jwt
import pytest

from apps.office.config import get_office_settings
from apps.office.container import get_office_container
from apps.office.models.api import (
    OfficeCatalogRagIndexStatusTotals,
    OfficeCatalogSemanticSearchResponse,
)
from apps.office.services.callback_token import encode_callback_context_token
from apps.office.services.catalog_rag_index_service import OFFICE_CATALOG_RAG_NAMESPACE_PREFIX
from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port

pytestmark = [pytest.mark.real_taskiq, pytest.mark.timeout(120)]


@pytest.fixture
async def office_saved_file_http():
    from aiohttp import web

    state = {"body": b"initial-bytes-for-office-callback-test"}

    async def handle(_request: web.Request) -> web.StreamResponse:
        return web.Response(body=state["body"], content_type="application/octet-stream")

    app = web.Application()
    app.router.add_get("/saved", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = tcp_site_assigned_port(site)
    base = f"http://127.0.0.1:{port}"
    try:
        yield {"base": base, "set_body": lambda body: state.update(body=body)}
    finally:
        await runner.cleanup()


async def _create_catalog(
    office_client,
    headers: dict[str, str],
    title: str,
    *,
    is_public: bool = True,
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={"title": title, "is_public": is_public},
    )
    assert response.status_code == 200
    return response.json()["catalog_id"]


def _rag_namespace_id(catalog_id: str) -> str:
    return f"{OFFICE_CATALOG_RAG_NAMESPACE_PREFIX}{catalog_id}"


async def _enable_rag_index(office_client, catalog_id: str, headers: dict[str, str]) -> dict[str, object]:
    response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rag_namespace_id"] == _rag_namespace_id(catalog_id)
    assert payload["initial_task_id"]
    return payload


async def _rag_index_status(office_client, catalog_id: str, headers: dict[str, str]) -> dict[str, object]:
    response = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/status",
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


async def _wait_rag_document_completed(
    rag_client,
    file_id: str,
    headers: dict[str, str],
    *,
    max_wait: float = 90.0,
) -> dict[str, object]:
    interval = 0.25
    elapsed = 0.0
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{file_id}/status",
            headers=headers,
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        if status_data["status"] == "completed":
            return status_data
        if status_data["status"] == "failed":
            pytest.fail(status_data.get("error_message"))
        await asyncio.sleep(interval)
        elapsed += interval
    pytest.fail(f"RAG document {file_id} did not complete within {max_wait}s")


async def _wait_catalog_index_ready(
    office_client,
    catalog_id: str,
    headers: dict[str, str],
    *,
    ready_count: int,
    max_wait: float = 90.0,
) -> dict[str, object]:
    interval = 0.25
    elapsed = 0.0
    while elapsed < max_wait:
        status_payload = await _rag_index_status(office_client, catalog_id, headers)
        totals = OfficeCatalogRagIndexStatusTotals.model_validate(status_payload["totals"])
        if totals.failed > 0:
            pytest.fail(f"catalog RAG indexing failed: {totals.model_dump()}")
        if totals.ready >= ready_count and totals.pending == 0:
            return status_payload
        await asyncio.sleep(interval)
        elapsed += interval
    last = await _rag_index_status(office_client, catalog_id, headers)
    pytest.fail(
        f"catalog {catalog_id} did not reach ready={ready_count} within {max_wait}s: {last['totals']}"
    )


async def _upload_searchable_csv(
    office_client,
    headers: dict[str, str],
    catalog_id: str,
    unique_id: str,
    *,
    title_suffix: str,
) -> tuple[str, str, str]:
    needle = f"office-rag-needle-{unique_id}-{title_suffix}"
    content = f"topic,content\nsearchable,{needle}\n".encode()
    response = await office_client.post(
        "/documents/api/v1/documents",
        headers=headers,
        files={"file": (f"{title_suffix}-{unique_id}.csv", io.BytesIO(content), "text/csv")},
        data={"title": f"{title_suffix} {unique_id}", "catalog_id": catalog_id},
    )
    assert response.status_code == 200
    body = response.json()
    return body["binding_id"], body["file_id"], needle


async def _search_catalog_namespace(
    rag_client,
    rag_namespace_id: str,
    query: str,
    headers: dict[str, str],
) -> list[dict[str, object]]:
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": query, "limit": 5},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["results"]


async def _assert_namespace_searchable(
    rag_client,
    rag_namespace_id: str,
    headers: dict[str, str],
    *,
    query: str,
    file_id: str,
) -> None:
    results = await _search_catalog_namespace(rag_client, rag_namespace_id, query, headers)
    document_ids = {item.get("document_id") for item in results}
    assert file_id in document_ids


async def _assert_namespace_search_misses_file(
    rag_client,
    rag_namespace_id: str,
    headers: dict[str, str],
    *,
    query: str,
    file_id: str,
) -> None:
    results = await _search_catalog_namespace(rag_client, rag_namespace_id, query, headers)
    document_ids = {item.get("document_id") for item in results}
    assert file_id not in document_ids


async def _assert_rag_namespace_absent(
    rag_client,
    rag_namespace_id: str,
    headers: dict[str, str],
) -> None:
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": "probe", "limit": 1},
        headers=headers,
    )
    assert response.status_code == 404


async def _assert_file_record_preserved(file_id: str) -> None:
    container = get_office_container()
    file_record = await container.file_repository.get(file_id)
    assert file_record is not None
    assert file_record.file_id == file_id


@pytest.mark.asyncio
async def test_enable_creates_namespace_and_sets_flag(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-enable-{unique_id}",
    )
    payload = await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    rag_namespace_id = payload["rag_namespace_id"]

    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload == {
        "enabled": True,
        "rag_namespace_id": rag_namespace_id,
        "totals": status_payload["totals"],
        "rag_index_updated_at": status_payload["rag_index_updated_at"],
    }
    assert status_payload["rag_index_updated_at"] is not None

    probe = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": "empty catalog probe", "limit": 1},
        headers=auth_headers_system,
    )
    assert probe.status_code == 200


@pytest.mark.asyncio
async def test_enable_idempotent_triggers_rebuild_task(
    office_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-idempotent-{unique_id}",
    )
    first = await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    second = await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    assert second["rag_namespace_id"] == first["rag_namespace_id"]
    assert second["initial_task_id"]
    assert second["initial_task_id"] != first["initial_task_id"]


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_rag_index(
    office_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-acl-{unique_id}",
        is_public=False,
    )
    add_member = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
        json={"user_id": system_user2_id},
    )
    assert add_member.status_code == 200

    enable_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=auth_headers_system_user2,
    )
    assert enable_response.status_code == 403
    assert enable_response.json()["detail"] == "Только владелец может управлять RAG-индексом каталога"


@pytest.mark.asyncio
async def test_upload_indexes_document_to_completed_and_searchable(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-upload-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    _binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="upload",
    )

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    status_data = await _wait_rag_document_completed(
        rag_client,
        file_id,
        auth_headers_system,
    )
    assert status_data["document_id"] == file_id
    assert status_data["status"] == "completed"

    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_upload_skips_index_when_catalog_rag_disabled(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-skipped-{unique_id}",
    )
    _binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="skipped",
    )

    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload["enabled"] is False
    assert status_payload["totals"] == {
        "ready": 0,
        "pending": 0,
        "failed": 0,
        "absent": 1,
    }

    status_response = await rag_client.get(
        f"/rag/api/v1/documents/{file_id}/status",
        headers=auth_headers_system,
    )
    assert status_response.status_code == 404

    await _assert_rag_namespace_absent(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_from_file_indexes_when_catalog_rag_enabled(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-from-file-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    needle = f"office-rag-from-file-{unique_id}"
    upload = await office_client.post(
        "/documents/api/v1/files/",
        headers=auth_headers_system,
        files={
            "file": (
                f"raw-{unique_id}.txt",
                io.BytesIO(f"plain text content {needle}".encode()),
                "text/plain",
            )
        },
        data={"public": "false"},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    create = await office_client.post(
        "/documents/api/v1/documents/from-file",
        headers=auth_headers_system,
        json={
            "file_id": file_id,
            "catalog_id": catalog_id,
            "title": f"From file {unique_id}",
        },
    )
    assert create.status_code == 200

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)
    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )


@pytest.mark.asyncio
async def test_soft_delete_unindexes_document(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-soft-del-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="soft-delete",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    delete_response = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload["totals"] == {
        "ready": 0,
        "pending": 0,
        "failed": 0,
        "absent": 0,
    }

    index_status = await rag_client.get(
        f"/rag/api/v1/documents/{file_id}/status",
        headers=auth_headers_system,
    )
    assert index_status.status_code == 404

    await _assert_namespace_search_misses_file(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_restore_reindexes_document(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-restore-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="restore",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    delete_response = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    restore_response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/restore",
        headers=auth_headers_system,
    )
    assert restore_response.status_code == 200

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)
    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )


@pytest.mark.asyncio
async def test_permanent_delete_unindexes_document(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-perm-del-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="permanent",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    soft_delete = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert soft_delete.status_code == 204

    permanent_delete = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}/permanent",
        headers=auth_headers_system,
    )
    assert permanent_delete.status_code == 204

    index_status = await rag_client.get(
        f"/rag/api/v1/documents/{file_id}/status",
        headers=auth_headers_system,
    )
    assert index_status.status_code == 404

    await _assert_namespace_search_misses_file(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_move_between_enabled_catalogs_reindexes_in_target_namespace(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    source_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-move-src-{unique_id}",
    )
    target_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-move-dst-{unique_id}",
    )
    await _enable_rag_index(office_client, source_catalog_id, auth_headers_system)
    await _enable_rag_index(office_client, target_catalog_id, auth_headers_system)

    binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        source_catalog_id,
        unique_id,
        title_suffix="move",
    )
    await _wait_catalog_index_ready(
        office_client,
        source_catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    move_response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/move",
        headers=auth_headers_system,
        json={"catalog_id": target_catalog_id},
    )
    assert move_response.status_code == 200
    assert move_response.json()["catalog_id"] == target_catalog_id

    await _wait_catalog_index_ready(
        office_client,
        target_catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)

    await _assert_namespace_search_misses_file(
        rag_client,
        _rag_namespace_id(source_catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )
    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(target_catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )


@pytest.mark.asyncio
async def test_move_to_disabled_catalog_unindexes_only(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    enabled_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-move-on-{unique_id}",
    )
    disabled_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-move-off-{unique_id}",
    )
    await _enable_rag_index(office_client, enabled_catalog_id, auth_headers_system)

    binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        enabled_catalog_id,
        unique_id,
        title_suffix="move-off",
    )
    await _wait_catalog_index_ready(
        office_client,
        enabled_catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    move_response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/move",
        headers=auth_headers_system,
        json={"catalog_id": disabled_catalog_id},
    )
    assert move_response.status_code == 200

    enabled_status = await _rag_index_status(
        office_client,
        enabled_catalog_id,
        auth_headers_system,
    )
    assert enabled_status["totals"] == {
        "ready": 0,
        "pending": 0,
        "failed": 0,
        "absent": 0,
    }

    disabled_status = await _rag_index_status(
        office_client,
        disabled_catalog_id,
        auth_headers_system,
    )
    assert disabled_status["enabled"] is False
    disabled_totals = OfficeCatalogRagIndexStatusTotals.model_validate(disabled_status["totals"])
    assert disabled_totals.absent == 1

    index_status = await rag_client.get(
        f"/rag/api/v1/documents/{file_id}/status",
        headers=auth_headers_system,
    )
    assert index_status.status_code == 404

    await _assert_namespace_search_misses_file(
        rag_client,
        _rag_namespace_id(enabled_catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_copy_to_enabled_catalog_indexes_new_file(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    source_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-copy-src-{unique_id}",
    )
    target_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-copy-dst-{unique_id}",
    )
    await _enable_rag_index(office_client, target_catalog_id, auth_headers_system)

    binding_id, source_file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        source_catalog_id,
        unique_id,
        title_suffix="copy-src",
    )

    copy_response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/copy",
        headers=auth_headers_system,
        json={"catalog_id": target_catalog_id, "title": f"Copy {unique_id}"},
    )
    assert copy_response.status_code == 200
    copied_file_id = copy_response.json()["file_id"]
    assert copied_file_id != source_file_id

    await _wait_catalog_index_ready(
        office_client,
        target_catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, copied_file_id, auth_headers_system)
    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(target_catalog_id),
        auth_headers_system,
        query=needle,
        file_id=copied_file_id,
    )
    await _assert_file_record_preserved(source_file_id)
    await _assert_file_record_preserved(copied_file_id)


@pytest.mark.asyncio
async def test_disable_removes_rag_namespace_and_preserves_files(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-disable-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    _binding_id, file_id, _needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="disable",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )

    disable_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/disable",
        headers=auth_headers_system,
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["success"] is True

    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload["enabled"] is False

    await _assert_rag_namespace_absent(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_delete_catalog_disables_rag_namespace(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-del-cat-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    _binding_id, file_id, _needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="delete-catalog",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    rag_namespace_id = _rag_namespace_id(catalog_id)

    soft_delete = await office_client.delete(
        f"/documents/api/v1/documents/{_binding_id}",
        headers=auth_headers_system,
    )
    assert soft_delete.status_code == 204

    permanent_delete = await office_client.delete(
        f"/documents/api/v1/documents/{_binding_id}/permanent",
        headers=auth_headers_system,
    )
    assert permanent_delete.status_code == 204

    delete_catalog = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert delete_catalog.status_code == 204

    await _assert_rag_namespace_absent(
        rag_client,
        rag_namespace_id,
        auth_headers_system,
    )
    await _assert_file_record_preserved(file_id)


@pytest.mark.asyncio
async def test_rebuild_reindexes_all_bindings(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-rebuild-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    _binding_a, file_a, needle_a = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="rebuild-a",
    )
    _binding_b, file_b, needle_b = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="rebuild-b",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=2,
    )

    rebuild_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/rebuild",
        headers=auth_headers_system,
    )
    assert rebuild_response.status_code == 202
    assert rebuild_response.json()["task_id"]

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=2,
    )
    await _wait_rag_document_completed(rag_client, file_a, auth_headers_system)
    await _wait_rag_document_completed(rag_client, file_b, auth_headers_system)

    rag_namespace_id = _rag_namespace_id(catalog_id)
    await _assert_namespace_searchable(
        rag_client,
        rag_namespace_id,
        auth_headers_system,
        query=needle_a,
        file_id=file_a,
    )
    await _assert_namespace_searchable(
        rag_client,
        rag_namespace_id,
        auth_headers_system,
        query=needle_b,
        file_id=file_b,
    )


@pytest.mark.asyncio
async def test_rebuild_when_rag_disabled_returns_409(
    office_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-rebuild-off-{unique_id}",
    )

    rebuild_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/rebuild",
        headers=auth_headers_system,
    )
    assert rebuild_response.status_code == 409
    assert rebuild_response.json()["detail"] == "RAG-индекс для каталога не включён"


@pytest.mark.asyncio
async def test_onlyoffice_callback_save_reindexes_document(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
    office_saved_file_http,
):
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-callback-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    needle = f"office-rag-callback-{unique_id}"
    upload_response = await office_client.post(
        "/documents/api/v1/files/",
        headers=auth_headers_system,
        files={
            "file": (
                f"callback-{unique_id}.txt",
                io.BytesIO(b"initial content before onlyoffice callback"),
                "text/plain",
            )
        },
        data={"public": "false"},
    )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]

    create_response = await office_client.post(
        "/documents/api/v1/documents/from-file",
        headers=auth_headers_system,
        json={
            "file_id": file_id,
            "catalog_id": catalog_id,
            "title": f"Callback doc {unique_id}",
        },
    )
    assert create_response.status_code == 200
    binding_id = create_response.json()["binding_id"]

    new_body = f"replaced content with {needle}".encode()
    office_saved_file_http["set_body"](new_body)

    integ = get_office_settings().office
    ctx_tok = encode_callback_context_token(
        binding_id=binding_id,
        company_id="system",
        namespace="default",
        secret=integ.jwt_secret,
        ttl_seconds=3600,
    )
    file_url = f"{office_saved_file_http['base']}/saved"
    auth_payload = {"status": 2, "url": file_url}
    bearer = jwt.encode({"payload": auth_payload}, integ.jwt_secret, algorithm="HS256")

    callback_response = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        headers={"Authorization": f"Bearer {bearer}"},
        json=auth_payload,
    )
    assert callback_response.status_code == 200
    assert callback_response.json()["error"] == 0

    container = get_office_container()
    meta = await container.file_processor.get_file_record(file_id)
    assert meta is not None
    assert meta.checksum == hashlib.sha256(new_body).hexdigest()

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)
    await _assert_namespace_searchable(
        rag_client,
        _rag_namespace_id(catalog_id),
        auth_headers_system,
        query=needle,
        file_id=file_id,
    )


async def _create_subcatalog(
    office_client,
    headers: dict[str, str],
    parent_catalog_id: str,
    title: str,
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={
            "title": title,
            "is_public": True,
            "parent_catalog_id": parent_catalog_id,
        },
    )
    assert response.status_code == 200
    return response.json()["catalog_id"]


async def _patch_rag_include_subcatalogs(
    office_client,
    catalog_id: str,
    headers: dict[str, str],
    *,
    include_subcatalogs: bool,
) -> dict[str, object]:
    response = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/settings",
        headers=headers,
        json={"include_subcatalogs": include_subcatalogs},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["include_subcatalogs"] is include_subcatalogs
    return payload


async def _catalog_semantic_search(
    office_client,
    catalog_id: str,
    headers: dict[str, str],
    *,
    query: str,
) -> OfficeCatalogSemanticSearchResponse:
    response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/search",
        headers=headers,
        json={"query": query, "limit": 20},
    )
    assert response.status_code == 200
    return OfficeCatalogSemanticSearchResponse.model_validate(response.json())


@pytest.mark.asyncio
async def test_patch_rag_settings_persists_include_subcatalogs(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-settings-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    await _patch_rag_include_subcatalogs(
        office_client,
        catalog_id,
        auth_headers_system,
        include_subcatalogs=True,
    )
    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload["include_subcatalogs"] is True

    await _patch_rag_include_subcatalogs(
        office_client,
        catalog_id,
        auth_headers_system,
        include_subcatalogs=False,
    )
    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    assert status_payload["include_subcatalogs"] is False


@pytest.mark.asyncio
async def test_nested_catalog_semantic_search_respects_include_subcatalogs(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    _ = rag_service, rag_worker
    parent_catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-parent-{unique_id}",
    )
    child_catalog_id = await _create_subcatalog(
        office_client,
        auth_headers_system,
        parent_catalog_id,
        f"rag-child-{unique_id}",
    )
    await _enable_rag_index(office_client, parent_catalog_id, auth_headers_system)
    await _enable_rag_index(office_client, child_catalog_id, auth_headers_system)

    _binding_id, file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        child_catalog_id,
        unique_id,
        title_suffix="nested-child",
    )
    await _wait_catalog_index_ready(
        office_client,
        child_catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)

    scoped_search = await _catalog_semantic_search(
        office_client,
        parent_catalog_id,
        auth_headers_system,
        query=needle,
    )
    assert scoped_search.include_subcatalogs is False
    assert file_id not in {item.file_id for item in scoped_search.items}

    await _patch_rag_include_subcatalogs(
        office_client,
        parent_catalog_id,
        auth_headers_system,
        include_subcatalogs=True,
    )
    subtree_search = await _catalog_semantic_search(
        office_client,
        parent_catalog_id,
        auth_headers_system,
        query=needle,
    )
    assert subtree_search.include_subcatalogs is True
    assert child_catalog_id in subtree_search.catalog_ids
    matching_items = [item for item in subtree_search.items if item.file_id == file_id]
    assert len(matching_items) == 1
    assert matching_items[0].binding_id
    assert matching_items[0].snippet
    assert matching_items[0].catalog_id == child_catalog_id
