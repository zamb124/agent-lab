"""
BFF documents/office: реальные PostgreSQL (platform_office), MinIO, httpx; callback — GET с aiohttp (как URL от Document Server).
"""

from __future__ import annotations

import hashlib
import io
from urllib.parse import parse_qs, quote, urlparse

import jwt
import pytest
from aiohttp import web

from apps.office.config import get_office_settings
from apps.office.container import get_office_container
from apps.office.services.callback_token import encode_callback_context_token
from apps.office.services.onlyoffice_jwt import decode_download_token
from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port

pytestmark = [pytest.mark.timeout(120)]


def _onlyoffice_editor_token(body: dict[str, object]) -> str:
    assert body.get("handler") == "onlyoffice"
    onlyoffice = body.get("onlyoffice")
    assert isinstance(onlyoffice, dict)
    token = onlyoffice.get("token")
    assert isinstance(token, str)
    return token


async def _first_accessible_catalog_id(office_client, headers: dict[str, str]) -> str:
    r = await office_client.get("/documents/api/v1/catalogs", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        cr = await office_client.post(
            "/documents/api/v1/catalogs",
            headers=headers,
            json={"title": "bff-integration-catalog"},
        )
        assert cr.status_code == 200
        return cr.json()["catalog_id"]
    return items[0]["catalog_id"]


@pytest.fixture
async def office_saved_file_http():
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
        yield {"base": base, "set_body": lambda b: state.update(body=b)}
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_documents_health_json_not_spa_shell(office_client):
    r = await office_client.get("/documents/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["service"] == "documents"
    assert "<!DOCTYPE html>" not in r.text


@pytest.mark.asyncio
async def test_office_integration_status_configured(office_client, auth_headers_system):
    r = await office_client.get(
        "/documents/api/v1/integration/status",
        headers=auth_headers_system,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert data["detail"] == ""


@pytest.mark.asyncio
async def test_office_list_namespaces_uses_shared_namespace_repository(
    office_client, auth_headers_system
):
    r = await office_client.get(
        "/documents/api/v1/namespaces",
        headers=auth_headers_system,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("items"), list)
    assert len(data["items"]) >= 1
    first = data["items"][0]
    assert isinstance(first.get("name"), str) and first["name"].strip() != ""
    assert "is_default" in first


@pytest.mark.asyncio
async def test_office_empty_document_list_rename_delete(office_client, auth_headers_system, unique_id):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    title = f"Empty doc {unique_id}"
    cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": title, "catalog_id": catalog_id},
    )
    assert cr.status_code == 200
    created = cr.json()
    binding_id = created["binding_id"]
    catalog_id = created["catalog_id"]

    lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system,
    )
    assert lr.status_code == 200
    items = lr.json()["items"]
    match = next((i for i in items if i["binding_id"] == binding_id), None)
    assert match is not None
    assert match["catalog_id"] == catalog_id
    assert match["title"] == title
    assert "created_at" in match
    assert "updated_at" in match
    assert isinstance(match["file_size"], int)
    assert match["file_size"] >= 0
    assert match["created_by_user_id"]
    assert "created_by_display_name" in match
    assert "created_by_avatar_url" in match

    new_title = f"Renamed {unique_id}"
    pr = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
        json={"title": new_title},
    )
    assert pr.status_code == 200
    assert pr.json()["title"] == new_title

    dr = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert dr.status_code == 204


@pytest.mark.asyncio
async def test_office_list_documents_search_and_sort(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    alpha_title = f"Alpha {unique_id}"
    beta_title = f"Beta {unique_id}"
    for title in (alpha_title, beta_title):
        cr = await office_client.post(
            "/documents/api/v1/documents/empty",
            headers=auth_headers_system,
            json={"title": title, "catalog_id": catalog_id},
        )
        assert cr.status_code == 200

    search_r = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id, "q": "Alpha"},
        headers=auth_headers_system,
    )
    assert search_r.status_code == 200
    search_items = search_r.json()["items"]
    assert any(i["title"] == alpha_title for i in search_items)
    assert not any(i["title"] == beta_title for i in search_items)

    sort_r = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id, "sort": "title", "order": "asc"},
        headers=auth_headers_system,
    )
    assert sort_r.status_code == 200
    sort_items = sort_r.json()["items"]
    titles = [i["title"] for i in sort_items if i["title"] in (alpha_title, beta_title)]
    assert titles == sorted(titles)


@pytest.mark.asyncio
async def test_office_upload_csv_cell_type(office_client, auth_headers_system, unique_id):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    files = {
        "file": (
            f"sheet-{unique_id}.csv",
            b"col1,col2\n1,2\n",
            "text/csv",
        )
    }
    r = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"title": f"CSV {unique_id}", "catalog_id": catalog_id},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["binding_id"]
    assert j["file_id"]
    assert j["catalog_id"]


