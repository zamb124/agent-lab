"""Async mail RAG index: persist enqueues; index_mail_message ready/failed."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailMessageRagIndexPayload,
    MailProvider,
    MailRagIndexStatus,
)
from core.mail.repositories import MailMessageRepository
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_persist_sets_pending_and_enqueues_rag_index(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_message_repository: MailMessageRepository,
    mail_member_context: MailMemberSeed,
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    enqueued: list[dict[str, str]] = []

    async def _capture_enqueue(**kwargs: str) -> None:
        enqueued.append(dict(kwargs))

    monkeypatch.setattr("core.mail.service.enqueue_mail_rag_index", _capture_enqueue)

    class _StubRag:
        async def ingest_text(self, **_kwargs: Any) -> Any:
            raise AssertionError("persist must not call ingest_text synchronously")

    object.__setattr__(mail_service, "_rag_client", _StubRag())

    company_id = f"mailragp_{unique_id}"
    user_id = f"urag_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.ragp.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"r{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 3
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="31",
            subject="Index me",
            from_address="a@example.com",
            body_text="body for rag",
        ),
    ]
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)
    stored = await mail_message_repository.get_by_uid(
        binding.mailbox_binding_id, folder="INBOX", uid=31
    )
    assert stored is not None
    assert stored.rag_index_status == MailRagIndexStatus.PENDING
    assert stored.rag_document_id is None
    assert len(enqueued) == 1
    assert enqueued[0]["mailbox_binding_id"] == binding.mailbox_binding_id
    assert enqueued[0]["uid"] == "31"


@pytest.mark.asyncio
async def test_index_mail_message_ready_and_failed(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_message_repository: MailMessageRepository,
    mail_member_context: MailMemberSeed,
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    async def _noop_enqueue(**_kwargs: str) -> None:
        return None

    monkeypatch.setattr("core.mail.service.enqueue_mail_rag_index", _noop_enqueue)

    class _FakeIngest:
        document_id = "doc_mail_rag_1"

    class _OkRag:
        async def ingest_text(self, **_kwargs: Any) -> _FakeIngest:
            return _FakeIngest()

    class _FailRag:
        async def ingest_text(self, **_kwargs: Any) -> _FakeIngest:
            raise RuntimeError("rag down")

    class _StubRag:
        async def ingest_text(self, **_kwargs: Any) -> Any:
            raise AssertionError("persist must not call ingest_text synchronously")

    object.__setattr__(mail_service, "_rag_client", _StubRag())

    company_id = f"mailragx_{unique_id}"
    user_id = f"uxrag_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.ragx.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"x{unique_id[:8]}",
            password="test-pass-1",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.uidvalidity = 9
    recording_mail_port.inbox = [
        InboundMailMessage(
            uid="41",
            subject="Ready",
            from_address="a@example.com",
            body_text="ready body",
        ),
        InboundMailMessage(
            uid="42",
            subject="Fail",
            from_address="b@example.com",
            body_text="fail body",
        ),
    ]
    _ = await mail_service.sync_user_inbox(binding, max_new_messages=20)

    object.__setattr__(mail_service, "_rag_client", _OkRag())
    ready = await mail_service.index_mail_message(
        mailbox_binding_id=binding.mailbox_binding_id,
        folder="INBOX",
        uid="41",
        company_id=company_id,
    )
    assert ready.rag_index_status == MailRagIndexStatus.READY
    assert ready.rag_document_id == "doc_mail_rag_1"

    object.__setattr__(mail_service, "_rag_client", _FailRag())
    with pytest.raises(RuntimeError, match="rag down"):
        _ = await mail_service.index_mail_message(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="42",
            company_id=company_id,
        )
    failed = await mail_message_repository.get_by_uid(
        binding.mailbox_binding_id, folder="INBOX", uid=42
    )
    assert failed is not None
    assert failed.rag_index_status == MailRagIndexStatus.FAILED
    assert failed.subject == "Fail"

    retry = await mail_service.request_rag_index(
        MailMessageRagIndexPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            uid="42",
        ),
        company_id=company_id,
    )
    assert retry.rag_index_status == MailRagIndexStatus.PENDING
