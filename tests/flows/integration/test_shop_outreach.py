"""shop_outreach bundle: seed-mode → CRM dedupe → render → dry-run/send.

Seed-контент с email обходит search/llm ноды (bootstrap seed_mode) — граф идёт
bootstrap → dedupe_upsert_crm → render_preview → [send_batch] → final_report.

tools.* из code-нод исполняются в процессе тестового flows-сервиса (sandbox →
capability_gateway → POST /flows/api/v1/tool-runtime/call), поэтому MailService
там реальный и строит настоящий ImapSmtpTransport через production-фабрику.
Connection указывает на GreenMail MTA (docker-compose-test): реальный SMTP,
реальная доставка в ящик получателя, реальный TLS-IMAP APPEND в Sent
(MAIL__TLS__EXTRA_CA_FILE в COMMON_TEST_ENV верифицирует цепочку).
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from apps.crm.models.entity_type import EntityType
from apps.flows.src.services.flows_loader import load_flows_to_db
from apps.flows.src.state import ExecutionState
from core.authz.models import AuthzObject
from core.config.models import MailConfig, MailTlsConfig
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
)
from core.mail.service import MailService
from core.types import JsonObject, require_json_object
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.greenmail import (
    GREENMAIL_CA_FILE,
    GREENMAIL_IMAP_HOST,
    GREENMAIL_IMAP_PORT,
    GREENMAIL_MAIL_DOMAIN,
    GREENMAIL_SMTP_HOST,
    GREENMAIL_SMTP_PORT,
    greenmail_ensure_user,
    imap_fetch_raw,
    imap_uids_by_subject,
)
from tests.flows.durable_runtime_harness import run_flow, workflow_state


def _stats(state: ExecutionState) -> JsonObject:
    raw = state.get("run_stats_json")
    assert isinstance(raw, str) and raw.strip(), "run_stats_json не записан"
    return require_json_object(json.loads(raw), "run_stats_json")


def _mail_service(di) -> MailService:
    return MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(
            tls=MailTlsConfig(
                extra_ca_file=str(GREENMAIL_CA_FILE), check_hostname=False
            )
        ),
        files_service=di.files_service,
    )


async def _seed_company_with_mailbox(
    di, *, company_id: str, user_id: str, unique_id: str, local_part: str, password: str
):
    company, user = await seed_mail_company_member(
        di, company_id=company_id, user_id=user_id, unique_id=unique_id
    )
    service = _mail_service(di)
    _ = await service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=GREENMAIL_MAIL_DOMAIN,
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host=GREENMAIL_IMAP_HOST,
            imap_port=GREENMAIL_IMAP_PORT,
            smtp_host=GREENMAIL_SMTP_HOST,
            smtp_port=GREENMAIL_SMTP_PORT,
            use_ssl=False,
        ),
        company_id=company.company_id,
    )
    binding = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user.user_id,
            local_part=local_part,
            password=password,
            provision=False,
            sync_enabled=True,
        ),
        company_id=company.company_id,
    )
    await greenmail_ensure_user(binding.email_address, password)
    _ = await EntityType.create(
        EntityType(
            company_id=company.company_id,
            namespace="default",
            type_id="lead",
            name="Лид",
        )
    )
    deadline = asyncio.get_running_loop().time() + 10.0
    while not await di.authz_service.can_view(
        AuthzObject.company(company.company_id), user_id=user.user_id
    ):
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("authz can_view visibility timeout")
        await asyncio.sleep(0.05)
    return company, user, binding


@pytest_asyncio.fixture()
async def outreach_env(di, unique_id: str):
    """company+user+connection(→GreenMail)+binding 'sales'+seeded bundle."""
    company, user, binding = await _seed_company_with_mailbox(
        di,
        company_id=f"so_{unique_id}",
        user_id=f"so_user_{unique_id}",
        unique_id=unique_id,
        local_part="sales",
        password="test-pass-outreach",
    )
    _ = await load_flows_to_db(
        di.flow_access_service,
        files_service=di.files_service,
    )
    yield binding, company.company_id, user.user_id


@pytest_asyncio.fixture()
async def recipient_mailbox(unique_id: str):
    """Отдельный реальный ящик получателя на GreenMail (чистый INBOX на тест)."""
    email = f"rcpt{unique_id}@{GREENMAIL_MAIL_DOMAIN}"
    password = "rcpt-pass"
    await greenmail_ensure_user(email, password)
    return email, password


@pytest.mark.asyncio
async def test_dry_run_renders_preview_and_creates_crm_entity(
    app, di, outreach_env, mock_llm_with_queue, unique_id: str, recipient_mailbox
) -> None:
    """send_enabled=false: лид попадает в CRM, письмо рендерится, отправки нет."""
    _binding, _company_id, user_id = outreach_env
    rcpt_email, rcpt_password = recipient_mailbox
    mock_llm_with_queue(["Итог: 1 лид, отправка выключена."])
    flow = await di.flow_factory.get_flow(
        "shop_outreach", tool_registry=di.tool_registry
    )
    assert flow is not None
    state = workflow_state(
        flow_id="shop_outreach",
        unique_id=unique_id,
        content="Лид вручную: lead1@restaurant.example",
        user_id=user_id,
        variables={
            "send_enabled": False,
            "test_recipient": rcpt_email,
            "sender_local_part": "sales",
            "sender_display_name": "Platform Sales",
            "crm_namespace": "default",
        },
    )
    result = await run_flow(di=di, flow=flow, state=state)

    stats = _stats(result)
    assert stats["send_enabled"] is False
    assert stats["to_send"] == 1, (
        f"stats={stats} node_errors={result.get('node_errors')} "
        f"leads={result.get('leads')} leads_to_send={result.get('leads_to_send')} "
        f"skipped={result.get('skipped_leads')}"
    )
    assert stats["sent"] == 0
    assert stats["failed"] == 0

    leads_to_send = result.get("leads_to_send")
    assert isinstance(leads_to_send, list) and len(leads_to_send) == 1
    lead = require_json_object(leads_to_send[0], "lead")
    assert lead["email"] == "lead1@restaurant.example"
    entity_id = str(lead.get("entity_id") or "")
    assert entity_id, "CRM entity не создана"

    rendered = result.get("rendered_emails")
    assert isinstance(rendered, list) and len(rendered) == 1
    email_obj = require_json_object(rendered[0], "rendered")
    subject = str(email_obj.get("subject") or "")
    html = str(email_obj.get("body_html") or "")
    assert subject.strip()
    assert "бесплатн" in html.lower(), "HTML должен подчёркивать бесплатность"

    # Реальный канал: в INBOX получателя ничего не упало.
    uids = await imap_uids_by_subject(
        rcpt_email, rcpt_password, folder="INBOX", subject=subject
    )
    assert uids == [], "dry-run не должен доставлять письма"


@pytest.mark.asyncio
async def test_send_batch_sends_via_mail_send_tool(
    app, di, outreach_env, mock_llm_with_queue, unique_id: str, recipient_mailbox
) -> None:
    """send_enabled=true + test_recipient: письмо уходит через реальный MailService
    flows-сервиса → GreenMail SMTP → реальный ящик получателя → APPEND в Sent.
    """
    binding, _company_id, user_id = outreach_env
    rcpt_email, rcpt_password = recipient_mailbox
    mock_llm_with_queue(["Итог: отправлено 1 письмо."])
    flow = await di.flow_factory.get_flow(
        "shop_outreach", tool_registry=di.tool_registry
    )
    assert flow is not None
    state = workflow_state(
        flow_id="shop_outreach",
        unique_id=unique_id,
        content="Лид вручную: vip@cafe.example",
        user_id=user_id,
        variables={
            "send_enabled": True,
            "test_recipient": rcpt_email,
            "sender_local_part": "sales",
            "sender_display_name": "Platform Sales",
            "crm_namespace": "default",
        },
    )
    result = await run_flow(di=di, flow=flow, state=state)

    stats = _stats(result)
    assert stats["send_enabled"] is True
    assert stats["sent"] == 1
    assert stats["failed"] == 0

    send_results = result.get("send_results")
    assert isinstance(send_results, list) and len(send_results) == 1
    record = require_json_object(send_results[0], "send_results[0]")
    assert record["to"] == rcpt_email
    assert record["lead_email"] == "vip@cafe.example"
    assert record["ok"] is True, f"send должен завершиться успехом: {record}"
    assert str(record.get("message_id") or "").strip()

    rendered = result.get("rendered_emails")
    assert isinstance(rendered, list) and rendered
    subject = str(require_json_object(rendered[0], "r").get("subject") or "")

    # Реальная доставка: письмо лежит в INBOX получателя на MTA.
    # Каждый poll — полный IMAPS-коннект, под нагрузкой это секунды.
    deadline = asyncio.get_running_loop().time() + 90.0
    uids: list[bytes] = []
    while not uids:
        uids = await imap_uids_by_subject(
            rcpt_email, rcpt_password, folder="INBOX", subject=subject
        )
        if uids:
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("письмо не дошло до INBOX получателя на MTA")
        await asyncio.sleep(0.5)
    raw = await imap_fetch_raw(
        rcpt_email, rcpt_password, folder="INBOX", subject=subject
    )
    mime = (raw or b"").decode("utf-8", errors="replace")
    assert "Platform Sales" in mime
    assert binding.email_address in mime

    # Отправитель: реальная копия в Sent через TLS-IMAP APPEND.
    sent_uids = await imap_uids_by_subject(
        binding.email_address, "test-pass-outreach", folder="Sent", subject=subject
    )
    assert sent_uids, "Sent-копия не найдена на сервере"


@pytest.mark.asyncio
async def test_cross_tenant_send_denied_over_real_tool_runtime(
    app, di, outreach_env, mock_llm_with_queue, unique_id: str, recipient_mailbox
) -> None:
    """Компания B запускает тот же flow с sender_local_part ящика компании A:
    mail_send в granian-процессе резолвит binding только внутри B → отказ до SMTP.
    """
    _binding_a, _company_a_id, _user_a = outreach_env
    rcpt_email, rcpt_password = recipient_mailbox
    # Компания B: свой ящик 'ops', НО flow просит 'sales' — есть только у A.
    _company_b, user_b, _binding_b = await _seed_company_with_mailbox(
        di,
        company_id=f"soB_{unique_id}",
        user_id=f"soB_user_{unique_id}",
        unique_id=f"{unique_id}b",
        local_part="ops",
        password="test-pass-tenant-b",
    )
    # Bundles сидятся per-company по активному контексту — после seed контекст = B.
    _ = await load_flows_to_db(
        di.flow_access_service,
        files_service=di.files_service,
    )
    mock_llm_with_queue(["Итог: ошибка отправки."])
    flow = await di.flow_factory.get_flow(
        "shop_outreach", tool_registry=di.tool_registry
    )
    assert flow is not None
    state = workflow_state(
        flow_id="shop_outreach",
        unique_id=unique_id,
        content="Лид вручную: victim@cafe.example",
        user_id=user_b.user_id,
        variables={
            "send_enabled": True,
            "test_recipient": rcpt_email,
            "sender_local_part": "sales",
            "sender_display_name": "Platform Sales",
            "crm_namespace": "default",
        },
    )
    result = await run_flow(di=di, flow=flow, state=state)

    stats = _stats(result)
    assert stats["sent"] == 0
    assert stats["failed"] == 1
    send_results = result.get("send_results")
    assert isinstance(send_results, list) and len(send_results) == 1
    record = require_json_object(send_results[0], "send_results[0]")
    assert record["ok"] is False
    # Boundary маскирует MailPermissionError в generic 500 — detail не протекает
    # наружу (не раскрываем, существует ли чужой binding вообще).
    error = str(record.get("error") or "")
    assert error.strip() and "internal server error" in error.lower(), error

    # На MTA ничего не ушло: INBOX получателя пуст по отрендеренному subject.
    rendered = result.get("rendered_emails")
    assert isinstance(rendered, list) and rendered
    subject = str(require_json_object(rendered[0], "r").get("subject") or "")
    assert subject.strip()
    inbox_all = await imap_uids_by_subject(
        rcpt_email, rcpt_password, folder="INBOX", subject=subject
    )
    assert inbox_all == [], "отказ авторизации должен случиться ДО SMTP"
