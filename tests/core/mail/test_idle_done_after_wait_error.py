"""Сбой IMAP IDLE wait не прячет ошибку idle_done и не теряет исходную ошибку ожидания."""

from collections.abc import Awaitable

from core.mail.transport.idle_session import ImapIdlePush, _finish_idle_after_wait_error


class _DoneFails:
    def __init__(self) -> None:
        self.done_calls: int = 0

    def idle_start(self, timeout: float = 0) -> Awaitable[None]:
        _ = timeout
        raise AssertionError("idle_start is not used")

    def wait_server_push(self) -> Awaitable[ImapIdlePush]:
        raise AssertionError("wait_server_push is not used")

    def idle_done(self) -> None:
        self.done_calls += 1
        raise RuntimeError("done failed")

    def logout(self) -> Awaitable[None]:
        raise AssertionError("logout is not used")


def test_finish_idle_after_wait_error_survives_done_failure() -> None:
    client = _DoneFails()
    _finish_idle_after_wait_error(client, mailbox="INBOX")
    assert client.done_calls == 1
