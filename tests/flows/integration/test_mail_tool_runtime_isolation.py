"""Cross-tenant изоляция почты через РЕАЛЬНЫЙ production-путь.

pytest → POST http://127.0.0.1:9016/capability-gateway/api/v1/capabilities/call
(тот же вход, что у language-sandbox) → verify_execution_context (HMAC) →
POST /flows/api/v1/tool-runtime/call → MailService в granian-процессе
(company-scope → OpenFGA → GreenMail MTA).

В отличие от tests/flows/tools/test_mail_tools.py (прямой вызов сервиса)
здесь проверяется весь wire: подпись execution token, межсервисный HTTP
gateway→flows и маскирование доменной ошибки на boundary.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx2 import AsyncClient

from core.authz.models import AuthzObject
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
)
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.config.models import MailConfig, MailTlsConfig
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
)
from core.mail.service import MailService
from core.models.identity_models import Company, User, UserStatus
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
    smtp_deliver,
)
from tests.fixtures.auth import set_test_company_member_roles
from tests.flows.durable_runtime_harness import workflow_state

GATEWAY_CALL_URL = "http://127.0.0.1:9016/capability-gateway/api/v1/capabilities/call"


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


async def _seed_mailbox(
    di, *, company_id: str, user_id: str, unique_id: str, local_part: str, password: str
) -> MailboxBinding:
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
    return binding


def _execution_context(*, company_id: str, user_id: str) -> CapabilityExecutionContext:
    """Подписанный execution context — то, что flows выдаёт code-runner'у."""
    suffix = uuid.uuid4().hex[:8]
    claims = CapabilityExecutionTokenClaims(
        company_id=company_id,
        user_id=user_id,
        flow_id="security-probe",
        branch_id="default",
        session_id=f"security-probe:{suffix}",
        task_id=f"task-{suffix}",
        context_id=f"context-{suffix}",
        channel="test",
        exp=execution_token_exp(300),
    )
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=company_id,
        user_id=user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
    )