@pytest.mark.asyncio
async def test_open_existing_file_as_document_is_same_file_and_idempotent(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    upload = await office_client.post(
        "/documents/api/v1/files/",
        headers=auth_headers_system,
        files={
            "file": (
                f"flow-table-{unique_id}.csv",
                io.BytesIO(b"a,b\n1,2\n"),
                "text/csv",
            )
        },
        data={"public": "false"},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    first = await office_client.post(
        "/documents/api/v1/documents/from-file",
        headers=auth_headers_system,
        json={"file_id": file_id, "catalog_id": catalog_id, "title": f"Flow table {unique_id}"},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["file_id"] == file_id
    assert first_body["catalog_id"] == catalog_id
    assert first_body["file_category"] == "spreadsheet"
    assert first_body["onlyoffice_document_type"] == "cell"
    assert first_body["editor_url"].startswith("/documents/embed/edit/")

    second = await office_client.post(
        "/documents/api/v1/documents/from-file",
        headers=auth_headers_system,
        json={"file_id": file_id, "catalog_id": catalog_id},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["binding_id"] == first_body["binding_id"]
    assert second_body["file_id"] == file_id


@pytest.mark.asyncio
async def test_office_empty_document_cell_slide_csv_editor_type(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    cases: list[tuple[dict[str, str], str]] = [
        ({"title": f"Cell {unique_id}", "document_type": "cell"}, "cell"),
        ({"title": f"Slide {unique_id}", "document_type": "slide"}, "slide"),
        (
            {
                "title": f"Csv {unique_id}",
                "document_type": "cell",
                "spreadsheet_format": "csv",
            },
            "cell",
        ),
    ]
    for payload, expected_dt in cases:
        body = {**payload, "catalog_id": catalog_id}
        cr = await office_client.post(
            "/documents/api/v1/documents/empty",
            headers=auth_headers_system,
            json=body,
        )
        assert cr.status_code == 200, payload
        binding_id = cr.json()["binding_id"]
        er = await office_client.get(
            f"/documents/api/v1/documents/{binding_id}/editor-config",
            headers=auth_headers_system,
        )
        assert er.status_code == 200
        secret = get_office_settings().office.jwt_secret
        cfg = jwt.decode(_onlyoffice_editor_token(er.json()), secret, algorithms=["HS256"])
        assert cfg["documentType"] == expected_dt


@pytest.mark.asyncio
async def test_office_empty_rejects_spreadsheet_format_for_word(
    office_client, auth_headers_system, unique_id
):
    r = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={
            "title": f"Bad {unique_id}",
            "document_type": "word",
            "spreadsheet_format": "xlsx",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_office_editor_config_download_roundtrip(office_client, auth_headers_system, unique_id):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"Editor {unique_id}", "catalog_id": catalog_id},
    )
    assert cr.status_code == 200
    binding_id = cr.json()["binding_id"]

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 200
    body = er.json()
    secret = get_office_settings().office.jwt_secret
    cfg = jwt.decode(_onlyoffice_editor_token(body), secret, algorithms=["HS256"])
    assert cfg["documentType"] == "word"
    assert cfg["document"]["key"] == binding_id or cfg["document"]["key"].startswith(f"{binding_id}_")
    assert cfg["editorConfig"]["mode"] == "edit"
    assert cfg["editorConfig"]["coEditing"]["mode"] == "fast"
    assert cfg["editorConfig"]["lang"] in ("ru", "en")
    cust = cfg["editorConfig"]["customization"]
    assert cust["compactToolbar"] is True
    assert cust["compactHeader"] is True
    assert cust["uiTheme"] == "theme-humanitec-light"
    assert cust["features"]["featuresTips"] is False
    logo = cust["logo"]
    assert "frontend_logo.svg" in logo["image"]
    assert "/static/core/" in logo["image"]
    assert logo["url"].endswith("/documents")
    assert cust["customer"]["name"] == "HUMANITEC"
    dl = cfg["document"]["url"]
    parsed = urlparse(dl)
    qs = parse_qs(parsed.query)
    token = qs["token"][0]
    dl_claims = decode_download_token(token, secret)
    assert dl_claims.binding_id == binding_id
    assert dl_claims.file_id == cr.json()["file_id"]
    path = parsed.path
    dlr = await office_client.get(f"{path}?token={quote(token, safe='')}")
    assert dlr.status_code == 200
    assert dlr.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_onlyoffice_callback_saves_to_s3(
    office_client,
    auth_headers_system,
    unique_id,
    office_saved_file_http,
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"Callback {unique_id}", "catalog_id": catalog_id},
    )
    assert cr.status_code == 200
    binding_id = cr.json()["binding_id"]
    file_id = cr.json()["file_id"]

    new_body = b"replaced-by-onlyoffice-callback-pipeline"
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

    post = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        headers={"Authorization": f"Bearer {bearer}"},
        json=auth_payload,
    )
    assert post.status_code == 200
    assert post.json()["error"] == 0

    c = get_office_container()
    meta = await c.file_processor.get_file_record(file_id)
    assert meta is not None
    expected_checksum = hashlib.sha256(new_body).hexdigest()
    assert meta.checksum == expected_checksum
    assert meta.file_size == len(new_body)

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 200
    cfg = jwt.decode(_onlyoffice_editor_token(er.json()), integ.jwt_secret, algorithms=["HS256"])
    assert cfg["document"]["key"] == f"{binding_id}_{expected_checksum[:24]}"

    office_saved_file_http["set_body"](b"duplicate-callback-should-not-apply")
    bearer_dup = jwt.encode({"payload": auth_payload}, integ.jwt_secret, algorithm="HS256")
    post_dup = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        headers={"Authorization": f"Bearer {bearer_dup}"},
        json=auth_payload,
    )
    assert post_dup.status_code == 200
    assert post_dup.json()["error"] == 0

    meta_after = await c.file_processor.get_file_record(file_id)
    assert meta_after.checksum == expected_checksum
    assert meta_after.file_size == len(new_body)


@pytest.mark.asyncio
async def test_office_nested_catalog_documents_list(office_client, auth_headers_system, unique_id):
    parent_title = f"Parent {unique_id}"
    pr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": parent_title, "is_public": True},
    )
    assert pr.status_code == 200
    parent_id = pr.json()["catalog_id"]

    child_title = f"Child {unique_id}"
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": child_title, "is_public": True, "parent_catalog_id": parent_id},
    )
    assert cr.status_code == 200
    child_id = cr.json()["catalog_id"]

    title = f"In subcatalog {unique_id}"
    doc_cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": title, "catalog_id": child_id},
    )
    assert doc_cr.status_code == 200
    binding_id = doc_cr.json()["binding_id"]

    parent_lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": parent_id},
        headers=auth_headers_system,
    )
    assert parent_lr.status_code == 200
    parent_ids = {item["binding_id"] for item in parent_lr.json()["items"]}
    assert binding_id not in parent_ids

    child_lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": child_id},
        headers=auth_headers_system,
    )
    assert child_lr.status_code == 200
    child_items = child_lr.json()["items"]
    match = next((item for item in child_items if item["binding_id"] == binding_id), None)
    assert match is not None
    assert match["catalog_id"] == child_id

    delete_parent = await office_client.delete(
        f"/documents/api/v1/catalogs/{parent_id}",
        headers=auth_headers_system,
    )
    assert delete_parent.status_code == 409

    await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    delete_child = await office_client.delete(
        f"/documents/api/v1/catalogs/{child_id}",
        headers=auth_headers_system,
    )
    assert delete_child.status_code == 204

    delete_parent_ok = await office_client.delete(
        f"/documents/api/v1/catalogs/{parent_id}",
        headers=auth_headers_system,
    )
    assert delete_parent_ok.status_code == 204


