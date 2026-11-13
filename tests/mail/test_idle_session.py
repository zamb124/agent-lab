"""MailIdleSession: lifecycle IDLE-команды — DONE + await до logout."""

from __future__ import annotations

import asyncio

import aioimaplib
import pytest

from core.mail.exceptions import MailTransportError
from core.mail.models import MailIdleWakeKind
from core.mail.transport.idle_session import MailIdleSession

# aioimaplib.Response — runtime namedtuple(result, lines), stub не видит полей.
_OK_RESPONSE = aioimaplib.Response("OK", [])  # pyright: ignore[reportCallIssue]


class _FakeIdleClient:
    """Минимальный фейк aioimaplib: idle_start отдаёт pending-задачу IDLE."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._idle_future: asyncio.Future[aioimaplib.Response] | None = None
        self.hold_idle: bool = False
        self.push: list[bytes] | None = None
        self.push_exc: Exception | None = None

    async def idle_start(self, timeout: float = 0) -> asyncio.Future[aioimaplib.Response]:
        _ = timeout
        self.calls.append("idle_start")
        loop = asyncio.get_running_loop()
        self._idle_future = loop.create_future()
        if not self.hold_idle:
            self._idle_future.set_result(_OK_RESPONSE)
        return self._idle_future

    async def wait_server_push(self) -> list[bytes]:
        self.calls.append("wait_server_push")
        if self.push is not None:
            return self.push
        if self.push_exc is not None:
            raise self.push_exc
        await asyncio.sleep(60)
        raise AssertionError("wait_server_push must be cancelled by timeout")

    def idle_done(self) -> None:
        self.calls.append("idle_done")
        if self._idle_future is not None and not self._idle_future.done():
            self._idle_future.set_result(_OK_RESPONSE)

    async def logout(self) -> aioimaplib.Response:
        self.calls.append("logout")
        return _OK_RESPONSE


def _session(client: _FakeIdleClient) -> MailIdleSession:
    return MailIdleSession(
        client,  # pyright: ignore[reportArgumentType] — фейк клиента
        mailbox="INBOX",
    )


@pytest.mark.asyncio
async def test_aclose_finishes_pending_idle_before_logout() -> None:
    """Pending IDLE-команда завершается через idle_done + await до logout."""
    client = _FakeIdleClient()
    session = _session(client)
    client.hold_idle = True
    _ = await session.wait_wake(timeout_seconds=0.05)
    await session.aclose()
    assert client.calls[-2:] == ["idle_done", "logout"]


@pytest.mark.asyncio
async def test_wait_wake_timeout_finishes_idle() -> None:
    """Таймаут wait_wake завершает IDLE-команду до возврата."""
    client = _FakeIdleClient()
    session = _session(client)
    wake = await session.wait_wake(timeout_seconds=0.05)
    assert wake.kind == MailIdleWakeKind.TIMEOUT
    assert client.calls == ["idle_start", "wait_server_push", "idle_done"]


@pytest.mark.asyncio
async def test_wait_wake_push_finishes_idle_and_classifies() -> None:
    """EXISTS-push: IDLE завершается до возврата, wake классифицирован."""
    client = _FakeIdleClient()
    client.push = [b"* 4 EXISTS"]
    session = _session(client)
    wake = await session.wait_wake(timeout_seconds=1)
    assert wake.kind == MailIdleWakeKind.EXISTS
    assert client.calls == ["idle_start", "wait_server_push", "idle_done"]


@pytest.mark.asyncio
async def test_wait_wake_wait_error_finishes_idle() -> None:
    """Ошибка wait_server_push: IDLE завершается, ошибка обёрнута в MailTransportError."""
    client = _FakeIdleClient()
    client.push_exc = ConnectionError("conn reset")
    session = _session(client)
    with pytest.raises(MailTransportError, match="IMAP IDLE wait failed"):
        _ = await session.wait_wake(timeout_seconds=1)
    assert client.calls == ["idle_start", "wait_server_push", "idle_done"]


@pytest.mark.asyncio
async def test_aclose_idempotent_and_wait_after_close_fails() -> None:
    """aclose без IDLE — только logout; повторный aclose no-op; wait после close — ошибка."""
    client = _FakeIdleClient()
    session = _session(client)
    await session.aclose()
    await session.aclose()
    assert client.calls == ["logout"]
    with pytest.raises(MailTransportError, match="already closed"):
        _ = await session.wait_wake(timeout_seconds=1)
