"""Общие хелперы для GreenMail MTA (docker-compose-test.yaml, сервис greenmail-test).

GreenMail — реальный почтовый сервер (SMTP :33025, IMAPS :33993, HTTP API :38080).
TLS: образ содержит фиксированный self-signed cert (один и тот же на каждом
boot), его PEM закоммичен в tests/certs/greenmail-test-ca.pem — поэтому
цепочка верифицируется по-настоящему; hostname-check выключен, потому что
CN сертификата не содержит localhost.

Порты выставлены наружу на 127.0.0.1 — granian/воркеры тест-стека ходят
прямо по хостовым портам, как настоящие клиенты MTA.
"""

from __future__ import annotations

import asyncio
import ssl
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path
from typing import cast

import aioimaplib
import aiosmtplib
from httpx2 import AsyncClient


async def imap_logout_quietly(client: aioimaplib.IMAP4_SSL) -> None:
    """GreenMail не отвечает на LOGOUT — teardown best-effort (как в транспорте)."""
    try:
        _ = await asyncio.wait_for(client.logout(), timeout=3.0)
    except Exception:
        pass

GREENMAIL_IMAP_HOST = "127.0.0.1"
GREENMAIL_IMAP_PORT = 33993
GREENMAIL_SMTP_HOST = "127.0.0.1"
GREENMAIL_SMTP_PORT = 33025
GREENMAIL_API_BASE = "http://localhost:38080"
GREENMAIL_MAIL_DOMAIN = "gm.test"
GREENMAIL_CA_FILE = (
    Path(__file__).resolve().parents[2] / "certs" / "greenmail-test-ca.pem"
)


def greenmail_ssl_context() -> ssl.SSLContext:
    """Тот же контекст, что MailService строит из MAIL__TLS__* в тест-стеке."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(GREENMAIL_CA_FILE))
    context.check_hostname = False
    return context


async def greenmail_ensure_user(email: str, password: str) -> None:
    """Создаёт пользователя GreenMail через HTTP API (идемпотентно).

    Проверка readiness заодно гарантирует, что тест падает сразу и понятно,
    если контейнер не поднят.
    """
    async with AsyncClient(base_url=GREENMAIL_API_BASE, timeout=10.0) as http:
        readiness = await http.get("/api/service/readiness")
        _ = readiness.raise_for_status()
        users = cast(
            list[dict[str, object]], (await http.get("/api/user")).json()
        )
        if not any(u.get("email") == email for u in users):
            created = await http.post(
                "/api/user",
                json={"email": email, "login": email, "password": password},
            )
            _ = created.raise_for_status()


async def greenmail_purge_user_mailbox(email: str) -> None:
    """Очищает все папки ящика (детерминизм между прогонами)."""
    async with AsyncClient(base_url=GREENMAIL_API_BASE, timeout=10.0) as http:
        response = await http.post("/api/mail/purge", params={"email": email})
        # 404 (нет такого эндпоинта в старой версии) — не фатально: письма
        # разных тестов различаются subject уникальными суффиксами.
        _ = response


async def imap_client(email: str, password: str) -> aioimaplib.IMAP4_SSL:
    """Независимый IMAP-клиент для проверки состояния сервера снаружи кода."""
    client = aioimaplib.IMAP4_SSL(
        host=GREENMAIL_IMAP_HOST,
        port=GREENMAIL_IMAP_PORT,
        ssl_context=greenmail_ssl_context(),
    )
    await client.wait_hello_from_server()
    response = await client.login(email, password)
    assert response.result == "OK", f"IMAP login {email}: {response}"
    return client


def _decode_subject(raw_header: bytes) -> str:
    """Раскодирует encoded-word Subject (=?utf-8?b?...?=) в текст."""
    fragments: list[tuple[bytes | str, str | None]] = decode_header(
        raw_header.decode("utf-8", errors="replace")
    )
    return "".join(
        part.decode(charset or "utf-8", errors="replace")
        if isinstance(part, bytes)
        else part
        for part, charset in fragments
    )


def _search_uids(lines: list[bytes | str]) -> list[bytes]:
    if not lines or not lines[0]:
        return []
    return [token for token in lines[0].split() if isinstance(token, bytes) and token.isdigit()]


async def _subject_by_uid(
    client: aioimaplib.IMAP4_SSL, uids: list[bytes]
) -> dict[bytes, str]:
    """SUBJECT каждого UID, декодированный локально — не зависит от SEARCH-диалекта MTA."""
    subjects: dict[bytes, str] = {}
    for uid in uids:
        fetched = await client.uid(
            "fetch", uid.decode(), "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])"
        )
        for line in fetched.lines:
            if isinstance(line, (bytes, bytearray)) and b"Subject:" in line:
                subjects[uid] = _decode_subject(line.split(b"Subject:", 1)[1].strip())
                break
    return subjects


async def imap_uids_by_subject(
    email: str,
    password: str,
    *,
    folder: str,
    subject: str,
) -> list[bytes]:
    """UID'ы писем с данным SUBJECT (substring) в папке — доказательство по проводу.

    SEARCH ALL + локальное сравнение: на GreenMail `SEARCH CHARSET UTF-8 SUBJECT`
    не матчит encoded-word сабжекты, поэтому декодируем заголовки сами.
    """
    client = await imap_client(email, password)
    try:
        selected = await client.select(folder)
        assert selected.result == "OK", f"SELECT {folder}: {selected}"
        found = await client.search("ALL")
        assert found.result == "OK"
        uids = _search_uids(found.lines)
        subjects = await _subject_by_uid(client, uids)
        return [uid for uid, subj in subjects.items() if subject in subj]
    finally:
        await imap_logout_quietly(client)


async def imap_fetch_raw(
    email: str,
    password: str,
    *,
    folder: str,
    subject: str,
) -> bytes | None:
    """Сырое RFC822 письма по SUBJECT — проверка MIME-заголовков по проводу."""
    client = await imap_client(email, password)
    try:
        selected = await client.select(folder)
        assert selected.result == "OK", f"SELECT {folder}: {selected}"
        found = await client.search("ALL")
        assert found.result == "OK"
        uids = _search_uids(found.lines)
        subjects = await _subject_by_uid(client, uids)
        matched = [uid for uid, subj in subjects.items() if subject in subj]
        if not matched:
            return None
        fetched = await client.uid("fetch", matched[-1].decode(), "(RFC822)")
        payload = [
            bytes(line)
            for line in fetched.lines
            if isinstance(line, (bytes, bytearray))
        ]
        return b"\n".join(payload)
    finally:
        await imap_logout_quietly(client)


async def smtp_deliver(
    *,
    to_address: str,
    from_address: str,
    subject: str,
    body: str,
) -> None:
    """Внешнее входящее письмо: реальный SMTP-клиент → MTA → INBOX пользователя."""
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = subject
    message["Message-ID"] = f"<inbound-{subject}@external>"
    message.set_content(body)
    smtp = aiosmtplib.SMTP(
        hostname=GREENMAIL_SMTP_HOST, port=GREENMAIL_SMTP_PORT, use_tls=False
    )
    _ = await smtp.connect()
    try:
        _ = await smtp.send_message(message)
    finally:
        _ = await smtp.quit()
