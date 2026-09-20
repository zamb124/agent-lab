"""Email trigger inbound: Redis index, dispatch→completed, filter, sync+dispatch.

Без unittest.mock/monkeypatch. MockLLM only. Mail IMAP — RecordingMailServerPort через DI.
Company `system` mail connection read-only — отдельная company на тест.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from apps.flows.src.models import FlowConfig
from apps.flows.src.triggers.email_filter import (
    email_trigger_index_key,
    email_trigger_index_member,
)
from apps.flows.src.triggers.handlers.email import (
    dispatch_email_triggers_for_messages,
    email_trigger_run_id,
)
from core.config.models import MailConfig
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
)
from core.mail.service import MailService
from core.types import require_json_object
from core.utils.tokens import get_token_service
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort
from tests.fixtures.ai_provider_defaults import company_with_test_ai_provider_defaults
from tests.flows.conftest import persist_owned_flow


async def _await_completed_state(container, session_id: str, *, timeout_sec: float = 20.0):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_state = None
    while asyncio.get_running_loop().time() < deadline:
        last_state = await container.workflow_runtime.get_state(session_id)
        if last_state is not None and last_state.terminal_task_state == "completed":
            return last_state
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"session {session_id!r} not completed in {timeout_sec}s; "
        f"terminal={getattr(last_state, 'terminal_task_state', None)!r}"
    )


def _mail_service_with_port(container, port: RecordingMailServerPort) -> MailService:
    return MailService(
        connection_repository=container.company_mail_connection_repository,
        binding_repository=container.mailbox_binding_repository,
        sync_cursor_repository=container.mailbox_sync_cursor_repository,
        folder_repository=container.mailbox_folder_repository,
        message_repository=container.mail_message_repository,
        authz=container.authz_service,
        namespace_service=container.namespace_service,
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        mail_config=MailConfig(),
        port_override=port,
    )


async def _seed_company_binding(
    *,
    container,
    mail_service: MailService,
    unique_id: str,
    prefix: str,
):
    company_id = f"{prefix}_{unique_id}"
    user_id = f"user_{unique_id}"
    company, user = await seed_mail_company_member(
        container,
        company_id=company_id,
        user_id=user_id,
        unique_id=unique_id,
    )
    company = company_with_test_ai_provider_defaults(company)
    await container.company_repository.set(company)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
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
            local_part=f"et{unique_id[:8]}",
            password="test-pass-email-trigger",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    token = get_token_service().create_token(
        user_id,
        company_id=company_id,
        roles=["owner", "admin"],
    )
    return company, user, binding, token


@pytest.mark.asyncio
async def test_create_email_trigger_indexes_redis(
    app, container, unique_id: str
) -> None:
    """API create email trigger → SADD flows:email_triggers:{mailbox_binding_id}."""
    port = RecordingMailServerPort(supports_provision=False)
    mail_service = _mail_service_with_port(container, port)
    company, user, binding, token = await _seed_company_binding(
        container=container,
        mail_service=mail_service,
        unique_id=unique_id,
        prefix="emidx",
    )

    flow_id = f"em_idx_{unique_id}"
    trigger_id = "on_mail"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Email Index",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await persist_owned_flow(
        container,
        agent,
        company_id=company.company_id,
        owner_user_id=user.user_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        created = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": trigger_id,
                "name": "Inbox",
                "type": "email",
                "enabled": True,
                "config": {"mailbox_binding_id": binding.mailbox_binding_id},
                "output_mapping": {"content": "subject"},
            },
        )
    assert created.status_code == 200, created.text
    body = require_json_object(created.json(), "create email trigger")
    assert body["status"] == "active"

    member = email_trigger_index_member(
        company_id=company.company_id, flow_id=flow_id, trigger_id=trigger_id
    )
    indexed = await container.redis_client.smembers(
        email_trigger_index_key(binding.mailbox_binding_id)
    )
    assert member in indexed

    _ = await container.redis_client.srem(
        email_trigger_index_key(binding.mailbox_binding_id), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_dispatch_match_fires_completed_and_dedups(
    app, container, unique_id: str, mock_llm_with_queue
) -> None:
    """dispatch → completed; повтор того же uid → fired==0."""
    mock_llm_with_queue(["Email processed"])
    port = RecordingMailServerPort(supports_provision=False)
    mail_service = _mail_service_with_port(container, port)
    company, user, binding, token = await _seed_company_binding(
        container=container,
        mail_service=mail_service,
        unique_id=unique_id,
        prefix="emfire",
    )

    flow_id = f"em_fire_{unique_id}"
    trigger_id = "on_mail"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Email Fire",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await persist_owned_flow(
        container,
        agent,
        company_id=company.company_id,
        owner_user_id=user.user_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        created = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": trigger_id,
                "name": "Inbox",
                "type": "email",
                "enabled": True,
                "config": {"mailbox_binding_id": binding.mailbox_binding_id},
                "output_mapping": {"content": "subject"},
            },
        )
    assert created.status_code == 200, created.text

    message = InboundMailMessage(
        uid="42",
        message_id=f"<fire-{unique_id}@example.com>",
        subject="Hello email trigger",
        from_address="sender@example.com",
        body_text="body",
    )
    fired = await dispatch_email_triggers_for_messages(
        container=container,
        binding=binding,
        messages=[message],
        dedup_ttl_seconds=3600,
    )
    assert fired == 1

    run_id = email_trigger_run_id(
        mailbox_binding_id=binding.mailbox_binding_id,
        flow_id=flow_id,
        trigger_id=trigger_id,
        mail_uid=message.uid,
    )
    session_id = f"{flow_id}:{run_id}"
    state = await _await_completed_state(container, session_id)
    assert state.content == "Hello email trigger"
    assert state.response == "Email processed"

    fired_again = await dispatch_email_triggers_for_messages(
        container=container,
        binding=binding,
        messages=[message],
        dedup_ttl_seconds=3600,
    )
    assert fired_again == 0

    member = email_trigger_index_member(
        company_id=company.company_id, flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        email_trigger_index_key(binding.mailbox_binding_id), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_dispatch_filter_mismatch_no_state(
    app, container, unique_id: str, mock_llm_with_queue
) -> None:
    """allowed_senders filter miss → fired==0, state отсутствует."""
    mock_llm_with_queue(["should not run"])
    port = RecordingMailServerPort(supports_provision=False)
    mail_service = _mail_service_with_port(container, port)
    company, user, binding, token = await _seed_company_binding(
        container=container,
        mail_service=mail_service,
        unique_id=unique_id,
        prefix="emfilt",
    )

    flow_id = f"em_filt_{unique_id}"
    trigger_id = "on_mail"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Email Filter",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await persist_owned_flow(
        container,
        agent,
        company_id=company.company_id,
        owner_user_id=user.user_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        created = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": trigger_id,
                "name": "Inbox",
                "type": "email",
                "enabled": True,
                "config": {
                    "mailbox_binding_id": binding.mailbox_binding_id,
                    "allowed_senders": ["allowed@example.com"],
                },
                "output_mapping": {"content": "subject"},
            },
        )
    assert created.status_code == 200, created.text

    message = InboundMailMessage(
        uid="99",
        message_id=f"<miss-{unique_id}@example.com>",
        subject="Blocked",
        from_address="other@example.com",
        body_text="x",
    )
    fired = await dispatch_email_triggers_for_messages(
        container=container,
        binding=binding,
        messages=[message],
        dedup_ttl_seconds=3600,
    )
    assert fired == 0
    run_id = email_trigger_run_id(
        mailbox_binding_id=binding.mailbox_binding_id,
        flow_id=flow_id,
        trigger_id=trigger_id,
        mail_uid=message.uid,
    )
    state = await container.workflow_runtime.get_state(f"{flow_id}:{run_id}")
    assert state is None

    member = email_trigger_index_member(
        company_id=company.company_id, flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        email_trigger_index_key(binding.mailbox_binding_id), member
    )
    await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_sync_binding_new_mail_dispatches(
    app, container, unique_id: str, mock_llm_with_queue
) -> None:
    """RecordingMailServerPort incremental UID → sync_binding → dispatch → completed."""
    mock_llm_with_queue(["Synced mail ok"])
    port = RecordingMailServerPort(supports_provision=False)
    mail_service = _mail_service_with_port(container, port)
    company, user, binding, token = await _seed_company_binding(
        container=container,
        mail_service=mail_service,
        unique_id=unique_id,
        prefix="emsync",
    )

    flow_id = f"em_sync_{unique_id}"
    trigger_id = "on_mail"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Email Sync",
        entry="main",
        nodes={"main": {"type": "llm_node", "prompt": "Echo: {content}"}},
    )
    await persist_owned_flow(
        container,
        agent,
        company_id=company.company_id,
        owner_user_id=user.user_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        created = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": trigger_id,
                "name": "Inbox",
                "type": "email",
                "enabled": True,
                "config": {"mailbox_binding_id": binding.mailbox_binding_id},
                "output_mapping": {"content": "subject"},
            },
        )
    assert created.status_code == 200, created.text

    port.uidvalidity = 7
    port.inbox = [
        InboundMailMessage(
            uid="1",
            message_id=f"<boot-{unique_id}@example.com>",
            subject="Bootstrap",
            from_address="a@example.com",
            body_text="old",
        )
    ]
    bootstrap = await mail_service.sync_binding(binding, max_new_messages=20)
    assert bootstrap.bootstrap is True

    port.inbox.append(
        InboundMailMessage(
            uid="2",
            message_id=f"<new-{unique_id}@example.com>",
            subject="New after sync",
            from_address="b@example.com",
            body_text="fresh",
        )
    )
    incremental = await mail_service.sync_binding(binding, max_new_messages=20)
    assert incremental.bootstrap is False
    assert len(incremental.new_messages) >= 1

    fired = await dispatch_email_triggers_for_messages(
        container=container,
        binding=binding,
        messages=incremental.new_messages,
        dedup_ttl_seconds=3600,
    )
    assert fired == 1

    new_msg = incremental.new_messages[-1]
    run_id = email_trigger_run_id(
        mailbox_binding_id=binding.mailbox_binding_id,
        flow_id=flow_id,
        trigger_id=trigger_id,
        mail_uid=new_msg.uid,
    )
    state = await _await_completed_state(container, f"{flow_id}:{run_id}")
    assert state.content == "New after sync"
    assert state.response == "Synced mail ok"

    member = email_trigger_index_member(
        company_id=company.company_id, flow_id=flow_id, trigger_id=trigger_id
    )
    _ = await container.redis_client.srem(
        email_trigger_index_key(binding.mailbox_binding_id), member
    )
    await container.flow_repository.delete(flow_id)
