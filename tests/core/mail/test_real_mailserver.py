"""Реальный MTA (GreenMail в docker-compose-test): wire-level IMAPS + SMTP.

Эти тесты НЕ используют RecordingMailServerPort: MailService строит настоящий
ImapSmtpTransport через production-фабрику, TLS-цепочка верифицируется по
закоммиченному CA (tests/certs/greenmail-test-ca.pem — cert самого образа),
письма реально ходят по TCP в GreenMail и обратно. Независимая проверка —
второй aioimaplib-клиент, который логинится в тот же сервер и читает папки.

Нужен поднятый greenmail-test (make test-up).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from core.clients.mail_client import MailClient
from core.config.models import MailConfig, MailTlsConfig
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailProvider,
)
from core.mail.service import MailService
from tests.core.mail.conftest import seed_mail_company_member
from tests.core.mail.greenmail import (
    GREENMAIL_CA_FILE,
    GREENMAIL_IMAP_HOST,
    GREENMAIL_IMAP_PORT,
    GREENMAIL_MAIL_DOMAIN,
    GREENMAIL_SMTP_HOST,
    GREENMAIL_SMTP_PORT,
    greenmail_ensure_user,
    imap_client,
    imap_logout_quietly,
    imap_uids_by_subject,
    smtp_deliver,
)


@pytest_asyncio.fixture()
async def real_mail_env(di, unique_id: str) -> AsyncIterator[
    tuple[MailClient, MailService, MailboxBinding, str, str]
]:
    """Компания + real connection(gm.test) + binding + живой GreenMail-пользователь.

    MailService БЕЗ port_override: порт строится production-фабрикой из
    connection + mail_config.tls (extra_ca_file → verified TLS к GreenMail).
    """
    password = "real-mail-pass"
    company, user = await seed_mail_company_member(
        di,
        company_id=f"gm_{unique_id}",
        user_id=f"gm_user_{unique_id}",
        unique_id=unique_id,
    )
    service = MailService(
        authz=di.authz_service,
        namespace_service=di.namespace_service,
        mail_config=MailConfig(
            tls=MailTlsConfig(
                extra_ca_file=str(GREENMAIL_CA_FILE),
                check_hostname=False,
            )
        ),
        files_service=di.files_service,
    )
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
            local_part=f"s{unique_id}",
            password=password,
            provision=False,
            sync_enabled=True,
        ),
        company_id=company.company_id,
    )
    await greenmail_ensure_user(binding.email_address, password)
    yield MailClient(service), service, binding, binding.email_address, password


@pytest.mark.asyncio
async def test_real_send_delivers_and_appends_sent(
    real_mail_env, unique_id: str
) -> None:
    """send_message: SMTP → MTA → INBOX получателя, APPEND → Sent отправителя."""
    client, _service, binding, sender_email, password = real_mail_env
    recipient = f"lead{unique_id}@{GREENMAIL_MAIL_DOMAIN}"
    recipient_password = "lead-pass"
    await greenmail_ensure_user(recipient, recipient_password)

    subject = f"real-send-{unique_id}"
    result = await client.send(
        mailbox_binding_id=binding.mailbox_binding_id,
        to_addresses=[recipient],
        subject=subject,
        body_text="Текст продажного письма",
        body_html="<b>Текст продажного письма</b>",
        sender_display_name="Platform Sales",
    )
    assert result["accepted"] == [recipient]
    assert result["from_address"] == sender_email

    # Независимая проверка: получатель видит письмо в своём INBOX по IMAP.
    deadline = asyncio.get_running_loop().time() + 10.0
    uids: list[bytes] = []
    while not uids:
        uids = await imap_uids_by_subject(
            recipient, recipient_password, folder="INBOX", subject=subject
        )
        if uids:
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("письмо не дошло до INBOX получателя")
        await asyncio.sleep(0.4)
    assert uids, "SMTP-доставка не подтверждена реальным IMAP-фетчем"

    # Отправитель: копия в Sent по реальному APPEND (ранее этот путь был недоступен).
    sent_uids = await imap_uids_by_subject(
        sender_email, password, folder="Sent", subject=subject
    )
    assert sent_uids, "Sent-копия не найдена на сервере после APPEND"


@pytest.mark.asyncio
async def test_real_inbound_sync_read_flags_move(real_mail_env, unique_id: str) -> None:
    """Полный read-path: SMTP in → IMAP sync → local read → flags/move на сервере."""
    client, service, binding, email_address, password = real_mail_env
    subject = f"real-inbound-{unique_id}"
    await smtp_deliver(
        to_address=email_address,
        from_address="customer@external.example",
        subject=subject,
        body="Входящий запрос от клиента",
    )
    await asyncio.sleep(0.4)

    # Реальный IMAP-fetch → persist → local-first чтение.
    sync = await service.sync_binding(binding, max_new_messages=50)
    assert sync.skipped_reason is None, f"sync skipped: {sync.skipped_reason}"

    # Folders — реальный LIST + CREATE стандартных папок на сервере.
    ensured = await service.ensure_standard_folders(binding.mailbox_binding_id)
    names = {f.name for f in ensured.folders}
    assert "INBOX" in names
    assert "Sent" in names, "ensure_standard_folders должен создать Sent на сервере"
    folders = await client.list_folders(mailbox_binding_id=binding.mailbox_binding_id)
    cached_names = {f.get("name") for f in folders.get("folders", [])}
    assert "Sent" in cached_names
    listed = await client.list_messages(
        mailbox_binding_id=binding.mailbox_binding_id, folder="INBOX"
    )
    items = listed.get("items") or []
    inbound = next((m for m in items if m.get("subject") == subject), None)
    assert inbound is not None, f"письмо {subject} не найдено в list_messages"
    uid = str(inbound["uid"])

    message = await client.get_message(
        mailbox_binding_id=binding.mailbox_binding_id, uid=uid, folder="INBOX"
    )
    assert "запрос от клиента" in (message.get("body_text") or "")

    found = await client.search_messages(
        mailbox_binding_id=binding.mailbox_binding_id, q="клиента", folder="INBOX"
    )
    hits = found.get("items") or []
    assert any(m.get("subject") == subject for m in hits)

    # Флаги: mark_seen → реальный UID STORE на сервере.
    _ = await client.set_flags(
        mailbox_binding_id=binding.mailbox_binding_id, uid=uid, folder="INBOX", seen=True
    )
    deadline = asyncio.get_running_loop().time() + 10.0
    while True:
        check = await imap_client(email_address, password)
        try:
            await check.select("INBOX")
            fetch = await check.uid("fetch", uid, "(FLAGS)")
            line = b" ".join(
                item for item in fetch.lines if isinstance(item, (bytes, bytearray))
            )
            if b"\\Seen" in line:
                break
        finally:
            await imap_logout_quietly(check)
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("\\Seen не появился на сервере")
        await asyncio.sleep(0.3)

    # Move: реальный UID COPY+STORE\Deleted+EXPUNGE в Trash.
    _ = await client.move_message(
        mailbox_binding_id=binding.mailbox_binding_id,
        uid=uid,
        folder="INBOX",
        destination_folder="Trash",
    )
    deadline = asyncio.get_running_loop().time() + 10.0
    while True:
        trash_uids = await imap_uids_by_subject(
            email_address, password, folder="Trash", subject=subject
        )
        if trash_uids:
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("письмо не появилось в Trash после move")
        await asyncio.sleep(0.3)
    remaining = await imap_uids_by_subject(
        email_address, password, folder="INBOX", subject=subject
    )
    assert remaining == [], "письмо должно исчезнуть из INBOX после move"


@pytest.mark.asyncio
async def test_real_save_draft(real_mail_env, unique_id: str) -> None:
    """save_draft → реальный APPEND в Drafts с флагом \\Draft."""
    client, _service, binding, email_address, password = real_mail_env
    subject = f"real-draft-{unique_id}"
    draft = await client.save_draft(
        mailbox_binding_id=binding.mailbox_binding_id,
        to_addresses=["someone@example.com"],
        subject=subject,
        body_text="Черновик ответа",
    )
    assert draft.get("uid") or draft.get("mailbox_binding_id")

    uids = await imap_uids_by_subject(
        email_address, password, folder="Drafts", subject=subject
    )
    assert uids, "черновик не найден в Drafts на сервере"


@pytest.mark.asyncio
async def test_real_personal_connect_and_healthcheck(
    real_mail_env, unique_id: str
) -> None:
    """connect_personal → реальный IMAP+SMTP login-probe → binding; затем healthcheck."""
    client, _service, _binding, _email, _password = real_mail_env
    personal_email = f"p{unique_id}@{GREENMAIL_MAIL_DOMAIN}"
    personal_password = "personal-pass"
    await greenmail_ensure_user(personal_email, personal_password)

    connected = await client.connect_personal(
        email_address=personal_email,
        password=personal_password,
        imap_host=GREENMAIL_IMAP_HOST,
        imap_port=GREENMAIL_IMAP_PORT,
        smtp_host=GREENMAIL_SMTP_HOST,
        smtp_port=GREENMAIL_SMTP_PORT,
        use_ssl=False,
    )
    personal_binding_id = str(connected.get("mailbox_binding_id") or "")
    assert personal_binding_id, "personal binding не создан после реального login-probe"

    health = await client.healthcheck_binding(mailbox_binding_id=personal_binding_id)
    assert health.get("imap_ok") is True, health
    assert health.get("smtp_ok") is True, health
