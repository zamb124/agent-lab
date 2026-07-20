"""IMAP IDLE session поверх aioimaplib."""

from __future__ import annotations

import asyncio
from typing import Final, Protocol, cast, final

import aioimaplib

from core.mail.exceptions import MailTransportError
from core.mail.models import MailIdleWake, MailIdleWakeKind


class _ImapIdleOps(Protocol):
    def idle_start(self, timeout: float = ...) -> asyncio.Future[object]: ...

    def wait_server_push(self) -> asyncio.Future[object]: ...

    def idle_done(self) -> object: ...

    def logout(self) -> asyncio.Future[object]: ...


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
    """Долгая IMAP SELECT + IDLE. Caller владеет lifecycle (aclose)."""

    def __init__(self, client: aioimaplib.IMAP4_SSL, *, mailbox: str) -> None:
        self._client: Final[_ImapIdleOps] = cast(_ImapIdleOps, cast(object, client))
        self._mailbox: Final[str] = mailbox
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
            _ = await self._client.idle_start(timeout=timeout_seconds)
        except Exception as exc:
            raise MailTransportError(f"IMAP IDLE start failed: {exc}") from exc
        try:
            push = await asyncio.wait_for(
                self._client.wait_server_push(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            try:
                _ = self._client.idle_done()
            except Exception as exc:
                raise MailTransportError(f"IMAP IDLE done after timeout failed: {exc}") from exc
            return MailIdleWake(kind=MailIdleWakeKind.TIMEOUT, raw="")
        except Exception as exc:
            try:
                _ = self._client.idle_done()
            except Exception:
                pass
            raise MailTransportError(f"IMAP IDLE wait failed: {exc}") from exc
        try:
            _ = self._client.idle_done()
        except Exception as exc:
            raise MailTransportError(f"IMAP IDLE done failed: {exc}") from exc
        if isinstance(push, (bytes, bytearray)):
            raw = bytes(push).decode("utf-8", errors="replace")
        elif isinstance(push, str):
            raw = push
        elif isinstance(push, list):
            parts: list[str] = []
            push_items: list[object] = cast(list[object], push)
            for item in push_items:
                if isinstance(item, (bytes, bytearray)):
                    parts.append(bytes(item).decode("utf-8", errors="replace"))
                else:
                    parts.append(str(item))
            raw = " ".join(parts)
        else:
            raw = str(push)
        return MailIdleWake(kind=classify_idle_push(raw), raw=raw)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            _ = await self._client.logout()
        except Exception as exc:
            raise MailTransportError(f"IMAP IDLE logout failed: {exc}") from exc