@pytest.mark.asyncio
async def test_office_nested_catalog_create(office_client, auth_headers_system, unique_id):
    parent_title = f"Parent {unique_id}"
    pr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": parent_title, "is_public": True},
    )
    assert pr.status_code == 200
    parent_id = pr.json()["catalog_id"]

    child_title = f"Child {unique_id}"
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": child_title, "is_public": True, "parent_catalog_id": parent_id},
    )
    assert cr.status_code == 200
    child = cr.json()
    assert child["parent_catalog_id"] == parent_id

    lr = await office_client.get("/documents/api/v1/catalogs", headers=auth_headers_system)
    assert lr.status_code == 200
    items = lr.json()["items"]
    child_item = next((item for item in items if item["catalog_id"] == child["catalog_id"]), None)
    assert child_item is not None
    assert child_item["parent_catalog_id"] == parent_id
    assert child_item["rag_index_enabled"] is False


@pytest.mark.asyncio
async def test_office_catalog_list_includes_rag_index_enabled(
    office_client,
    auth_headers_system,
    unique_id,
):
    title = f"RAG flag {unique_id}"
    create_response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": title, "is_public": True},
    )
    assert create_response.status_code == 200
    catalog_id = create_response.json()["catalog_id"]

    list_response = await office_client.get("/documents/api/v1/catalogs", headers=auth_headers_system)
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    catalog_item = next((item for item in items if item["catalog_id"] == catalog_id), None)
    assert catalog_item is not None
    assert catalog_item["rag_index_enabled"] is False
