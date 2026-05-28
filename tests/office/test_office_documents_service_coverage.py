"""
Полное интеграционное покрытие BFF documents (office): PostgreSQL platform_office, shared (company/user),
S3/MinIO, Redis (callback dedupe), без моков внутренних компонентов платформы.
"""

from __future__ import annotations

import time
from urllib.parse import quote

import jwt
import pytest

from apps.office.config import get_office_settings
from apps.office.services.callback_token import encode_callback_context_token
from apps.office.services.minimal_ooxml import minimal_pptx_bytes, minimal_xlsx_bytes
from apps.office.services.onlyoffice_jwt import encode_download_token

pytestmark = [pytest.mark.timeout(120)]


def _decode_editor_config_token(token: str) -> dict[str, object]:
    secret = get_office_settings().office.jwt_secret
    payload: dict[str, object] = jwt.decode(token, secret, algorithms=["HS256"])  # pyright: ignore[reportAssignmentType]
    return payload


def _editor_document_file_type(cfg: dict[str, object]) -> str:
    document_raw = cfg["document"]
    if not isinstance(document_raw, dict):
        raise AssertionError("document must be object")
    file_type = document_raw.get("fileType")
    if not isinstance(file_type, str):
        raise AssertionError("document.fileType must be str")
    return file_type


async def _first_accessible_catalog_id(office_client, headers: dict[str, str]) -> str:
    r = await office_client.get("/documents/api/v1/catalogs", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        cr = await office_client.post(
            "/documents/api/v1/catalogs",
            headers=headers,
            json={"title": "integration-catalog"},
        )
        assert cr.status_code == 200
        return cr.json()["catalog_id"]
    return items[0]["catalog_id"]


@pytest.mark.asyncio
async def test_documents_list_requires_catalog_id(office_client, auth_headers_system):
    r = await office_client.get(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_documents_list_multiple_catalog_ids(
    office_client, auth_headers_system, unique_id
):
    cr1 = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"M1 {unique_id}"},
    )
    cr2 = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"M2 {unique_id}"},
    )
    assert cr1.status_code == 200
    assert cr2.status_code == 200
    id1 = cr1.json()["catalog_id"]
    id2 = cr2.json()["catalog_id"]
    d1 = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"D1 {unique_id}", "catalog_id": id1},
    )
    assert d1.status_code == 200
    bid1 = d1.json()["binding_id"]

    r_both = await office_client.get(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        params=[("catalog_ids", id1), ("catalog_ids", id2)],
    )
    assert r_both.status_code == 200
    items_both = r_both.json()["items"]
    ids_both = {x["binding_id"] for x in items_both}
    assert bid1 in ids_both

    r_second_only = await office_client.get(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        params=[("catalog_ids", id2)],
    )
    assert r_second_only.status_code == 200
    items_second = r_second_only.json()["items"]
    ids_second = {x["binding_id"] for x in items_second}
    assert bid1 not in ids_second


@pytest.mark.asyncio
async def test_company_members_lists_company_from_shared_storage(
    office_client, auth_headers_system, system_user_id
):
    r = await office_client.get(
        "/documents/api/v1/company-members",
        headers=auth_headers_system,
    )
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    ids = {row["user_id"] for row in rows}
    assert system_user_id in ids
    for row in rows:
        assert "name" in row
        assert "roles" in row
        assert isinstance(row["roles"], list)


@pytest.mark.asyncio
async def test_catalogs_crud_and_list_contains_file_count(
    office_client, auth_headers_system, unique_id
):
    title = f"Cat {unique_id}"
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": title},
    )
    assert cr.status_code == 200
    body = cr.json()
    catalog_id = body["catalog_id"]
    assert body["title"] == title
    assert body["is_owner"] is True
    assert body["is_public"] is True

    lr = await office_client.get(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
    )
    assert lr.status_code == 200
    items = lr.json()["items"]
    found = next((x for x in items if x["catalog_id"] == catalog_id), None)
    assert found is not None
    assert found["file_count"] == 0
    assert found["owner_user_id"]
    assert found["is_public"] is True

    gr = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert gr.status_code == 200
    assert gr.json()["catalog_id"] == catalog_id

    new_title = f"CatRenamed {unique_id}"
    pr = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
        json={"title": new_title},
    )
    assert pr.status_code == 200
    assert pr.json()["title"] == new_title

    pr_vis = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
        json={"is_public": False},
    )
    assert pr_vis.status_code == 200
    assert pr_vis.json()["is_public"] is False

    pr_back = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
        json={"is_public": True, "title": new_title},
    )
    assert pr_back.status_code == 200
    assert pr_back.json()["is_public"] is True

    dr = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert dr.status_code == 204

    gr2 = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert gr2.status_code == 404


