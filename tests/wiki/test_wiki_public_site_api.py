"""
Публичный сайт: анонимный доступ к разделу по одной ссылке.

Инварианты: токен живёт на корне, сайт — его опубликованное поддерево, а файл
отдаётся только если встречается в содержимом страницы этого сайта.
"""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient
from io import BytesIO
from PIL import Image

from core.files.create_spec import (
    FileCreateSpec,
    FilePostCreate,
    FileSourceKind,
    FileSourceRef,
)
from core.files.retention import FileRetentionKind, FileRetentionSpec
from tests.fixtures.s3 import require_s3_configured
from tests.wiki.conftest import PAGES_URL

PUBLIC_URL = "/wiki/api/v1/public/pages"

pytestmark = pytest.mark.no_test_doubles


async def _issue_link(wiki_client: AsyncClient, wiki_page_id: str) -> str:
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page_id}/access/link", json={"enabled": True, "permission": "viewer"}
    )
    assert response.status_code == 200, response.text
    return response.json()["url"].rsplit("/", 1)[-1]


async def test_child_page_opens_by_root_token(wiki_client, wiki_client_anonymous, create_page, unique_id):
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Глава {unique_id}", parent_page_id=root["wiki_page_id"])
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/pages/{child['wiki_page_id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["wiki_page_id"] == child["wiki_page_id"]
    assert body["parent_page_id"] == root["wiki_page_id"]
    assert body["is_full_width"] is False


async def test_site_tree_lists_published_subtree(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Глава {unique_id}", parent_page_id=root["wiki_page_id"])
    grandchild = await create_page(f"Пункт {unique_id}", parent_page_id=child["wiki_page_id"])
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/tree")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root_page_id"] == root["wiki_page_id"]
    assert [item["wiki_page_id"] for item in body["items"]] == [
        root["wiki_page_id"],
        child["wiki_page_id"],
        grandchild["wiki_page_id"],
    ]
    assert body["items"][0]["has_children"] is True
    assert body["items"][2]["has_children"] is False


async def test_draft_page_hides_its_whole_branch(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Глава {unique_id}", parent_page_id=root["wiki_page_id"])
    grandchild = await create_page(f"Пункт {unique_id}", parent_page_id=child["wiki_page_id"])
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    unpublished = await wiki_client.patch(
        f"{PAGES_URL}/{child['wiki_page_id']}", json={"is_published": False}
    )

    assert unpublished.status_code == 200, unpublished.text
    tree = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/tree")
    assert [item["wiki_page_id"] for item in tree.json()["items"]] == [root["wiki_page_id"]]
    assert (
        await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/pages/{child['wiki_page_id']}")
    ).status_code == 404
    assert (
        await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/pages/{grandchild['wiki_page_id']}")
    ).status_code == 404


async def test_page_outside_site_is_not_available(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    root = await create_page(f"Раздел {unique_id}")
    stranger = await create_page(f"Другая {unique_id}")
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    response = await wiki_client_anonymous.get(
        f"{PUBLIC_URL}/{token}/pages/{stranger['wiki_page_id']}"
    )

    assert response.status_code == 404


async def test_deleted_child_leaves_the_site(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Глава {unique_id}", parent_page_id=root["wiki_page_id"])
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    assert (await wiki_client.delete(f"{PAGES_URL}/{child['wiki_page_id']}")).status_code == 204

    assert (
        await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/pages/{child['wiki_page_id']}")
    ).status_code == 404
    tree = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/tree")
    assert [item["wiki_page_id"] for item in tree.json()["items"]] == [root["wiki_page_id"]]


async def test_child_markdown_is_available_by_root_token(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(
        f"Глава {unique_id}",
        markdown="# Глава\n\nТекст главы.",
        parent_page_id=root["wiki_page_id"],
    )
    token = await _issue_link(wiki_client, root["wiki_page_id"])

    response = await wiki_client_anonymous.get(
        f"{PUBLIC_URL}/{token}/pages/{child['wiki_page_id']}/markdown"
    )

    assert response.status_code == 200, response.text
    assert response.json()["markdown"].startswith("# Глава")


async def test_site_tree_for_unknown_token_returns_404(wiki_client_anonymous):
    response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/not-a-real-token/tree")

    assert response.status_code == 404


def _wiki_image_spec() -> FileCreateSpec:
    return FileCreateSpec(
        source_kind=FileSourceKind.PLATFORM_AUXILIARY,
        source_ref=FileSourceRef(),
        retention=FileRetentionSpec(kind=FileRetentionKind.PLATFORM_DEFAULT),
        post_create=FilePostCreate(is_public=False),
    )


async def _upload_private_image(wiki_di, payload: bytes, name: str) -> str:
    record = await wiki_di.files_service.create(
        _wiki_image_spec(),
        payload,
        original_name=name,
        content_type="image/png",
    )
    assert record.is_public is False
    return record.file_id


async def _put_image_content(wiki_client: AsyncClient, wiki_page_id: str, file_id: str) -> None:
    response = await wiki_client.put(
        f"{PAGES_URL}/{wiki_page_id}/content",
        json={
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "image",
                        "attrs": {
                            "src": f"/wiki/api/v1/files/download/{file_id}",
                            "file_id": file_id,
                        },
                    }
                ],
            }
        },
    )
    assert response.status_code == 200, response.text


async def test_image_of_published_page_is_served_by_token(
    wiki_client, wiki_client_anonymous, wiki_di, wiki_domain_context, create_page, unique_id
):
    _ = wiki_domain_context
    require_s3_configured()
    page = await create_page(f"Раздел {unique_id}")
    png_buf = BytesIO()
    Image.new("RGB", (800, 600), (200, 60, 60)).save(png_buf, format="PNG")
    payload = png_buf.getvalue()
    file_id = await _upload_private_image(wiki_di, payload, f"cover-{unique_id}.png")
    await _put_image_content(wiki_client, page["wiki_page_id"], file_id)
    token = await _issue_link(wiki_client, page["wiki_page_id"])

    public_page = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}")
    assert public_page.status_code == 200, public_page.text
    image = public_page.json()["content"]["content"][0]
    assert image["attrs"]["src"] == f"{PUBLIC_URL}/{token}/files/{file_id}?v=lg"

    file_response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/files/{file_id}")

    assert file_response.status_code == 200, file_response.text
    assert file_response.content == payload

    variant_response = await wiki_client_anonymous.get(
        f"{PUBLIC_URL}/{token}/files/{file_id}?v=sm!sq"
    )
    assert variant_response.status_code == 200, variant_response.text
    assert variant_response.headers["content-type"] == "image/webp"
    assert variant_response.content != payload


async def test_file_outside_site_content_is_not_served(
    wiki_client, wiki_client_anonymous, wiki_di, wiki_domain_context, create_page, unique_id
):
    _ = wiki_domain_context
    require_s3_configured()
    page = await create_page(f"Раздел {unique_id}")
    stranger_file_id = await _upload_private_image(
        wiki_di, f"stranger-{unique_id}".encode("utf-8"), f"stranger-{unique_id}.png"
    )
    token = await _issue_link(wiki_client, page["wiki_page_id"])

    response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/files/{stranger_file_id}")

    assert response.status_code == 404


async def test_image_becomes_unavailable_when_page_is_unpublished(
    wiki_client, wiki_client_anonymous, wiki_di, wiki_domain_context, create_page, unique_id
):
    _ = wiki_domain_context
    require_s3_configured()
    root = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Глава {unique_id}", parent_page_id=root["wiki_page_id"])
    file_id = await _upload_private_image(
        wiki_di, f"child-image-{unique_id}".encode("utf-8"), f"child-{unique_id}.png"
    )
    await _put_image_content(wiki_client, child["wiki_page_id"], file_id)
    token = await _issue_link(wiki_client, root["wiki_page_id"])
    assert (
        await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/files/{file_id}")
    ).status_code == 200

    unpublished = await wiki_client.patch(
        f"{PAGES_URL}/{child['wiki_page_id']}", json={"is_published": False}
    )

    assert unpublished.status_code == 200, unpublished.text
    assert (
        await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}/files/{file_id}")
    ).status_code == 404


async def test_full_width_page_reports_width_publicly(
    wiki_client, wiki_client_anonymous, create_page, unique_id
):
    page = await create_page(f"Раздел {unique_id}")
    token = await _issue_link(wiki_client, page["wiki_page_id"])

    patched = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}", json={"is_full_width": True}
    )

    assert patched.status_code == 200, patched.text
    response = await wiki_client_anonymous.get(f"{PUBLIC_URL}/{token}")
    assert response.json()["is_full_width"] is True
