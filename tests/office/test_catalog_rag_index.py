"""
Office catalog RAG index: end-to-end сценарии без моков.

Инфраструктура: PostgreSQL, MinIO, rag_service (HTTP :9002), rag_worker (TaskIQ queue rag),
office_client (ASGI), rag_client (ASGI). Все мутации индекса — через real TaskIQ worker.
"""

from __future__ import annotations

import asyncio
import hashlib
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
from core.config import get_settings
from core.rag.search_options_resolver import resolve_platform_search_options
from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port
from tests.office.helpers import upload_office_file_bytes

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
    company_visible: bool = True,
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={"title": title, "company_visible": company_visible},
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
    namespace: str = "default",
) -> tuple[str, str]:
    from tests.office.access_helpers import upload_txt_document

    needle = f"office-rag-needle-{unique_id}-{title_suffix}"
    content = f"topic,content\nsearchable,{needle}\n".encode()
    file_id = await upload_txt_document(
        office_client,
        headers,
        catalog_id=catalog_id,
        title=f"{title_suffix} {unique_id}",
        content=content,
        namespace=namespace,
    )
    return file_id, needle


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
    expected_platform_defaults = resolve_platform_search_options(
        settings=get_settings(),
    ).model_dump(mode="json")
    assert status_payload == {
        "enabled": True,
        "rag_namespace_id": rag_namespace_id,
        "include_subcatalogs": False,
        "search_options": None,
        "platform_defaults": expected_platform_defaults,
        "totals": status_payload["totals"],
        "rag_index_updated_at": status_payload["rag_index_updated_at"],
    }
    assert status_payload["rag_index_updated_at"] is not None
    assert status_payload["platform_defaults"]["rrf_k"] is not None
    assert status_payload["platform_defaults"]["per_channel_top_k"] is not None

    probe = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": "empty catalog probe", "limit": 1},
        headers=auth_headers_system,
    )
    assert probe.status_code == 200


