"""Offline: IMAP IDLE wake → enqueue sync; supervisor gates."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest

from apps.idle.tasks.mail_idle_supervisor import (
    _idle_one_binding,
    mail_idle_supervisor_task,
)
from core.config.models import MailSyncConfig
from core.mail.models import MailIdleWake, MailIdleWakeKind
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import seed_connected_user_binding
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]


@pytest.mark.asyncio
async def test_idle_exists_enqueues_sync(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="idleex",
    )
    recording_mail_port.idle_wake = MailIdleWake(kind=MailIdleWakeKind.EXISTS)
    enqueued: list[tuple[str, str]] = []

    async def _fake_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    monkeypatch.setattr(
        "apps.idle.tasks.mail_idle_supervisor.enqueue_mail_sync_binding",
        _fake_enqueue,
    )
    woke = await _idle_one_binding(
        mail_service=mail_service,
        binding=binding,
        timeout_seconds=1.0,
    )
    assert woke is True
    assert enqueued == [(binding.company_id, binding.mailbox_binding_id)]


@pytest.mark.asyncio
async def test_idle_timeout_does_not_enqueue(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context: MailMemberSeed,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _company_id, _user_id, binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="idletm",
    )
    recording_mail_port.idle_wake = MailIdleWake(kind=MailIdleWakeKind.TIMEOUT)
    enqueued: list[tuple[str, str]] = []

    async def _fake_enqueue(*, company_id: str, mailbox_binding_id: str) -> None:
        enqueued.append((company_id, mailbox_binding_id))

    monkeypatch.setattr(
        "apps.idle.tasks.mail_idle_supervisor.enqueue_mail_sync_binding",
        _fake_enqueue,
    )
    woke = await _idle_one_binding(
        mail_service=mail_service,
        binding=binding,
        timeout_seconds=1.0,
    )
    assert woke is False
    assert enqueued == []


@pytest.mark.asyncio
async def test_idle_supervisor_respects_idle_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.idle.tasks.mail_idle_supervisor.get_settings",
        lambda: SimpleNamespace(
            mail_sync=MailSyncConfig(enabled=True, idle_enabled=False)
        ),
    )
    result = await mail_idle_supervisor_task(di=SimpleNamespace())
    assert result == {"idle_sessions": 0, "wakes": 0}