@pytest.mark.asyncio
async def test_catalog_delete_409_when_contains_documents(
    office_client, auth_headers_system, unique_id
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"WithFiles {unique_id}"},
    )
    assert cr_cat.status_code == 200
    catalog_id = cr_cat.json()["catalog_id"]

    doc = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"InCat {unique_id}", "catalog_id": catalog_id},
    )
    assert doc.status_code == 200

    dr = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert dr.status_code == 409


@pytest.mark.asyncio
async def test_empty_document_requires_catalog_id_when_multiple_catalogs(
    office_client, auth_headers_system, unique_id
):
    a = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"A {unique_id}"},
    )
    b = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"B {unique_id}"},
    )
    assert a.status_code == 200
    assert b.status_code == 200

    r = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"Amb {unique_id}"},
    )
    assert r.status_code == 400
    assert "catalog_id" in (r.json().get("detail") or "").lower()


@pytest.mark.asyncio
async def test_catalog_acl_member_access_after_invite(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"Shared {unique_id}", "is_public": False},
    )
    assert cr_cat.status_code == 200
    catalog_id = cr_cat.json()["catalog_id"]

    blocked = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert blocked.status_code == 403

    add = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
        json={"user_id": system_user2_id},
    )
    assert add.status_code == 200
    members = add.json()["members"]
    ids = {m["user_id"] for m in members}
    assert system_user2_id in ids

    ok = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert ok.status_code == 200

    patch_denied = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system_user2,
        json={"title": f"Hacked {unique_id}"},
    )
    assert patch_denied.status_code == 403

    add_denied = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system_user2,
        json={"user_id": system_user2_id},
    )
    assert add_denied.status_code == 403


@pytest.mark.asyncio
async def test_catalog_public_default_allows_company_peer_documents(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"Pub {unique_id}"},
    )
    assert cr_cat.status_code == 200
    assert cr_cat.json()["is_public"] is True
    catalog_id = cr_cat.json()["catalog_id"]
    ok = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_catalog_add_member_forbidden_when_public(
    office_client,
    auth_headers_system,
    system_user2_id,
    unique_id,
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"PubMem {unique_id}", "is_public": True},
    )
    assert cr_cat.status_code == 200
    catalog_id = cr_cat.json()["catalog_id"]
    add = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
        json={"user_id": system_user2_id},
    )
    assert add.status_code == 400


@pytest.mark.asyncio
async def test_get_catalog_detail_includes_is_public(
    office_client, auth_headers_system, unique_id
):
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"Detail {unique_id}", "is_public": False},
    )
    assert cr.status_code == 200
    catalog_id = cr.json()["catalog_id"]
    assert cr.json()["is_public"] is False
    gr = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system,
    )
    assert gr.status_code == 200
    body = gr.json()
    assert body["catalog_id"] == catalog_id
    assert body["is_public"] is False


@pytest.mark.asyncio
async def test_peer_sees_public_catalog_in_list(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    title = f"PubPeer {unique_id}"
    cr1 = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": title, "is_public": True},
    )
    assert cr1.status_code == 200
    catalog_id = cr1.json()["catalog_id"]
    lr = await office_client.get(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system_user2,
    )
    assert lr.status_code == 200
    items = lr.json()["items"]
    ids = {x["catalog_id"] for x in items}
    assert catalog_id in ids
    found = next(x for x in items if x["catalog_id"] == catalog_id)
    assert found["is_public"] is True
    assert found["title"] == title


@pytest.mark.asyncio
async def test_private_catalog_not_listed_for_peer(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    cr1 = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"PrivPeer {unique_id}", "is_public": False},
    )
    assert cr1.status_code == 200
    catalog_id = cr1.json()["catalog_id"]
    lr = await office_client.get(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system_user2,
    )
    assert lr.status_code == 200
    ids = {x["catalog_id"] for x in lr.json()["items"]}
    assert catalog_id not in ids


@pytest.mark.asyncio
async def test_patch_is_public_forbidden_for_non_owner(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"OwnPatch {unique_id}", "is_public": True},
    )
    assert cr.status_code == 200
    catalog_id = cr.json()["catalog_id"]
    pr = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system_user2,
        json={"is_public": False},
    )
    assert pr.status_code == 403