@pytest.mark.asyncio
async def test_documents_rag_index_statuses_batch_endpoint(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    """POST /documents/rag-index-statuses — лёгкий batch без list reload."""
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-statuses-batch-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    file_id, _needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="statuses-batch",
    )
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)

    missing_id = f"missing-file-{unique_id}"
    response = await office_client.post(
        "/documents/api/v1/documents/rag-index-statuses",
        headers=auth_headers_system,
        json={"file_ids": [file_id, missing_id]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["statuses"][file_id] == "ready"
    assert payload["statuses"][missing_id] == "absent"


@pytest.mark.asyncio
async def test_list_documents_includes_rag_index_status(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    """GET /documents: rag_index_status null без индекса; pending→ready при включённом RAG."""
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-list-status-{unique_id}",
    )
    file_id, _needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="list-status",
    )

    list_before = await office_client.get(
        f"/documents/api/v1/documents?catalog_id={catalog_id}",
        headers=auth_headers_system,
    )
    assert list_before.status_code == 200
    items_before = list_before.json()["items"]
    assert len(items_before) == 1
    assert items_before[0]["file_id"] == file_id
    assert items_before[0]["rag_index_status"] is None

    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    list_pending = await office_client.get(
        f"/documents/api/v1/documents?catalog_id={catalog_id}",
        headers=auth_headers_system,
    )
    assert list_pending.status_code == 200
    items_pending = list_pending.json()["items"]
    assert len(items_pending) == 1
    assert items_pending[0]["rag_index_status"] in ("pending", "ready")

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    await _wait_rag_document_completed(rag_client, file_id, auth_headers_system)

    list_ready = await office_client.get(
        f"/documents/api/v1/documents?catalog_id={catalog_id}",
        headers=auth_headers_system,
    )
    assert list_ready.status_code == 200
    items_ready = list_ready.json()["items"]
    assert len(items_ready) == 1
    assert items_ready[0]["file_id"] == file_id
    assert items_ready[0]["rag_index_status"] == "ready"


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
        company_visible=False,
    )
    add_member = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"members": [{"user_id": system_user2_id, "relation": "viewer"}]},
    )
    assert add_member.status_code == 200

    enable_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=auth_headers_system_user2,
    )
    assert enable_response.status_code == 403
    body = enable_response.json()
    assert body.get("code") == "authz_denied" or "can_admin" in str(body.get("detail", "")).lower()


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

    file_id, needle = await _upload_searchable_csv(
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
    file_id, needle = await _upload_searchable_csv(
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
        "absent": 0,
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

    uploaded = await upload_office_file_bytes(
        office_client,
        auth_headers_system,
        filename=f"raw-{unique_id}.txt",
        content=f"plain text content {needle}".encode(),
        content_type="text/plain",
    )
    file_id = str(uploaded["file_id"])

    create = await office_client.post(
        "/documents/api/v1/documents",
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
    file_id, needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}",
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
    file_id, needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    restore_response = await office_client.post(
        f"/documents/api/v1/documents/{file_id}/restore",
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
    file_id, needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}",
        headers=auth_headers_system,
    )
    assert soft_delete.status_code == 204

    permanent_delete = await office_client.delete(
        f"/documents/api/v1/documents/{file_id}/permanent",
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

    file_id, needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}/move",
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

    file_id, needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}/move",
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
    assert disabled_totals.absent == 0

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

    source_file_id, needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        source_catalog_id,
        unique_id,
        title_suffix="copy-src",
    )

    copy_response = await office_client.post(
        f"/documents/api/v1/documents/{source_file_id}/copy",
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
    file_id, _needle = await _upload_searchable_csv(
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
    file_id, _needle = await _upload_searchable_csv(
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
        f"/documents/api/v1/documents/{file_id}",
        headers=auth_headers_system,
    )
    assert soft_delete.status_code == 204

    permanent_delete = await office_client.delete(
        f"/documents/api/v1/documents/{file_id}/permanent",
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

    file_a, needle_a = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="rebuild-a",
    )
    file_b, needle_b = await _upload_searchable_csv(
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
async def test_signature_sidecar_skipped_from_catalog_rag_index(
    office_client,
    rag_client,
    rag_service,
    rag_worker,
    auth_headers_system,
    unique_id,
):
    """CryptoPro .sig sidecar не ставится в rag_index_document_s3; totals.failed=0."""
    _ = rag_service, rag_worker
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-sig-skip-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    file_csv, _needle = await _upload_searchable_csv(
        office_client,
        auth_headers_system,
        catalog_id,
        unique_id,
        title_suffix="with-sig",
    )
    sig_content = b"\x30\x82\x02\x00fake-cryptopro-detached-signature"
    sig_uploaded = await upload_office_file_bytes(
        office_client,
        auth_headers_system,
        filename=f"contract-{unique_id}.pdf.sig",
        content=sig_content,
        content_type="application/octet-stream",
    )
    file_sig = str(sig_uploaded["file_id"])
    sig_response = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        json={
            "file_id": file_sig,
            "title": f"sig {unique_id}",
            "catalog_id": catalog_id,
        },
    )
    assert sig_response.status_code == 200, sig_response.text
    sig_body = sig_response.json()
    assert sig_body["file_id"] == file_sig
    assert sig_body["file_category"] == "signature"

    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    totals = OfficeCatalogRagIndexStatusTotals.model_validate(status_payload["totals"])
    assert totals == OfficeCatalogRagIndexStatusTotals(
        ready=1,
        pending=0,
        failed=0,
        absent=1,
    )

    sig_status = await rag_client.get(
        f"/rag/api/v1/documents/{file_sig}/status",
        headers=auth_headers_system,
    )
    assert sig_status.status_code == 404
    await _wait_rag_document_completed(rag_client, file_csv, auth_headers_system)

    rebuild_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/rebuild",
        headers=auth_headers_system,
    )
    assert rebuild_response.status_code == 202
    await _wait_catalog_index_ready(
        office_client,
        catalog_id,
        auth_headers_system,
        ready_count=1,
    )
    after_rebuild = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    rebuild_totals = OfficeCatalogRagIndexStatusTotals.model_validate(after_rebuild["totals"])
    assert rebuild_totals.failed == 0
    assert rebuild_totals.absent == 1
    assert rebuild_totals.ready == 1


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

    uploaded = await upload_office_file_bytes(
        office_client,
        auth_headers_system,
        filename=f"callback-{unique_id}.txt",
        content=b"initial content before onlyoffice callback",
        content_type="text/plain",
    )
    file_id = str(uploaded["file_id"])

    create_response = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        json={
            "file_id": file_id,
            "catalog_id": catalog_id,
            "title": f"Callback doc {unique_id}",
        },
    )
    assert create_response.status_code == 200
    file_id = create_response.json()["file_id"]

    new_body = f"replaced content with {needle}".encode()
    office_saved_file_http["set_body"](new_body)

    integ = get_office_settings().office
    ctx_tok = encode_callback_context_token(
        file_id=file_id,
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
    meta = await container.files_service.get(file_id)
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
            "company_visible": True,
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
async def test_patch_rag_settings_persists_search_options(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-search-opts-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)

    patch_response = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/settings",
        headers=auth_headers_system,
        json={"rrf_k": 40, "freshness_weight": 0.2},
    )
    assert patch_response.status_code == 200
    patch_payload = patch_response.json()
    assert patch_payload["search_options"] is not None
    assert patch_payload["search_options"]["rrf_k"] == 40
    assert patch_payload["search_options"]["freshness_weight"] == 0.2

    status_payload = await _rag_index_status(office_client, catalog_id, auth_headers_system)
    status_search_options = status_payload["search_options"]
    assert isinstance(status_search_options, dict)
    assert status_search_options["rrf_k"] == 40
    assert status_search_options["freshness_weight"] == 0.2

    list_response = await office_client.get(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    catalog_item = next(
        item for item in list_response.json()["items"] if item["catalog_id"] == catalog_id
    )
    catalog_search_options = catalog_item["rag_index_search_options"]
    assert isinstance(catalog_search_options, dict)
    assert catalog_search_options["rrf_k"] == 40

    clear_response = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/settings",
        headers=auth_headers_system,
        json={"clear_search_options": True},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["search_options"] is None


@pytest.mark.asyncio
async def test_catalog_semantic_search_applies_catalog_search_options(
    office_client,
    auth_headers_system,
    unique_id,
    monkeypatch,
):
    catalog_id = await _create_catalog(
        office_client,
        auth_headers_system,
        f"rag-search-merge-{unique_id}",
    )
    await _enable_rag_index(office_client, catalog_id, auth_headers_system)
    await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/settings",
        headers=auth_headers_system,
        json={"rrf_k": 55, "freshness_weight": 0.15},
    )

    captured: dict[str, object] = {}

    async def _capture_search(
        namespace_id: str,
        query: str,
        *,
        limit: int,
        channels=None,
        rrf_k=None,
        per_channel_top_k=None,
        rerank=None,
        rerank_max_candidates=None,
        retrieval=None,
        freshness_weight=None,
        freshness_half_life_days=None,
    ) -> dict[str, object]:
        captured["namespace_id"] = namespace_id
        captured["query"] = query
        captured["limit"] = limit
        captured["rrf_k"] = rrf_k
        captured["freshness_weight"] = freshness_weight
        return {"results": []}

    container = get_office_container()
    monkeypatch.setattr(container.rag_client, "search", _capture_search)

    search_response = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/search",
        headers=auth_headers_system,
        json={"query": "needle", "limit": 10},
    )
    assert search_response.status_code == 200
    assert captured["rrf_k"] == 55
    assert captured["freshness_weight"] == 0.15
    assert captured["namespace_id"] == _rag_namespace_id(catalog_id)


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

    file_id, needle = await _upload_searchable_csv(
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
    assert matching_items[0].file_id
    assert matching_items[0].snippet
    assert matching_items[0].catalog_id == child_catalog_id
