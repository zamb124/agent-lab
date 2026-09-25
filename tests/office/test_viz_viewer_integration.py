"""Office BFF: .viz FileRecord → editor-config handler=viz + viewer-stream roundtrip."""

from __future__ import annotations

import json

import pytest

from core.viz.models import (
    VIZ_CONTENT_TYPE,
    VizDocument,
    VizEngine,
    VizKind,
    parse_viz_document_bytes,
)
from tests.fixtures.s3 import require_s3_configured
from tests.office.access_helpers import parse_viz_stream_url
from tests.office.helpers import upload_office_file_bytes

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]


def _viz_bytes(*, title: str, source: str) -> bytes:
    document = VizDocument(
        kind=VizKind.FLOWCHART,
        engine=VizEngine.MERMAID,
        title=title,
        spec={"source": source},
    )
    return json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )


async def _upload_viz(
    office_client,
    auth_headers_system: dict[str, str],
    *,
    unique_id: str,
    title: str,
    source: str,
) -> str:
    require_s3_configured()
    uploaded = await upload_office_file_bytes(
        office_client,
        auth_headers_system,
        filename=f"{title.replace(' ', '-')}-{unique_id}.viz",
        content=_viz_bytes(title=title, source=source),
        content_type=VIZ_CONTENT_TYPE,
    )
    file_id = uploaded.get("file_id")
    assert isinstance(file_id, str) and file_id
    return file_id


async def test_viz_file_editor_config(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    title = f"EditorConfig {unique_id}"
    source = "flowchart TD\n  A-->B"
    file_id = await _upload_viz(
        office_client,
        auth_headers_system,
        unique_id=unique_id,
        title=title,
        source=source,
    )
    response = await office_client.get(
        f"/documents/api/v1/files/{file_id}/editor-config",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handler"] == "viz"
    assert body["file_id"] == file_id
    caps = body["capabilities"]
    assert caps["view"] is True
    assert caps["preview"] is True
    assert caps["edit"] is False
    assert caps["sync_on_close"] is False
    viz = body["viz"]
    assert isinstance(viz, dict)
    assert viz["kind"] == "flowchart"
    assert viz["engine"] == "mermaid"
    assert viz["title"] == title
    document = viz["document"]
    assert isinstance(document, dict)
    assert document["kind"] == "flowchart"
    assert document["engine"] == "mermaid"
    assert document["title"] == title
    assert document["spec"]["source"] == source


async def test_viz_viewer_stream_roundtrip(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    title = f"Stream {unique_id}"
    source = "flowchart TD\n  Start-->Finish"
    file_id = await _upload_viz(
        office_client,
        auth_headers_system,
        unique_id=f"{unique_id}-stream",
        title=title,
        source=source,
    )
    open_response = await office_client.get(
        f"/documents/api/v1/files/{file_id}/editor-config",
        headers=auth_headers_system,
    )
    assert open_response.status_code == 200, open_response.text
    open_body = open_response.json()
    stream_url = parse_viz_stream_url(open_body)
    stream_response = await office_client.get(stream_url)
    assert stream_response.status_code == 200, stream_response.text
    document = parse_viz_document_bytes(stream_response.content)
    assert document.title == title
    assert document.spec.get("source") == source
    assert document.model_dump(mode="json") == open_body["viz"]["document"]


async def test_viz_editor_config_cross_company_forbidden(
    office_client,
    auth_headers_system,
    auth_headers_company2,
    unique_id: str,
) -> None:
    file_id = await _upload_viz(
        office_client,
        auth_headers_system,
        unique_id=f"{unique_id}-xco",
        title=f"Private {unique_id}",
        source="flowchart TD\n  A-->B",
    )
    response = await office_client.get(
        f"/documents/api/v1/files/{file_id}/editor-config",
        headers=auth_headers_company2,
    )
    assert response.status_code == 403
    detail = response.json().get("detail") or ""
    assert "company" in detail.lower()


async def test_viz_invalid_json_editor_config_422(
    office_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    require_s3_configured()
    uploaded = await upload_office_file_bytes(
        office_client,
        auth_headers_system,
        filename=f"broken-{unique_id}.viz",
        content=b"{not-json",
        content_type=VIZ_CONTENT_TYPE,
    )
    file_id = str(uploaded["file_id"])
    response = await office_client.get(
        f"/documents/api/v1/files/{file_id}/editor-config",
        headers=auth_headers_system,
    )
    assert response.status_code == 400, response.text
    detail = response.json().get("detail") or ""
    assert isinstance(detail, str)
    assert "viz document JSON is invalid" in detail
    with pytest.raises(ValueError):
        _ = parse_viz_document_bytes(b"{not-json")