@pytest.mark.asyncio
async def test_catalog_list_members_get_and_remove_member(
    office_client,
    auth_headers_system,
    system_user2_id,
    unique_id,
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"Members {unique_id}", "is_public": False},
    )
    assert cr_cat.status_code == 200
    catalog_id = cr_cat.json()["catalog_id"]

    gr0 = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
    )
    assert gr0.status_code == 200
    assert len(gr0.json()["members"]) >= 1

    add = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
        json={"user_id": system_user2_id},
    )
    assert add.status_code == 200
    gr1 = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
    )
    assert gr1.status_code == 200
    ids = {m["user_id"] for m in gr1.json()["members"]}
    assert system_user2_id in ids

    rm = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}/members/{system_user2_id}",
        headers=auth_headers_system,
    )
    assert rm.status_code == 204

    gr2 = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
    )
    assert gr2.status_code == 200
    ids2 = {m["user_id"] for m in gr2.json()["members"]}
    assert system_user2_id not in ids2


@pytest.mark.asyncio
async def test_delete_catalog_forbidden_for_non_owner(
    office_client, auth_headers_system, auth_headers_system_user2, unique_id
):
    cr = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"NoDel {unique_id}"},
    )
    assert cr.status_code == 200
    catalog_id = cr.json()["catalog_id"]
    dr = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}",
        headers=auth_headers_system_user2,
    )
    assert dr.status_code == 403


@pytest.mark.asyncio
async def test_catalog_member_remove_owner_forbidden(
    office_client, auth_headers_system, unique_id
):
    cr_cat = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=auth_headers_system,
        json={"title": f"Own {unique_id}"},
    )
    catalog_id = cr_cat.json()["catalog_id"]
    owner_id = cr_cat.json()["owner_user_id"]
    rm = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}/members/{owner_id}",
        headers=auth_headers_system,
    )
    assert rm.status_code == 400


@pytest.mark.asyncio
async def test_office_download_rejects_invalid_and_mismatched_tokens(office_client):
    secret = get_office_settings().office.jwt_secret
    r0 = await office_client.get(
        "/documents/api/v1/office-download?token=not-a-jwt",
    )
    assert r0.status_code == 401

    now = int(time.time())
    no_binding = jwt.encode(
        {
            "typ": "office_dl",
            "file_id": "file_x",
            "company_id": "system",
            "iat": now,
            "exp": now + 120,
        },
        secret,
        algorithm="HS256",
    )
    r1 = await office_client.get(
        f"/documents/api/v1/office-download?token={quote(no_binding, safe='')}",
    )
    assert r1.status_code == 401

    wrong_binding = encode_download_token(
        file_id="file_never_exists_zzzz",
        company_id="system",
        binding_id="a" * 64,
        secret=secret,
        ttl_seconds=120,
    )
    r2 = await office_client.get(
        f"/documents/api/v1/office-download?token={quote(wrong_binding, safe='')}",
    )
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(office_client, auth_headers_system, unique_id):
    files = {
        "file": (
            f"empty-{unique_id}.txt",
            b"",
            "text/plain",
        )
    }
    r = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"title": "x"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_onlyoffice_callback_invalid_context_token_401(office_client):
    r = await office_client.post(
        "/documents/api/v1/onlyoffice/callback?token=not-a-valid-jwt",
        json={"status": 1},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_onlyoffice_callback_requires_bearer_and_accepts_status_without_save(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"Cb meta {unique_id}", "catalog_id": catalog_id},
    )
    assert cr.status_code == 200
    binding_id = cr.json()["binding_id"]

    integ = get_office_settings().office
    ctx_tok = encode_callback_context_token(
        binding_id=binding_id,
        company_id="system",
        namespace="default",
        secret=integ.jwt_secret,
        ttl_seconds=3600,
    )

    no_auth = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        json={"status": 1},
    )
    assert no_auth.status_code == 401

    bearer = jwt.encode({"payload": {"status": 1}}, integ.jwt_secret, algorithm="HS256")
    ok = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"status": 1},
    )
    assert ok.status_code == 200
    assert ok.json()["error"] == 0

    body_token = jwt.encode({"status": 1}, integ.jwt_secret, algorithm="HS256")
    ok_body_token = await office_client.post(
        f"/documents/api/v1/onlyoffice/callback?token={quote(ctx_tok, safe='')}",
        json={"token": body_token},
    )
    assert ok_body_token.status_code == 200
    assert ok_body_token.json()["error"] == 0


