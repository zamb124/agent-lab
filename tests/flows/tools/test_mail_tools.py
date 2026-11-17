"""Тесты builtin mail tools: метаданные, резолюция отправителя, запись через MailClient.

MailServerPort — RecordingMailServerPort через DI (port_override), без mock.
Отправка и чтение идут через реальный MailService с тестовой компанией.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.tools.mail.mail_tools import (
    mail_add_member,
    mail_connect_personal,
    mail_create_mailbox,
    mail_get_message,
    mail_get_thread,
    mail_healthcheck_binding,
    mail_list_bindings,
    mail_list_folders,
    mail_list_members,
    mail_list_messages,
    mail_move_message,
    mail_patch_binding,
    mail_remove_member,
    mail_save_draft,
    mail_search_messages,
    mail_send,
    mail_set_default_binding,
    mail_set_flags,
    mail_sync_now,
)
from core.authz.models import AuthzObject
from core.clients.mail_client import MailClient
from core.config.models import MailConfig
from core.context import set_context
from core.mail.exceptions import MailBindingNotFoundError, MailPermissionError
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    InboundMailMessage,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
)
from core.mail.service import MailService
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus
from core.types import JsonObject, require_json_array, require_json_object
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.fakes import RecordingMailServerPort
from tests.fixtures.auth import set_test_company_member_roles


def _as_object(raw: object, label: str) -> JsonObject:
    return require_json_object(raw, label)


def test_mail_tools_metadata() -> None:
    for tool in (
        mail_list_bindings,
        mail_create_mailbox,
        mail_connect_personal,
        mail_healthcheck_binding,
        mail_list_folders,
        mail_get_message,
        mail_save_draft,
        mail_send,
        mail_set_flags,
    ):
        assert "mail" in tool.tags, tool.name
        props = require_json_object(
            tool.parameters.get("properties", {}), f"{tool.name}.properties"
        )
        assert props is not None
    send_props = require_json_object(
        mail_send.parameters.get("properties", {}), "mail_send.properties"
    )
    for field in ("mailbox_binding_id", "from_local_part", "sender_display_name", "body_html"):
        assert field in send_props


def _state(unique_id: str, user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"mail-tool-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id=user_id,
        session_id=f"mail:ctx-{unique_id}",
    )


@pytest_asyncio.fixture()
async def mail_env(di, unique_id: str):
    """Компания + user + GENERIC connection + user binding 'sales'."""
    company_id = f"mt_{unique_id}"
    user_id = f"mt_user_{unique_id}"
    company, user = await seed_mail_company_member(
        di, company_id=company_id, user_id=user_id, unique_id=unique_id
    )
    port = RecordingMailServerPort(supports_provision=False)
    service = MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(),
        port_override=port,
        files_service=di.files_service,
    )
    _ = await service.upsert_connection(
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
    binding = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part="sales",
            password="test-pass-mail-tools",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_id,
    )
    # OpenFGA lag: ждём can_view прежде чем tool.run сделает company-check
    deadline = asyncio.get_running_loop().time() + 10.0
    while not await di.authz_service.can_view(AuthzObject.company(company_id), user_id=user_id):
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("authz can_view visibility timeout")
        await asyncio.sleep(0.05)
    client = MailClient(service)
    yield client, port, binding, company.company_id, user.user_id, service


@pytest.mark.asyncio
async def test_mail_list_bindings_returns_accessible(mail_env, unique_id: str) -> None:
    client, _port, binding, _cid, uid, _svc = mail_env
    bound = mail_list_bindings.with_dependencies([client])
    out = _as_object(await bound.run({}, _state(unique_id, uid)), "list_bindings")
    items = require_json_array(out.get("items"), "list_bindings.items")
    found = [
        _as_object(i, "item")
        for i in items
        if _as_object(i, "item").get("mailbox_binding_id") == binding.mailbox_binding_id
    ]
    assert len(found) == 1
    for item in (_as_object(i, "item") for i in items):
        assert "password" not in item and "password_encrypted" not in item


@pytest.mark.asyncio
async def test_mail_send_records_message_and_html(mail_env, unique_id: str) -> None:
    client, port, binding, _cid, uid, svc = mail_env
    bound = mail_send.with_dependencies([client])
    out = _as_object(
        await bound.run(
            {
                "mailbox_binding_id": binding.mailbox_binding_id,
                "to_addresses": ["lead@example.com"],
                "subject": "Offer",
                "body_text": "Hello",
                "body_html": "<h1>Hello</h1>",
                "sender_display_name": "Sales Team",
            },
            _state(unique_id, uid),
        ),
        "mail_send.result",
    )
    assert out["mailbox_binding_id"] == binding.mailbox_binding_id
    assert require_json_array(out.get("accepted"), "accepted") == ["lead@example.com"]
    assert len(port.sent) == 1
    sender, message = port.sent[0]
    assert sender == binding.email_address
    assert message.from_address is not None and "Sales Team" in message.from_address
    assert port.last_sent_body_html == "<h1>Hello</h1>"


@pytest.mark.asyncio
async def test_mail_send_resolves_local_part(mail_env, unique_id: str) -> None:
    client, port, binding, _cid, uid, svc = mail_env
    bound = mail_send.with_dependencies([client])
    out = _as_object(
        await bound.run(
            {
                "from_local_part": "sales",
                "to_addresses": ["x@example.com"],
                "subject": "S",
                "body_text": "B",
            },
            _state(unique_id, uid),
        ),
        "mail_send.local_part",
    )
    assert out["mailbox_binding_id"] == binding.mailbox_binding_id
    assert port.sent[0][0] == binding.email_address


@pytest.mark.asyncio
async def test_mail_send_denies_unknown_binding(mail_env, unique_id: str) -> None:
    client, _port, _binding, _cid, uid, _svc = mail_env
    bound = mail_send.with_dependencies([client])
    with pytest.raises(MailPermissionError):
        await bound.run(
            {
                "mailbox_binding_id": "nonexistent-binding",
                "to_addresses": ["x@example.com"],
                "subject": "S",
                "body_text": "B",
            },
            _state(unique_id, uid),
        )


@pytest.mark.asyncio
async def test_mail_send_rejects_too_many_recipients(mail_env, unique_id: str) -> None:
    client, _port, binding, _cid, uid, _svc = mail_env
    bound = mail_send.with_dependencies([client])
    with pytest.raises(Exception, match="to_addresses"):
        await bound.run(
            {
                "mailbox_binding_id": binding.mailbox_binding_id,
                "to_addresses": [f"u{i}@example.com" for i in range(6)],
                "subject": "S",
                "body_text": "B",
            },
            _state(unique_id, uid),
        )


@pytest.mark.asyncio
async def test_mail_list_folders(mail_env, unique_id: str) -> None:
    """Folders — local-first: до sync пусто+needs_sync, после sync — INBOX."""
    client, _port, binding, _cid, uid, svc = mail_env
    out = _as_object(
        await mail_list_folders.with_dependencies([client]).run(
            {"mailbox_binding_id": binding.mailbox_binding_id}, _state(unique_id, uid)
        ),
        "list_folders.unsynced",
    )
    assert require_json_array(out.get("folders"), "folders") == []
    assert out.get("needs_sync") is True
    _ = await svc.sync_binding(binding, max_new_messages=20)
    bound = mail_list_folders.with_dependencies([client])
    out = _as_object(
        await bound.run({"mailbox_binding_id": binding.mailbox_binding_id}, _state(unique_id, uid)),
        "list_folders",
    )
    names = [
        str(_as_object(f, "folder").get("name") or "")
        for f in require_json_array(out.get("folders"), "folders")
    ]
    assert "INBOX" in names


@pytest.mark.asyncio
async def test_mail_get_and_flag_message(mail_env, unique_id: str) -> None:
    client, port, binding, _cid, uid, svc = mail_env
    port.inbox.append(
        InboundMailMessage(
            uid="11",
            message_id="m-11@x",
            subject="Lead reply",
            from_address="lead@example.com",
            to_addresses=[binding.email_address],
            body_text="interested",
        )
    )
    # get/set_flags — local-first по StoredMailMessage: реальный sync наполняет стор
    _ = await svc.sync_binding(binding, max_new_messages=20)
    msg = _as_object(
        await mail_get_message.with_dependencies([client]).run(
            {
                "mailbox_binding_id": binding.mailbox_binding_id,
                "uid": "11",
                "folder": "INBOX",
            },
            _state(unique_id, uid),
        ),
        "get_message",
    )
    assert msg["uid"] == "11"
    _ = await mail_set_flags.with_dependencies([client]).run(
        {
            "mailbox_binding_id": binding.mailbox_binding_id,
            "uid": "11",
            "folder": "INBOX",
            "seen": True,
        },
        _state(unique_id, uid),
    )
    assert port.mark_seen_calls and port.mark_seen_calls[-1][2] == "11"


@pytest.mark.asyncio
async def test_mail_save_draft(mail_env, unique_id: str) -> None:
    client, port, binding, _cid, uid, svc = mail_env
    out = _as_object(
        await mail_save_draft.with_dependencies([client]).run(
            {
                "mailbox_binding_id": binding.mailbox_binding_id,
                "to_addresses": ["a@example.com"],
                "subject": "Draft subj",
                "body_text": "draft body",
            },
            _state(unique_id, uid),
        ),
        "save_draft",
    )
    assert out.get("uid")
    assert port.append_message_calls


@pytest.mark.asyncio
async def test_mail_healthcheck_binding(mail_env, unique_id: str) -> None:
    """healthcheck доступен только для personal-scope binding."""
    client, _port, _binding, _cid, uid, _svc = mail_env
    personal = _as_object(
        await mail_connect_personal.with_dependencies([client]).run(
            {
                "email_address": f"hc_{unique_id}@ext.test",
                "password": "ext-pass",
                "imap_host": "imap.ext.test",
                "imap_port": 993,
                "smtp_host": "smtp.ext.test",
                "smtp_port": 465,
                "use_ssl": True,
            },
            _state(unique_id, uid),
        ),
        "connect_personal",
    )
    out = _as_object(
        await mail_healthcheck_binding.with_dependencies([client]).run(
            {"mailbox_binding_id": personal["mailbox_binding_id"]},
            _state(unique_id, uid),
        ),
        "healthcheck",
    )
    assert out["imap_ok"] is True and out["smtp_ok"] is True


@pytest.mark.asyncio
async def test_mail_connect_personal_creates_binding(mail_env, unique_id: str) -> None:
    client, port, _binding, _cid, uid, _svc = mail_env
    out = _as_object(
        await mail_connect_personal.with_dependencies([client]).run(
            {
                "email_address": f"personal_{unique_id}@external.test",
                "password": "ext-pass",
                "imap_host": "imap.external.test",
                "imap_port": 993,
                "smtp_host": "smtp.external.test",
                "smtp_port": 465,
                "use_ssl": True,
            },
            _state(unique_id, uid),
        ),
        "connect_personal",
    )
    assert out.get("mailbox_binding_id")
    assert port.healthcheck_with_credentials_calls


@pytest.mark.asyncio
async def test_mail_create_mailbox_role(mail_env, unique_id: str) -> None:
    """Admin создаёт role-ящик (provision=False на generic connection)."""
    client, _port, _binding, _cid, uid, _svc = mail_env
    out = _as_object(
        await mail_create_mailbox.with_dependencies([client]).run(
            {
                "kind": "role",
                "local_part": f"info{unique_id[:6]}",
                "provision": False,
            },
            _state(unique_id, uid),
        ),
        "create_mailbox",
    )
    assert out.get("mailbox_binding_id")
    assert out.get("local_part") == f"info{unique_id[:6]}"
    assert out.get("kind") == "role"


@pytest.mark.asyncio
async def test_mail_send_from_personal_binding(mail_env, unique_id: str) -> None:
    """Произвольный внешний ящик: connect_personal → mail_send по binding_id."""
    client, port, _binding, _cid, uid, _svc = mail_env
    personal = _as_object(
        await mail_connect_personal.with_dependencies([client]).run(
            {
                "email_address": f"me_{unique_id}@mydomain.io",
                "password": "ext-pass",
                "imap_host": "imap.mydomain.io",
                "imap_port": 993,
                "smtp_host": "smtp.mydomain.io",
                "smtp_port": 465,
                "use_ssl": True,
            },
            _state(unique_id, uid),
        ),
        "connect_personal",
    )
    res = _as_object(
        await mail_send.with_dependencies([client]).run(
            {
                "mailbox_binding_id": personal["mailbox_binding_id"],
                "to_addresses": ["lead@example.com"],
                "subject": "Hi",
                "body_text": "B",
            },
            _state(unique_id, uid),
        ),
        "mail_send.personal",
    )
    assert res["mailbox_binding_id"] == personal["mailbox_binding_id"]
    assert port.sent[-1][0] == f"me_{unique_id}@mydomain.io"


# ---------------------------------------------------------------------------
# Tenant isolation: компания B не может читать/писать/слать ящики компании A,
# и обычный member компании C не может трогать personal-ящик коллеги.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def two_company_env(di, unique_id: str):
    """Компании A(binding 'sales') и B(binding 'ops'); контекст — userB@companyB."""
    company_a_id = f"mtA_{unique_id}"
    user_a_id = f"mtA_user_{unique_id}"
    company_b_id = f"mtB_{unique_id}"
    user_b_id = f"mtB_user_{unique_id}"
    port = RecordingMailServerPort(supports_provision=False)
    service = MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(),
        port_override=port,
        files_service=di.files_service,
    )
    company_a, user_a = await seed_mail_company_member(
        di, company_id=company_a_id, user_id=user_a_id, unique_id=unique_id
    )
    _ = await service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"a_{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.a.example.com",
            imap_port=993,
            smtp_host="smtp.a.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_a.company_id,
    )
    binding_a = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_a.user_id,
            local_part="sales",
            password="test-pass-tenant-a",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_a.company_id,
    )
    company_b, user_b = await seed_mail_company_member(
        di, company_id=company_b_id, user_id=user_b_id, unique_id=f"{unique_id}b"
    )
    _ = await service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"b_{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.b.example.com",
            imap_port=993,
            smtp_host="smtp.b.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company_b.company_id,
    )
    binding_b = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_b.user_id,
            local_part="ops",
            password="test-pass-tenant-b",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company_b.company_id,
    )
    deadline = asyncio.get_running_loop().time() + 10.0
    while not await di.authz_service.can_view(
        AuthzObject.company(company_b.company_id), user_id=user_b.user_id
    ):
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("authz can_view visibility timeout")
        await asyncio.sleep(0.05)
    yield MailClient(service), port, binding_a, binding_b, company_b.company_id, user_b.user_id


@pytest.mark.asyncio
async def test_cross_tenant_list_bindings_excludes_other_company(
    two_company_env, unique_id: str
) -> None:
    client, _port, binding_a, binding_b, _cid_b, uid_b = two_company_env
    bound = mail_list_bindings.with_dependencies([client])
    out = _as_object(await bound.run({}, _state(unique_id, uid_b)), "list_bindings.B")
    items = require_json_array(out.get("items"), "items")
    ids = {
        str(_as_object(i, "item").get("mailbox_binding_id") or "")
        for i in items
    }
    assert binding_b.mailbox_binding_id in ids
    assert binding_a.mailbox_binding_id not in ids, "ящик другой компании не должен попадать в список"


@pytest.mark.asyncio
async def test_cross_tenant_send_denied(two_company_env, unique_id: str) -> None:
    """mail_send: ни по чужому binding_id, ни по чужому local_part."""
    client, port, binding_a, _binding_b, _cid_b, uid_b = two_company_env
    bound = mail_send.with_dependencies([client])
    with pytest.raises(MailPermissionError):
        await bound.run(
            {
                "mailbox_binding_id": binding_a.mailbox_binding_id,
                "to_addresses": ["lead@example.com"],
                "subject": "S",
                "body_text": "B",
            },
            _state(unique_id, uid_b),
        )
    with pytest.raises(MailPermissionError):
        await bound.run(
            {
                "from_local_part": "sales",
                "to_addresses": ["lead@example.com"],
                "subject": "S",
                "body_text": "B",
            },
            _state(unique_id, uid_b),
        )
    assert port.sent == [], "письмо не должно уйти вообще"


@pytest.mark.asyncio
async def test_cross_tenant_binding_ops_denied(two_company_env, unique_id: str) -> None:
    """Все операции по чужому binding_id — отказ (binding вне компании B)."""
    client, _port, binding_a, _binding_b, _cid_b, uid_b = two_company_env
    bid = binding_a.mailbox_binding_id
    state = _state(unique_id, uid_b)
    denied = (MailPermissionError, MailBindingNotFoundError)
    ops: list[tuple[FunctionTool, JsonObject]] = [
        (mail_list_folders, {"mailbox_binding_id": bid}),
        (mail_list_messages, {"mailbox_binding_id": bid}),
        (mail_search_messages, {"mailbox_binding_id": bid, "q": "invoice"}),
        (mail_get_message, {"mailbox_binding_id": bid, "uid": "1"}),
        (mail_get_thread, {"mailbox_binding_id": bid, "uid": "1"}),
        (mail_sync_now, {"mailbox_binding_id": bid}),
        (mail_save_draft, {"mailbox_binding_id": bid, "to_addresses": ["x@y.zz"], "subject": "s", "body_text": "b"}),
        (mail_set_flags, {"mailbox_binding_id": bid, "uid": "1", "seen": True}),
        (mail_move_message, {"mailbox_binding_id": bid, "uid": "1", "destination_folder": "Trash"}),
        (mail_patch_binding, {"mailbox_binding_id": bid, "sync_enabled": False}),
        (mail_set_default_binding, {"mailbox_binding_id": bid}),
        (mail_list_members, {"mailbox_binding_id": bid}),
        (mail_add_member, {"mailbox_binding_id": bid, "user_id": "anyone"}),
        (mail_remove_member, {"mailbox_binding_id": bid, "user_id": "anyone"}),
        (mail_healthcheck_binding, {"mailbox_binding_id": bid}),
    ]
    for tool, args in ops:
        bound = tool.with_dependencies([client])
        tool_name = getattr(tool, "name", str(tool))
        with pytest.raises(denied):
            _ = await bound.run(args, state)



@pytest.mark.asyncio
async def test_cross_tenant_create_mailbox_lands_in_own_company(
    two_company_env, unique_id: str
) -> None:
    """create_mailbox как B создаёт ящик на домене/компании B, не A."""
    client, _port, binding_a, _binding_b, cid_b, uid_b = two_company_env
    out = _as_object(
        await mail_create_mailbox.with_dependencies([client]).run(
            {"kind": "role", "local_part": f"rb{unique_id[:6]}", "provision": False},
            _state(unique_id, uid_b),
        ),
        "create_mailbox.B",
    )
    email = str(out.get("email_address") or "").lower()
    assert email == f"rb{unique_id[:6]}@b_{unique_id}.example.com"
    assert str(out.get("company_id") or "") == cid_b


# ---------------------------------------------------------------------------
# Same-company: обычный member vs personal (USER) binding коллеги.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def same_company_env(di, unique_id: str):
    """Компания C: userA(admin, personal binding) + userM(member). Контекст — userM."""
    company_id = f"mtC_{unique_id}"
    user_a_id = f"mtC_userA_{unique_id}"
    user_m_id = f"mtC_userM_{unique_id}"
    port = RecordingMailServerPort(supports_provision=False)
    service = MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(),
        port_override=port,
        files_service=di.files_service,
    )
    company, user_a = await seed_mail_company_member(
        di, company_id=company_id, user_id=user_a_id, unique_id=unique_id
    )
    _ = await service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"c_{unique_id}.example.com",
            provider=MailProvider.GENERIC_IMAP_SMTP,
            imap_host="imap.c.example.com",
            imap_port=993,
            smtp_host="smtp.c.example.com",
            smtp_port=465,
            use_ssl=True,
        ),
        company_id=company.company_id,
    )
    binding_a = await service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_a.user_id,
            local_part="boss",
            password="test-pass-tenant-c",
            provision=False,
            sync_enabled=True,
        ),
        company_id=company.company_id,
    )
    # userM — обычный member той же компании (без admin).
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
    await Company.set(company)
    await set_test_company_member_roles(
        di.authz_service,
        company_id=company.company_id,
        user_id=user_m.user_id,
        roles=["member"],
    )
    set_context(
        Context(
            user=user_m,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    # member компании проходит tool-gate (can_view company) — ждём visibility.
    deadline = asyncio.get_running_loop().time() + 10.0
    while not await di.authz_service.can_view(
        AuthzObject.company(company.company_id), user_id=user_m.user_id
    ):
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("authz can_view visibility timeout")
        await asyncio.sleep(0.05)
    yield MailClient(service), port, binding_a, company.company_id, user_m.user_id


@pytest.mark.asyncio
async def test_same_company_member_isolation(same_company_env, unique_id: str) -> None:
    """Member видит только свои ящики: personal binding коллеги недоступен."""
    client, port, binding_a, _cid, uid_m = same_company_env
    state = _state(unique_id, uid_m)
    out = _as_object(
        await mail_list_bindings.with_dependencies([client]).run({}, state),
        "list_bindings.member",
    )
    items = require_json_array(out.get("items"), "items")
    ids = {
        str(_as_object(i, "item").get("mailbox_binding_id") or "")
        for i in items
    }
    assert binding_a.mailbox_binding_id not in ids
    denied = (MailPermissionError, MailBindingNotFoundError)
    with pytest.raises(denied):
        await mail_send.with_dependencies([client]).run(
            {
                "mailbox_binding_id": binding_a.mailbox_binding_id,
                "to_addresses": ["lead@example.com"],
                "subject": "S",
                "body_text": "B",
            },
            state,
        )
    with pytest.raises(denied):
        await mail_get_message.with_dependencies([client]).run(
            {"mailbox_binding_id": binding_a.mailbox_binding_id, "uid": "1"},
            state,
        )
    with pytest.raises(denied):
        await mail_list_folders.with_dependencies([client]).run(
            {"mailbox_binding_id": binding_a.mailbox_binding_id},
            state,
        )
    assert port.sent == []