async def _capability_call(
    *,
    context: CapabilityExecutionContext,
    name: str,
    kwargs: JsonObject,
) -> tuple[int, JsonObject]:
    """Реальный HTTP-вызов capability — тот же вход, что у sandbox."""
    state = workflow_state(
        flow_id="security-probe",
        unique_id=uuid.uuid4().hex[:8],
        user_id=context.user_id or "unknown",
    )
    request = CapabilityCallRequest(
        context=context,
        name=name,
        kwargs=kwargs,
        state=require_json_object(state.model_dump(mode="json"), "state"),
    )
    async with AsyncClient(timeout=60.0) as http:
        response = await http.post(
            GATEWAY_CALL_URL,
            content=request.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
    try:
        body = response.json()
    except ValueError:
        return response.status_code, {"raw": response.text[:500]}
    return response.status_code, require_json_object(body, "gateway response")


@pytest_asyncio.fixture()
async def tenant_pair(
    di, unique_id: str
) -> tuple[MailboxBinding, MailboxBinding, str, str]:
    """A: ящик 'sales' (жертва); B: ящик 'ops' (атакующий сотрудник)."""
    binding_a = await _seed_mailbox(
        di,
        company_id=f"isoA_{unique_id}",
        user_id=f"isoA_user_{unique_id}",
        unique_id=unique_id,
        local_part="sales",
        password="pass-iso-a",
    )
    binding_b = await _seed_mailbox(
        di,
        company_id=f"isoB_{unique_id}",
        user_id=f"isoB_user_{unique_id}",
        unique_id=f"{unique_id}b",
        local_part="ops",
        password="pass-iso-b",
    )
    # Контекст после второго сида — компания B; юзер B — тот, кем подписан token.
    company_b_id = f"isoB_{unique_id}"
    user_b_id = f"isoB_user_{unique_id}"
    return binding_a, binding_b, company_b_id, user_b_id


@pytest.mark.asyncio
async def test_read_write_denied_on_foreign_binding_over_gateway(
    app,
    di,
    tenant_pair: tuple[MailboxBinding, MailboxBinding, str, str],
    unique_id: str,
) -> None:
    """B дергает read/write tools по binding'у A — отказ до любого IMAP/SMTP.

    В INBOX A лежит реальное письмо (SMTP-доставка) — защищаемые данные
    физически существуют на MTA, но недостижимы из чужой компании.
    """
    binding_a, binding_b, company_b_id, user_b_id = tenant_pair
    await smtp_deliver(
        to_address=binding_a.email_address,
        from_address="attacker-bait@external.example",
        subject=f"Secret contract {unique_id}",
        body="Тело письма компании A, которое B не должен прочитать.",
    )
    ctx_b = _execution_context(company_id=company_b_id, user_id=user_b_id)

    denied_ops: list[tuple[str, JsonObject]] = [
        ("tools.mail_list_messages", {"mailbox_binding_id": binding_a.mailbox_binding_id}),
        (
            "tools.mail_get_message",
            {"mailbox_binding_id": binding_a.mailbox_binding_id, "uid": "1"},
        ),
        (
            "tools.mail_search_messages",
            {"mailbox_binding_id": binding_a.mailbox_binding_id, "q": "secret"},
        ),
        ("tools.mail_list_folders", {"mailbox_binding_id": binding_a.mailbox_binding_id}),
        ("tools.mail_sync_now", {"mailbox_binding_id": binding_a.mailbox_binding_id}),
        (
            "tools.mail_save_draft",
            {
                "mailbox_binding_id": binding_a.mailbox_binding_id,
                "to_addresses": ["victim@example.com"],
                "subject": "x",
                "body_text": "x",
            },
        ),
        (
            "tools.mail_send",
            {
                "mailbox_binding_id": binding_a.mailbox_binding_id,
                "to_addresses": ["victim@example.com"],
                "subject": "x",
                "body_text": "x",
            },
        ),
    ]
    for name, kwargs in denied_ops:
        status_code, _body = await _capability_call(
            context=ctx_b, name=name, kwargs=kwargs
        )
        assert status_code >= 400, (
            f"{name} по чужому binding вернул {status_code}: {_body}"
        )

    # Позитивный контроль: тот же путь со СВОИМ binding — работает.
    status_code, body = await _capability_call(
        context=ctx_b,
        name="tools.mail_list_messages",
        kwargs={"mailbox_binding_id": binding_b.mailbox_binding_id},
    )
    assert status_code == 200, body
    assert body.get("status") == "ok", body


@pytest.mark.asyncio
async def test_list_bindings_does_not_leak_foreign_mailbox_over_gateway(
    app, di, tenant_pair: tuple[MailboxBinding, MailboxBinding, str, str]
) -> None:
    """list_bindings в контексте B возвращает только ящики B — A невидим."""
    binding_a, binding_b, company_b_id, user_b_id = tenant_pair
    ctx_b = _execution_context(company_id=company_b_id, user_id=user_b_id)

    status_code, body = await _capability_call(
        context=ctx_b, name="tools.mail_list_bindings", kwargs={}
    )
    assert status_code == 200, body
    assert body.get("status") == "ok", body
    result = require_json_object(body.get("result"), "list_bindings result")
    items = result.get("items")
    assert isinstance(items, list)
    ids = [require_json_object(i, "binding").get("mailbox_binding_id") for i in items]
    assert binding_b.mailbox_binding_id in ids
    assert binding_a.mailbox_binding_id not in ids


@pytest.mark.asyncio
async def test_forged_execution_context_rejected_over_gateway(
    app, di, tenant_pair: tuple[MailboxBinding, MailboxBinding, str, str]
) -> None:
    """Подпись — первый гейт: контекст с mismatch claims/context отвергается
    ещё до вызова tool (ни company-scope, ни FGA не достигаются)."""
    binding_a, _binding_b, company_b_id, user_b_id = tenant_pair
    ctx_b = _execution_context(company_id=company_b_id, user_id=user_b_id)
    # Подмена: claims подписаны под B, но context утверждает company_id другой.
    forged = ctx_b.model_copy(update={"company_id": "victim-company"})

    status_code, body = await _capability_call(
        context=forged,
        name="tools.mail_list_messages",
        kwargs={"mailbox_binding_id": binding_a.mailbox_binding_id},
    )
    assert status_code >= 400, body


@pytest_asyncio.fixture()
async def same_company_pair(
    di, unique_id: str
) -> tuple[MailboxBinding, MailboxBinding, str, str]:
    """Компания C: userA (admin, personal 'boss') + userM (member, свой 'worker')."""
    company_id = f"isoC_{unique_id}"
    user_a_id = f"isoC_userA_{unique_id}"
    user_m_id = f"isoC_userM_{unique_id}"
    company, user_a = await seed_mail_company_member(
        di, company_id=company_id, user_id=user_a_id, unique_id=unique_id
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
    binding_a = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_a.user_id,
            local_part="boss",
            password="pass-iso-boss",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company.company_id,
    )
    await greenmail_ensure_user(binding_a.email_address, "pass-iso-boss")

    # Обычный member той же компании (роль member, без admin/owner).
    user_m = User(
        user_id=user_m_id,
        name=f"Mail Member {unique_id}",
        status=UserStatus.ACTIVE,
        emails=[f"{user_m_id}@mail.test"],
        companies={company.company_id: ["member"]},
        active_company_id=company.company_id,
    )
    await User.set(user_m)
    company.members[user_m.user_id] = ["member"]
    _ = await Company.set(company)
    await set_test_company_member_roles(
        di.authz_service,
        company_id=company.company_id,
        user_id=user_m.user_id,
        roles=["member"],
    )
    # Свой ящик member'а — admin создаёт привязку для коллеги.
    binding_m = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_m.user_id,
            local_part="worker",
            password="pass-iso-worker",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company.company_id,
    )
    await greenmail_ensure_user(binding_m.email_address, "pass-iso-worker")
    # member проходит tool-gate (can_view company) — ждём visibility в OpenFGA.
    deadline = asyncio.get_running_loop().time() + 10.0
    while not await di.authz_service.can_view(
        AuthzObject.company(company.company_id), user_id=user_m.user_id
    ):
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("authz can_view visibility timeout")
        await asyncio.sleep(0.05)
    return binding_a, binding_m, company.company_id, user_m.user_id


