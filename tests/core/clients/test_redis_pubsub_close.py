"""Закрытие Redis-подписки не роняет выход из subscribe."""

import pytest

from core.clients.redis_client import _RedisSdkPubSub


class _UnsubscribeFails(_RedisSdkPubSub):
    def __init__(self) -> None:
        self.unsubscribed: bool = False

    async def unsubscribe(self, *channels: str) -> None:
        _ = channels
        self.unsubscribed = True
        raise OSError("closed")

    async def aclose(self) -> None:
        raise AssertionError("aclose must not run after unsubscribe failure")


class _Closes(_RedisSdkPubSub):
    def __init__(self) -> None:
        self.steps: list[str] = []

    async def unsubscribe(self, *channels: str) -> None:
        _ = channels
        self.steps.append("unsubscribe")

    async def aclose(self) -> None:
        self.steps.append("aclose")


@pytest.mark.asyncio
async def test_close_subscription_survives_oserror() -> None:
    pubsub = _UnsubscribeFails()
    await pubsub.close_subscription("channel-1")
    assert pubsub.unsubscribed is True


@pytest.mark.asyncio
async def test_close_subscription_unsubscribes_then_closes() -> None:
    pubsub = _Closes()
    await pubsub.close_subscription("channel-1")
    assert pubsub.steps == ["unsubscribe", "aclose"]