@pytest.mark.asyncio
async def test_editor_and_rename_404_unknown_binding(
    office_client, auth_headers_system, unique_id
):
    fake_id = "deadbeef" * 8
    er = await office_client.get(
        f"/documents/api/v1/documents/{fake_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 404

    pr = await office_client.patch(
        f"/documents/api/v1/documents/{fake_id}",
        headers=auth_headers_system,
        json={"title": f"Nope {unique_id}"},
    )
    assert pr.status_code == 404


@pytest.mark.asyncio
async def test_get_catalog_unknown_returns_404(office_client, auth_headers_system):
    r = await office_client.get(
        "/documents/api/v1/catalogs/" + ("c" * 64),
        headers=auth_headers_system,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_office_download_token_mismatch_file_id(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    cr = await office_client.post(
        "/documents/api/v1/documents/empty",
        headers=auth_headers_system,
        json={"title": f"Tok {unique_id}", "catalog_id": catalog_id},
    )
    assert cr.status_code == 200
    binding_id = cr.json()["binding_id"]
    secret = get_office_settings().office.jwt_secret
    bad = encode_download_token(
        file_id="file_wrong_id_on_purpose",
        company_id="system",
        binding_id=binding_id,
        secret=secret,
        ttl_seconds=120,
    )
    r = await office_client.get(
        f"/documents/api/v1/office-download?token={quote(bad, safe='')}",
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_editor_config_jwt_matches_uploaded_xlsx(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    files = {
        "file": (
            f"upload-{unique_id}.xlsx",
            minimal_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    up = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"title": f"X {unique_id}", "catalog_id": catalog_id},
    )
    assert up.status_code == 200
    binding_id = up.json()["binding_id"]

    lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system,
    )
    assert lr.status_code == 200
    row = next(i for i in lr.json()["items"] if i["binding_id"] == binding_id)
    assert row["document_type"] == "cell"

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 200
    cfg = _decode_editor_config_token(er.json()["token"])
    assert cfg["documentType"] == "cell"
    assert _editor_document_file_type(cfg) == "xlsx"


@pytest.mark.asyncio
async def test_editor_config_jwt_matches_uploaded_pptx(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    files = {
        "file": (
            f"deck-{unique_id}.pptx",
            minimal_pptx_bytes(),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    }
    up = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"title": f"P {unique_id}", "catalog_id": catalog_id},
    )
    assert up.status_code == 200
    binding_id = up.json()["binding_id"]

    lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system,
    )
    row = next(i for i in lr.json()["items"] if i["binding_id"] == binding_id)
    assert row["document_type"] == "slide"

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 200
    cfg = _decode_editor_config_token(er.json()["token"])
    assert cfg["documentType"] == "slide"
    assert _editor_document_file_type(cfg) == "pptx"


@pytest.mark.asyncio
async def test_editor_config_jwt_matches_uploaded_csv(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    csv_body = b"a,b\n1,2\n"
    files = {
        "file": (
            f"grid-{unique_id}.csv",
            csv_body,
            "text/csv",
        )
    }
    up = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"catalog_id": catalog_id},
    )
    assert up.status_code == 200
    binding_id = up.json()["binding_id"]

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    assert er.status_code == 200
    cfg = _decode_editor_config_token(er.json()["token"])
    assert cfg["documentType"] == "cell"
    assert _editor_document_file_type(cfg) == "csv"


@pytest.mark.asyncio
async def test_upload_filename_blob_spreadsheet_mime_stores_cell_and_editor_cell(
    office_client, auth_headers_system, unique_id
):
    catalog_id = await _first_accessible_catalog_id(office_client, auth_headers_system)
    files = {
        "file": (
            "blob",
            minimal_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    up = await office_client.post(
        "/documents/api/v1/documents",
        headers=auth_headers_system,
        files=files,
        data={"title": f"Blob {unique_id}", "catalog_id": catalog_id},
    )
    assert up.status_code == 200
    binding_id = up.json()["binding_id"]

    lr = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system,
    )
    row = next(i for i in lr.json()["items"] if i["binding_id"] == binding_id)
    assert row["document_type"] == "cell"

    er = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/editor-config",
        headers=auth_headers_system,
    )
    cfg = _decode_editor_config_token(er.json()["token"])
    assert cfg["documentType"] == "cell"
    assert _editor_document_file_type(cfg) == "xlsx"
