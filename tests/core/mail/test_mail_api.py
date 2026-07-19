"""HTTP API почты через frontend_client."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.ai.company_settings import encrypt_secret
from core.config import get_settings
from core.mail.models import (
    CompanyMailConnection,
    IspmanagerProvisionConfig,
    MailConnectionStatus,
    MailProvider,
)
from core.mail.repositories import CompanyMailConnectionRepository


@pytest.mark.asyncio
async def test_mail_connection_get_and_bindings_list(
    frontend_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен")
    repo = CompanyMailConnectionRepository(db_url=shared_url)
    now = datetime.now(timezone.utc)
    _ = await repo.upsert(
        CompanyMailConnection(
            company_mail_connection_id=f"mailconn_api_{unique_id}",
            company_id="system",
            mail_domain="linnex.io",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            supports_provision=True,
            status=MailConnectionStatus.ACTIVE,
            ispmanager=IspmanagerProvisionConfig(
                base_url="https://panel.example.com/ispmgr",
                authinfo_user="admin",
                authinfo_password_encrypted=encrypt_secret(f"pass-{unique_id}"),
            ),
            created_at=now,
            updated_at=now,
        )
    )

    loaded = await repo.get_by_company("system")
    assert loaded is not None
    assert loaded.mail_domain == "linnex.io"

    get_response = await frontend_client.get(
        "/frontend/api/mail/connection",
        headers=auth_headers_system,
    )
    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["company_id"] == "system"
    assert body["mail_domain"] == "linnex.io"
    assert body["has_ispmanager_auth"] is True
    assert "authinfo_password" not in body

    put_response = await frontend_client.put(
        "/frontend/api/mail/connection",
        headers=auth_headers_system,
        json={
            "mail_domain": "linnex.io",
            "provider": "generic_imap_smtp",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
        },
    )
    assert put_response.status_code == 403

    list_response = await frontend_client.get(
        "/frontend/api/mail/bindings",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    assert "items" in list_response.json()

    missing_delete = await frontend_client.delete(
        f"/frontend/api/mail/bindings/mailbind_missing_{unique_id}",
        headers=auth_headers_system,
    )
    assert missing_delete.status_code == 404
