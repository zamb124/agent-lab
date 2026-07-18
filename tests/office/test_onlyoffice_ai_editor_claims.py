"""OnlyOffice editor JWT: platformAi claims + AI plugin autostart."""

from __future__ import annotations

import pytest

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers.onlyoffice_handler import OnlyOfficeViewerHandler
from core.clients.onlyoffice import verify_onlyoffice_jwt_hs256
from core.files.models import FileRecord
from core.files.types import FileCategory
from core.office.ai_settings import ONLYOFFICE_AI_PLUGIN_GUID
from core.office.platform_ai_claims import (
    OFFICE_AI_JWT_CLAIM_KEY,
    extract_office_platform_ai_claims,
)


def _docx_record() -> FileRecord:
    return FileRecord(
        file_id="file_ai_test",
        provider="minio",
        original_name="note.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=100,
        checksum="deadbeef",
        s3_bucket="b",
        s3_key="k",
        download_url="/files/download/file_ai_test",
        company_id="company_ai",
        uploaded_by="user_ai",
        is_public=False,
    )


def _ctx(*, public_link_token_hash: str | None = None) -> ViewerOpenContext:
    return ViewerOpenContext(
        handler_id="onlyoffice",
        binding_id="binding_ai",
        binding_kind="document",
        file_record=_docx_record(),
        title="note",
        file_category=FileCategory.OFFICE_DOC.value,
        onlyoffice_document_type="word",
        namespace="docs",
        company_id="company_ai",
        user_id="user_ai",
        user_name="AI User",
        editor_lang="ru",
        callback_public_base_url="http://host.docker.internal:8008",
        document_server_public_url="http://localhost:8002",
        jwt_secret="test-onlyoffice-jwt-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url="http://localhost:8002",
        browser_document_server_url="http://localhost:8002",
        link_permission="edit",
        public_link_token_hash=public_link_token_hash,
    )


@pytest.mark.asyncio
async def test_onlyoffice_editor_jwt_includes_platform_ai_and_autostart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.office.services.viewer_handlers.onlyoffice_handler.onlyoffice_editor_customization_payload",
        lambda **_kwargs: {},
    )
    config = await OnlyOfficeViewerHandler().build_open_config(_ctx())
    assert config.onlyoffice is not None
    payload = verify_onlyoffice_jwt_hs256(
        config.onlyoffice.token,
        "test-onlyoffice-jwt-secret",
    )
    claims = extract_office_platform_ai_claims(payload)
    assert claims.company_id == "company_ai"
    assert claims.user_id == "user_ai"
    assert claims.namespace == "docs"
    assert claims.binding_id == "binding_ai"
    assert claims.file_id == "file_ai_test"
    editor_config = payload.get("editorConfig")
    assert isinstance(editor_config, dict)
    plugins = editor_config.get("plugins")
    assert isinstance(plugins, dict)
    assert plugins.get("autostart") == [ONLYOFFICE_AI_PLUGIN_GUID]


@pytest.mark.asyncio
async def test_public_link_editor_skips_platform_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.office.services.viewer_handlers.onlyoffice_handler.onlyoffice_editor_customization_payload",
        lambda **_kwargs: {},
    )
    config = await OnlyOfficeViewerHandler().build_open_config(
        _ctx(public_link_token_hash="hash_public"),
    )
    assert config.onlyoffice is not None
    payload = verify_onlyoffice_jwt_hs256(
        config.onlyoffice.token,
        "test-onlyoffice-jwt-secret",
    )
    assert OFFICE_AI_JWT_CLAIM_KEY not in payload
    editor_config = payload.get("editorConfig")
    assert isinstance(editor_config, dict)
    assert "plugins" not in editor_config