@pytest.mark.asyncio
async def test_same_company_member_denied_on_colleague_mailbox_over_gateway(
    app,
    di,
    same_company_pair: tuple[MailboxBinding, MailboxBinding, str, str],
    unique_id: str,
) -> None:
    """Member той же компании не читает personal-ящик коллеги — FGA can_view
    внутри MailService в granian-процессе, отказ по реальному HTTP-пути."""
    binding_a, binding_m, company_id, user_m_id = same_company_pair
    await smtp_deliver(
        to_address=binding_a.email_address,
        from_address="client@external.example",
        subject=f"Private HR {unique_id}",
        body="Личная переписка сотрудника A.",
    )
    ctx_m = _execution_context(company_id=company_id, user_id=user_m_id)

    denied_ops: list[tuple[str, JsonObject]] = [
        ("tools.mail_list_messages", {"mailbox_binding_id": binding_a.mailbox_binding_id}),
        (
            "tools.mail_get_message",
            {"mailbox_binding_id": binding_a.mailbox_binding_id, "uid": "1"},
        ),
        ("tools.mail_list_folders", {"mailbox_binding_id": binding_a.mailbox_binding_id}),
        (
            "tools.mail_send",
            {
                "mailbox_binding_id": binding_a.mailbox_binding_id,
                "to_addresses": ["victim@example.com"],
                "subject": "x",
                "body_text": "x",
            },
        ),
    ]
    for name, kwargs in denied_ops:
        status_code, body = await _capability_call(
            context=ctx_m, name=name, kwargs=kwargs
        )
        assert status_code >= 400, (
            f"{name} по личному ящику коллеги вернул {status_code}: {body}"
        )

    # Свой ящик member'а — валидный ответ по тому же пути.
    status_code, body = await _capability_call(
        context=ctx_m,
        name="tools.mail_list_messages",
        kwargs={"mailbox_binding_id": binding_m.mailbox_binding_id},
    )
    assert status_code == 200, body
    assert body.get("status") == "ok", body
