"""Фикстура жизненного цикла эмулятора провайдеров верификации телефона.

Поднимает реальный Granian на свободном порту и прописывает бренд-конфиг
`customer_auth.brands["localhost"]` с endpoint'ами на эмулятор — ни одного
monkeypatch: прод-код читает URL из конфига, как в проде.

Host-заголовок `linnex.io` резолвится в apex `linnex.io`; cookie
`customer_token` ставится на `.linnex.io` — не public suffix, jar её
принимает (в отличие от `localhost`/`lvh.me`, которые в PSL).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from granian.constants import Interfaces
from granian.server.embed import Server as GranianEmbedServer

from core.config import get_settings
from core.config.models import (
    CustomerAuthBrandConfig,
    CustomerAuthMaxBotConfig,
    CustomerAuthOAuthClientConfig,
    CustomerAuthSmsruConfig,
    CustomerAuthTelegramBotConfig,
)
from tests.fixtures.phone_verification_emulator.app import (
    create_phone_verification_emulator_app,
)
from tests.fixtures.phone_verification_emulator.store import ProviderEmulatorStore

EMULATOR_APEX = "linnex.io"
TG_BOT_TOKEN = "111111:emu-telegram-token"
TG_BOT_USERNAME = "linnex_emulator_bot"
TG_WEBHOOK_SECRET = "emu-tg-secret"
MAX_ACCESS_TOKEN = "emu-max-access-token"
MAX_BOT_NAME = "linnex_emu_bot"
MAX_WEBHOOK_SECRET = "emu-max-secret"
OAUTH_CLIENT_ID = "emu-client-id"
OAUTH_CLIENT_SECRET = "emu-client-secret"
SMSRU_API_ID = "emu-smsru-api-id"


@dataclass(frozen=True)
class PhoneVerificationEmulatorHandle:
    base_url: str
    apex: str
    store: ProviderEmulatorStore


async def _wait_tcp_ready(host: str, port: int, attempts: int = 100) -> None:
    for _ in range(attempts):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError(f"phone verification emulator did not open {host}:{port}")


def emulator_brand_config(base_url: str) -> CustomerAuthBrandConfig:
    oauth = {
        slug: CustomerAuthOAuthClientConfig(
            enabled=True,
            client_id=OAUTH_CLIENT_ID,
            client_secret=OAUTH_CLIENT_SECRET,
            authorize_url=authorize_url,
            token_url=token_url,
            userinfo_url=userinfo_url,
        )
        for slug, authorize_url, token_url, userinfo_url in [
            (
                "yandex",
                f"{base_url}/yandex/authorize",
                f"{base_url}/yandex/token",
                f"{base_url}/yandex/info",
            ),
            (
                "vk",
                f"{base_url}/vk/authorize",
                f"{base_url}/vk/oauth2/auth",
                f"{base_url}/vk/oauth2/user_info",
            ),
            (
                "sber",
                f"{base_url}/sber/CSAFront/oidc/authorize.do",
                f"{base_url}/sber/ru/prod/tokens/v2/oidc",
                f"{base_url}/sber/ru/prod/sberbankid/v2.1/userinfo",
            ),
        ]
    }
    return CustomerAuthBrandConfig(
        telegram=CustomerAuthTelegramBotConfig(
            enabled=True,
            bot_token=TG_BOT_TOKEN,
            bot_username=TG_BOT_USERNAME,
            webhook_secret=TG_WEBHOOK_SECRET,
            api_base_url=f"{base_url}/tg",
            polling_enabled=True,
        ),
        max=CustomerAuthMaxBotConfig(
            enabled=True,
            access_token=MAX_ACCESS_TOKEN,
            bot_name=MAX_BOT_NAME,
            webhook_secret=MAX_WEBHOOK_SECRET,
            api_base_url=f"{base_url}/max",
        ),
        yandex=oauth["yandex"],
        vk=oauth["vk"],
        sber=oauth["sber"],
        smsru=CustomerAuthSmsruConfig(
            enabled=True,
            api_id=SMSRU_API_ID,
            api_base_url=f"{base_url}/smsru",
        ),
    )


@pytest.fixture
async def phone_verification_emulator(
    unused_tcp_port_factory: object,
) -> AsyncIterator[PhoneVerificationEmulatorHandle]:
    port_factory = unused_tcp_port_factory
    if not callable(port_factory):
        raise TypeError("unused_tcp_port_factory must be callable")
    port = int(port_factory())
    store = ProviderEmulatorStore(
        max_access_token=MAX_ACCESS_TOKEN,
        client_credentials={
            "yandex": (OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
            "vk": (OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
            "sber": (OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
        },
    )
    app = create_phone_verification_emulator_app(store)
    server = GranianEmbedServer(
        app, interface=Interfaces.ASGI, address="127.0.0.1", port=port
    )
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp_ready("127.0.0.1", port)
        base_url = f"http://127.0.0.1:{port}"
        settings = get_settings()
        brands = settings.customer_auth.brands
        previous = brands.get(EMULATOR_APEX)
        brands[EMULATOR_APEX] = emulator_brand_config(base_url)
        try:
            yield PhoneVerificationEmulatorHandle(
                base_url=base_url, apex=EMULATOR_APEX, store=store
            )
        finally:
            if previous is not None:
                brands[EMULATOR_APEX] = previous
            else:
                brands.pop(EMULATOR_APEX, None)
    finally:
        server.stop()
        await task
