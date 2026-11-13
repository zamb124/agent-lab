"""IMAP IDLE session поверх aioimaplib."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Final, Protocol, final

import aioimaplib

from core.imports import typed_view
from core.logging import get_logger
from core.mail.exceptions import MailTransportError
from core.mail.models import MailIdleWake, MailIdleWakeKind

logger = get_logger(__name__)

ImapIdlePush = list[bytes] | bytes | bytearray | str

# DONE/LOGOUT на полуживом соединении не должны висеть дольше этого окна.
_IDLE_FINISH_TIMEOUT_S = 5.0


class _ImapIdleOps(Protocol):
    def idle_start(self, timeout: float = ...) -> Awaitable[asyncio.Future[aioimaplib.Response]]: ...

    def wait_server_push(self) -> Awaitable[ImapIdlePush]: ...

    def idle_done(self) -> None: ...

    def logout(self) -> Awaitable[aioimaplib.Response]: ...


def classify_idle_push(raw: str) -> MailIdleWakeKind:
    upper = raw.upper()
    if "EXISTS" in upper:
        return MailIdleWakeKind.EXISTS
    if "RECENT" in upper:
        return MailIdleWakeKind.RECENT
    if "EXPUNGE" in upper:
        return MailIdleWakeKind.EXPUNGE
    if "BYE" in upper:
        return MailIdleWakeKind.BYE
    return MailIdleWakeKind.OTHER


@final
class MailIdleSession:
    """Долгая IMAP SELECT + IDLE. Caller владеет lifecycle (aclose).

    ``idle_start`` возвращает future pending IDLE-команды: она завершается
    только после DONE и ответа сервера. LOGOUT при живой IDLE-команде —
    protocol abort с пустым текстом, поэтому каждый выход из IDLE ждёт
    завершения команды, а ``aclose`` завершает незакрытый IDLE до logout.
    """

    def __init__(self, client: aioimaplib.IMAP4_SSL, *, mailbox: str) -> None:
        self._client: Final[_ImapIdleOps] = typed_view(client, aioimaplib.IMAP4_SSL, _ImapIdleOps)
        self._mailbox: Final[str] = mailbox
        self._idle_future: asyncio.Future[aioimaplib.Response] | None = None
        self._closed: bool = False

    @property
    def mailbox(self) -> str:
        return self._mailbox

    async def wait_wake(self, *, timeout_seconds: float) -> MailIdleWake:
        if self._closed:
            raise MailTransportError("MailIdleSession already closed")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        try:
            self._idle_future = await self._client.idle_start(timeout=timeout_seconds)
        except Exception as exc:
            raise MailTransportError(f"IMAP IDLE start failed: {exc}") from exc
        try:
            push = await asyncio.wait_for(
                self._client.wait_server_push(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            try:
                await self._finish_idle()
            except Exception as exc:
                raise MailTransportError(f"IMAP IDLE done after timeout failed: {exc}") from exc
            return MailIdleWake(kind=MailIdleWakeKind.TIMEOUT, raw="")
        except Exception as exc:
            await self._finish_idle_after_wait_error()
            raise MailTransportError(f"IMAP IDLE wait failed: {exc}") from exc
        try:
            await self._finish_idle()
        except Exception as exc:
            raise MailTransportError(f"IMAP IDLE done failed: {exc}") from exc
        if isinstance(push, list):
            raw = " ".join(item.decode("utf-8", errors="replace") for item in push)
        elif isinstance(push, str):
            raw = push
        else:
            raw = bytes(push).decode("utf-8", errors="replace")
        return MailIdleWake(kind=classify_idle_push(raw), raw=raw)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._finish_idle()
        except Exception as exc:
            logger.warning(
                "mail_idle_done_on_close_failed",
                mailbox=self._mailbox,
                error=str(exc),
            )
        try:
            _ = await asyncio.wait_for(self._client.logout(), timeout=_IDLE_FINISH_TIMEOUT_S)
        except Exception as exc:
            raise MailTransportError(
                f"IMAP IDLE logout failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def _finish_idle(self) -> None:
        """DONE + дождаться завершения pending IDLE-команды (bounded)."""
        idle_future = self._idle_future
        if idle_future is None:
            return
        self._idle_future = None
        self._client.idle_done()
        _ = await asyncio.wait_for(idle_future, timeout=_IDLE_FINISH_TIMEOUT_S)

    async def _finish_idle_after_wait_error(self) -> None:
        try:
            await self._finish_idle()
        except Exception as exc:
            logger.info(
                "mail_idle_done_after_wait_failed",
                mailbox=self._mailbox,
                error=str(exc),
            )
