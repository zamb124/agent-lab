"""E2E протоколов провайдеров customer-auth через реальный HTTP-эмулятор.

Без моков и monkeypatch: apex ``linnex.io`` получает бренд-конфиг с
endpoint'ами на локальный Granian-эмулятор
(``tests/fixtures/phone_verification_emulator``), и прод-клиенты провайдеров
ходят в него по официальным протоколам Telegram Bot API, MAX Bot API,
Yandex ID, VK ID (PKCE), Sber ID (OIDC) и SMS.RU — end-to-end.

Стек: реальный Postgres + Redis + полный shop app (ASGI transport).
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient, Response

from apps.shop.di import ShopDi
from core.config import get_settings
from core.customers.challenge import PhoneChallenge
from tests.fixtures.phone_verification_emulator.handle import (
    MAX_ACCESS_TOKEN,
    MAX_WEBHOOK_SECRET,
    TG_WEBHOOK_SECRET,
    PhoneVerificationEmulatorHandle,
)

_AUTH = "/shop/api/v1/public/customer-auth"
_COMPANY = "cmp_auth_e2e"


def _phone(unique_id: str, tag: int = 0) -> str:
    """Уникальный E.164 на тест: start-лимит считается по номеру на час."""
    return f"+7999{(int(unique_id[:7], 16) + tag) % 10**7:07d}"


async def _start(client: AsyncClient, company_id: str, phone: str) -> dict:
    resp = await client.post(
        f"{_AUTH}/start", json={"company_id": company_id, "phone": phone}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def _choose(
    client: AsyncClient, challenge_id: str, company_id: str, method: str, **extra: str
) -> Response:
    return await client.post(
        f"{_AUTH}/method",
        json={
            "challenge_id": challenge_id,
            "company_id": company_id,
            "method": method,
            **extra,
        },
    )


async def _verify(
    client: AsyncClient, challenge_id: str, company_id: str, **payload: object
) -> Response:
    return await client.post(
        f"{_AUTH}/verify",
        json={"challenge_id": challenge_id, "company_id": company_id, **payload},
    )


async def _challenge(di: ShopDi, challenge_id: str) -> PhoneChallenge:
    challenge = await PhoneChallenge.load(di.redis_client, challenge_id)
    assert challenge is not None
    return challenge


def _sent_code(store_requests: list[dict[str, str]], index: int = -1) -> str:
    """Код из текста SMS, записанного эмулятором (msg="Ваш код: 123456")."""
    msg = store_requests[index].get("msg", "")
    match = re.search(r"(\d{6})", msg)
    assert match is not None, f"no code in sms msg: {msg!r}"
    return match.group(1)


def _emu_code(challenge: PhoneChallenge) -> str:
    """Код, «доставленный» эмуляторным sender'ом (provider_message_id)."""
    msg_id = challenge.provider_data.get("provider_message_id", "")
    assert msg_id.startswith("emu-")
    return msg_id.removeprefix("emu-")


# --- fixtures ---------------------------------------------------------------


@pytest_asyncio.fixture
async def emu_client(
    shop_app, shop_di, unique_id: str, phone_verification_emulator
) -> AsyncIterator[AsyncClient]:
    """Анонимный клиент в apex ``linnex.io`` (бренд → эмулятор провайдеров).

    Уникальный source IP на тест — лимиты по IP не пересекаются между тестами.
    """
    _ = shop_di, phone_verification_emulator
    n = int(unique_id[:8], 16)
    ip = f"198.51.100.{n % 254 + 1}"
    transport = ASGITransport(app=shop_app, client=(ip, 1234))
    async with AsyncClient(transport=transport, base_url="http://linnex.io") as c:
        yield c


@pytest_asyncio.fixture
async def lvh_client(shop_app, shop_di, unique_id: str) -> AsyncIterator[AsyncClient]:
    """Клиент в apex ``lvh.me`` — бренд не сконфигурирован (только эмулятор)."""
    _ = shop_di
    n = int(unique_id[:8], 16)
    ip = f"198.52.100.{n % 254 + 1}"
    transport = ASGITransport(app=shop_app, client=(ip, 1234))
    async with AsyncClient(transport=transport, base_url="http://e2e.lvh.me") as c:
        yield c


# --- start / методы ---------------------------------------------------------


class TestStart:
    async def test_methods_all_providers(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        assert start["challenge_id"].startswith("phc_")
        assert start["phone_masked"] and "+7" in start["phone_masked"]
        kinds = [m["kind"] for m in start["methods"]]
        assert kinds == [
            "telegram_contact",
            "max_contact",
            "yandex_id",
            "vk_id",
            "sber_id",
            "sms_code",
            "emulator",
        ]
        ui = {m["kind"]: m["ui"] for m in start["methods"]}
        assert ui["telegram_contact"] == "contact_share"
        assert ui["yandex_id"] == "oauth"
        assert ui["sms_code"] == "code_input"
        assert ui["emulator"] == "auto"

    async def test_phone_normalization(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        raw = f"8 (999) {(int(unique_id[:7], 16)) % 10**7:07d}"
        start = await _start(emu_client, _COMPANY, raw)
        assert "+7" in start["phone_masked"]

    async def test_invalid_phone(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.post(
            f"{_AUTH}/start", json={"company_id": _COMPANY, "phone": "123"}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_phone"

    async def test_start_without_phone(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.post(f"{_AUTH}/start", json={"company_id": _COMPANY})
        assert resp.status_code == 200, resp.text

    async def test_rate_limit_per_phone(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        phone = _phone(unique_id)
        for _ in range(10):
            resp = await emu_client.post(
                f"{_AUTH}/start", json={"company_id": _COMPANY, "phone": phone}
            )
            assert resp.status_code == 200, resp.text
        resp = await emu_client.post(
            f"{_AUTH}/start", json={"company_id": _COMPANY, "phone": phone}
        )
        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate_limited"

    async def test_rate_limit_per_ip(
        self, shop_app, shop_di, unique_id: str, phone_verification_emulator
    ) -> None:
        """30 стартов с разных номеров с одного IP → 31-й 429."""
        _ = shop_di, phone_verification_emulator
        # IP уникален на вызов: rate-счётчики живут в Redis 1ч между прогонами.
        n = int(unique_id[:8], 16)
        ip = f"{n % 200 + 10}.{(n >> 8) % 254 + 1}.{(n >> 16) % 254 + 1}.77"
        transport = ASGITransport(app=shop_app, client=(ip, 5555))
        async with AsyncClient(transport=transport, base_url="http://linnex.io") as c:
            for i in range(30):
                resp = await c.post(
                    f"{_AUTH}/start",
                    json={"company_id": _COMPANY, "phone": _phone(unique_id, i + 1)},
                )
                assert resp.status_code == 200, f"#{i}: {resp.text}"
            resp = await c.post(
                f"{_AUTH}/start",
                json={"company_id": _COMPANY, "phone": _phone(unique_id, 99)},
            )
            assert resp.status_code == 429

    async def test_unconfigured_brand_only_emulator(
        self, lvh_client: AsyncClient, unique_id: str
    ) -> None:
        """Бренд без провайдеров: доступны sms_code (эмулятор-sender) и emulator."""
        start = await _start(lvh_client, _COMPANY, _phone(unique_id))
        kinds = {m["kind"] for m in start["methods"]}
        assert kinds == {"sms_code", "emulator"}

    async def test_provider_not_configured(
        self, lvh_client: AsyncClient, unique_id: str
    ) -> None:
        start = await _start(lvh_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            lvh_client, start["challenge_id"], _COMPANY, "telegram_contact"
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == "provider_not_configured"


# --- SMS.RU / код ------------------------------------------------------------


class TestSmsCode:
    async def test_sms_send_official_request(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone = _phone(unique_id)
        start = await _start(emu_client, _COMPANY, phone)
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["status"] == "challenge_sent"
        assert view["channel"] == "sms"
        assert view["resend_after"] == 60
        assert view["expires_in"] == 300
        reqs = phone_verification_emulator.store.sms_requests
        assert len(reqs) == 1
        assert reqs[0]["to"] == phone.lstrip("+")
        assert reqs[0]["api_id"]
        assert reqs[0]["json"] == "1"
        assert re.fullmatch(r"Ваш код: \d{6}", reqs[0]["msg"])

    async def test_verify_correct_code(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone = _phone(unique_id)
        start = await _start(emu_client, _COMPANY, phone)
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200, resp.text
        code = _sent_code(phone_verification_emulator.store.sms_requests)
        resp = await _verify(
            emu_client, start["challenge_id"], _COMPANY, code=code
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["customer"]["phone_e164"] == phone
        assert "customer_token" in resp.cookies
        me = await emu_client.get(f"{_AUTH}/me")
        assert me.status_code == 200
        assert me.json()["customer_id"] == body["customer"]["customer_id"]

    async def test_wrong_code_then_attempts_exceeded(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone = _phone(unique_id)
        start = await _start(emu_client, _COMPANY, phone)
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200
        real_code = _sent_code(phone_verification_emulator.store.sms_requests)
        wrong = "000000" if real_code != "000000" else "111111"
        for attempt in range(4):
            resp = await _verify(
                emu_client, start["challenge_id"], _COMPANY, code=wrong
            )
            assert resp.status_code == 400, f"attempt {attempt}: {resp.text}"
            assert resp.json()["detail"] == "code_invalid"
        resp = await _verify(emu_client, start["challenge_id"], _COMPANY, code=wrong)
        assert resp.status_code == 429
        assert resp.json()["detail"] == "attempts_exceeded"
        # Следующий вызов помечает challenge failed — верный код не принимается.
        resp = await _verify(
            emu_client, start["challenge_id"], _COMPANY, code=real_code
        )
        assert resp.status_code == 429
        resp = await _verify(
            emu_client, start["challenge_id"], _COMPANY, code=real_code
        )
        assert resp.status_code == 410
        assert resp.json()["detail"] == "challenge_expired"

    async def test_inner_207_not_deliverable(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone_verification_emulator.store.sms_inner_status_code = 207
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "not_deliverable"

    async def test_provider_failure_falls_back_to_emulator(
        self,
        emu_client: AsyncClient,
        shop_di,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """SMS.RU вернул отказ (retryable) → каскада дошла до emulator sender."""
        phone_verification_emulator.store.sms_top_status_code = 500
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200, resp.text
        challenge = await _challenge(shop_di, start["challenge_id"])
        assert challenge.provider_data.get("sender") == "emulator"
        code = _emu_code(challenge)
        resp = await _verify(
            emu_client, start["challenge_id"], _COMPANY, code=code
        )
        assert resp.status_code == 200, resp.text

    async def test_resend_issues_new_code(
        self,
        emu_client: AsyncClient,
        shop_di,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        cid = start["challenge_id"]
        resp = await _choose(emu_client, cid, _COMPANY, "sms_code")
        assert resp.status_code == 200
        first = _sent_code(phone_verification_emulator.store.sms_requests, 0)
        resp = await _choose(emu_client, cid, _COMPANY, "sms_code")
        assert resp.status_code == 200
        second = _sent_code(phone_verification_emulator.store.sms_requests, 1)
        assert len(phone_verification_emulator.store.sms_requests) == 2
        resp = await _verify(emu_client, cid, _COMPANY, code=first)
        assert resp.status_code == 400  # старый код перезаписан
        resp = await _verify(emu_client, cid, _COMPANY, code=second)
        assert resp.status_code == 200, resp.text

    async def test_send_limit_per_phone(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """sends_per_phone_day=20: повторный method на одном challenge → 21-й 429."""
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        cid = start["challenge_id"]
        for i in range(20):
            resp = await _choose(emu_client, cid, _COMPANY, "sms_code")
            assert resp.status_code == 200, f"#{i}: {resp.text}"
        resp = await _choose(emu_client, cid, _COMPANY, "sms_code")
        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate_limited"

    async def test_platform_budget_spent(
        self,
        emu_client: AsyncClient,
        shop_di,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """Стоимость SMS списывается из дневного бюджета платформы."""
        import time

        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200
        day = time.strftime("%Y%m%d", time.gmtime())
        spent = await shop_di.redis_client.get(f"cust_auth:budget:{day}")
        assert spent is not None and int(spent) >= 40  # 0.40 ₽

    async def test_budget_exhausted_blocks_sms(
        self,
        emu_client: AsyncClient,
        unique_id: str,
    ) -> None:
        cfg = get_settings().customer_auth
        prev = cfg.daily_budget_rub
        cfg.daily_budget_rub = 0
        try:
            start = await _start(emu_client, _COMPANY, _phone(unique_id))
            resp = await _choose(
                emu_client, start["challenge_id"], _COMPANY, "sms_code"
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "provider_unavailable"
        finally:
            cfg.daily_budget_rub = prev

    async def test_verify_wrong_company_scope(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "sms_code"
        )
        assert resp.status_code == 200
        code = _sent_code(phone_verification_emulator.store.sms_requests)
        resp = await _verify(
            emu_client, start["challenge_id"], "cmp_other", code=code
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "forbidden_scope"

    async def test_verify_unknown_challenge(self, emu_client: AsyncClient) -> None:
        resp = await _verify(emu_client, "phc_missing", _COMPANY, code="123456")
        assert resp.status_code == 410

    async def test_verify_no_proof(self, emu_client: AsyncClient, unique_id: str) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _verify(emu_client, start["challenge_id"], _COMPANY)
        assert resp.status_code == 400


# --- Telegram webhook ---------------------------------------------------------


def _tg_update_start(token: str, *, chat_id: int = 777001, update_id: int = 100) -> dict:
    """Официальный Update Bot API: `message.text = "/start <token>"`."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": chat_id, "is_bot": False, "first_name": "Иван"},
            "chat": {"id": chat_id, "first_name": "Иван", "type": "private"},
            "date": 1700000000,
            "text": f"/start {token}",
        },
    }


def _tg_update_contact(phone: str, *, user_id: int = 777001, contact_user_id: int | None = None, update_id: int = 101) -> dict:
    """Официальный Update Bot API с `message.contact` (shared contact)."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 2,
            "from": {"id": user_id, "is_bot": False, "first_name": "Иван"},
            "chat": {"id": user_id, "first_name": "Иван", "type": "private"},
            "date": 1700000001,
            "contact": {
                "phone_number": phone,
                "first_name": "Иван",
                "user_id": contact_user_id if contact_user_id is not None else user_id,
            },
        },
    }


class TestTelegramContact:
    async def _begin(
        self, client: AsyncClient, unique_id: str
    ) -> tuple[dict, str, str]:
        phone = _phone(unique_id)
        start = await _start(client, _COMPANY, phone)
        resp = await _choose(
            client, start["challenge_id"], _COMPANY, "telegram_contact"
        )
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["status"] == "awaiting_contact"
        link = view["deep_link"]
        assert link.startswith("https://t.me/linnex_emulator_bot?start=")
        return start, phone, link.rsplit("=", 1)[1]

    async def test_full_contact_share_flow(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        start, phone, token = await self._begin(emu_client, unique_id)
        # Пользователь открыл бота: /start <token> с правильным secret header.
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_start(token),
            headers={"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET},
        )
        assert resp.status_code == 200, resp.text
        # Бот прислал кнопку request_contact — вызов зафиксирован эмулятором.
        sent = phone_verification_emulator.store.telegram_messages
        assert len(sent) == 1
        kb = sent[0]["reply_markup"]["keyboard"][0][0]
        assert kb["request_contact"] is True
        assert sent[0]["chat_id"] == "777001"
        # Пользователь поделился своим контактом.
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_contact(phone),
            headers={"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET},
        )
        assert resp.status_code == 200, resp.text
        # Polling видит подтверждение и ставит cookie.
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": start["challenge_id"], "company_id": _COMPANY},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["customer"]["phone_e164"] == phone
        assert "customer_token" in resp.cookies
        me = await emu_client.get(f"{_AUTH}/me")
        assert me.status_code == 200

    async def test_wrong_secret_rejected(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start, _, token = await self._begin(emu_client, unique_id)
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_start(token),
            headers={"x-telegram-bot-api-secret-token": "wrong"},
        )
        assert resp.status_code == 409

    async def test_missing_secret_rejected(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start, _, token = await self._begin(emu_client, unique_id)
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram", json=_tg_update_start(token)
        )
        assert resp.status_code == 409

    async def test_foreign_contact_rejected(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        """contact.user_id != message.from.id → чужой контакт отклонён."""
        start, phone, token = await self._begin(emu_client, unique_id)
        headers = {"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET}
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram", json=_tg_update_start(token), headers=headers
        )
        assert resp.status_code == 200
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_contact(phone, contact_user_id=999999),
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "provider_mismatch"

    async def test_contact_phone_mismatch(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        """Номер контакта не совпал с номером challenge → provider_mismatch."""
        start, _, token = await self._begin(emu_client, unique_id)
        headers = {"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET}
        _ = await emu_client.post(
            f"{_AUTH}/webhooks/telegram", json=_tg_update_start(token), headers=headers
        )
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_contact("+79990000001"),
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "provider_mismatch"

    async def test_contact_invalid_phone(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start, _, token = await self._begin(emu_client, unique_id)
        headers = {"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET}
        _ = await emu_client.post(
            f"{_AUTH}/webhooks/telegram", json=_tg_update_start(token), headers=headers
        )
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_contact("not-a-phone"),
            headers=headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_phone"

    async def test_unknown_start_token_ignored(
        self, emu_client: AsyncClient, phone_verification_emulator: PhoneVerificationEmulatorHandle
    ) -> None:
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_start("unknown-token"),
            headers={"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET},
        )
        assert resp.status_code == 200
        assert phone_verification_emulator.store.telegram_messages == []

    async def test_polling_updates_flow(
        self,
        emu_client: AsyncClient,
        shop_di: ShopDi,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """getUpdates-поллинг: контракт тот же, что webhook.

        Продуктовый сценарий: хост без входящего доступа от api.telegram.org
        (`polling_enabled`) — таска `customer_auth_tg_poll` тянет updates
        long-poll'ом; webhook при этом снимается (иначе 409 Conflict).
        """
        start, phone, token = await self._begin(emu_client, unique_id)
        store = phone_verification_emulator.store
        # offset живёт в Redis между прогонами — id монотонны по wall-clock.
        base_id = int(time.time() * 1000)
        store.telegram_updates.extend(
            [
                _tg_update_start(token, update_id=base_id),
                _tg_update_contact(phone, update_id=base_id + 1),
            ]
        )
        processed = await shop_di.customer_auth_service.poll_telegram_updates(
            budget_seconds=0.5
        )
        assert processed == 2
        assert store.telegram_webhook_deleted == 1
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": start["challenge_id"], "company_id": _COMPANY},
        )
        assert resp.json()["status"] == "confirmed"

    async def test_contact_without_start_ignored(
        self, emu_client: AsyncClient
    ) -> None:
        """Контакт от пользователя без /start — молча игнорируется (200)."""
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/telegram",
            json=_tg_update_contact("+79990001122", user_id=555),
            headers={"x-telegram-bot-api-secret-token": TG_WEBHOOK_SECRET},
        )
        assert resp.status_code == 200

    async def test_unknown_provider_404(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/nosuch", json={"update_id": 1}
        )
        assert resp.status_code == 404


# --- MAX webhook --------------------------------------------------------------


def _max_update_start(token: str, *, user_id: int = 888001) -> dict:
    """Официальный MAX update: update_type=message_created, body.text=/start."""
    return {
        "update_type": "message_created",
        "timestamp": 1700000000000,
        "message": {
            "sender": {"user_id": user_id, "first_name": "Иван", "is_bot": False},
            "recipient": {"chat_id": user_id, "chat_type": "dialog", "user_id": user_id},
            "timestamp": 1700000000000,
            "body": {"mid": "mid.1", "seq": 1, "text": f"/start {token}", "attachments": []},
        },
    }


def _max_update_bot_started(token: str, *, user_id: int = 888001) -> dict:
    """Официальный MAX update `bot_started`: deep link `?start=<token>`.

    Токен приезжает в поле `payload`, `chat_id` — на верхнем уровне update;
    `message.body.text` при этом пуст (команды /start в ленте нет).
    """
    return {
        "update_type": "bot_started",
        "timestamp": 1700000000000,
        "chat_id": user_id,
        "user": {"user_id": user_id, "first_name": "Иван", "is_bot": False},
        "payload": token,
    }


def _max_update_contact(phone: str, *, user_id: int = 888001, with_binding: bool = True) -> dict:
    """MAX update с вложением contact: vcf_info + hash (owner binding, офиц. контракт)."""
    payload: dict = {
        "name": "Иван",
        "vcf_info": (
            "BEGIN:VCARD\r\nVERSION:3.0\r\nTEL;TYPE=cell:"
            + phone.lstrip("+")
            + "\r\nFN:Иван\r\nEND:VCARD\r\n"
        ),
    }
    if with_binding:
        payload["hash"] = "emu-hash-" + str(user_id)
    return {
        "update_type": "message_created",
        "timestamp": 1700000000001,
        "message": {
            "sender": {"user_id": user_id, "first_name": "Иван", "is_bot": False},
            "recipient": {"chat_id": user_id, "chat_type": "dialog", "user_id": user_id},
            "timestamp": 1700000000001,
            "body": {
                "mid": "mid.2",
                "seq": 2,
                "text": "",
                "attachments": [{"type": "contact", "payload": payload}],
            },
        },
    }


class TestMaxContact:
    async def _begin(
        self, client: AsyncClient, unique_id: str
    ) -> tuple[dict, str, str]:
        phone = _phone(unique_id)
        start = await _start(client, _COMPANY, phone)
        resp = await _choose(client, start["challenge_id"], _COMPANY, "max_contact")
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["status"] == "awaiting_contact"
        link = view["deep_link"]
        assert link.startswith("https://max.ru/linnex_emu_bot?start=")
        return start, phone, link.rsplit("=", 1)[1]

    async def test_full_contact_share_flow(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        start, phone, token = await self._begin(emu_client, unique_id)
        headers = {"x-max-bot-api-secret": MAX_WEBHOOK_SECRET}
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max", json=_max_update_start(token), headers=headers
        )
        assert resp.status_code == 200, resp.text
        sent = phone_verification_emulator.store.max_messages
        assert len(sent) == 1
        params, body = sent[0]
        assert params["chat_id"] == "888001"
        # Официальный контракт: токен в Authorization header, не в query.
        assert "access_token" not in params
        assert phone_verification_emulator.store.max_authorization == [MAX_ACCESS_TOKEN]
        kb = body["attachments"][0]["payload"]["buttons"][0][0]
        assert kb["type"] == "request_contact"
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max", json=_max_update_contact(phone), headers=headers
        )
        assert resp.status_code == 200, resp.text
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": start["challenge_id"], "company_id": _COMPANY},
        )
        assert resp.json()["status"] == "confirmed"

    async def test_bot_started_flow(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """Deep link `max.ru/<bot>?start=<token>` → update bot_started.

        Именно этот update приходит на проде при переходе по QR/deep link —
        `message.body.text` у него пуст, парсер обязан читать `payload`.
        """
        start, phone, token = await self._begin(emu_client, unique_id)
        headers = {"x-max-bot-api-secret": MAX_WEBHOOK_SECRET}
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max",
            json=_max_update_bot_started(token),
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        sent = phone_verification_emulator.store.max_messages
        assert len(sent) == 1
        params, body = sent[0]
        assert params["chat_id"] == "888001"
        kb = body["attachments"][0]["payload"]["buttons"][0][0]
        assert kb["type"] == "request_contact"
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max", json=_max_update_contact(phone), headers=headers
        )
        assert resp.status_code == 200, resp.text
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": start["challenge_id"], "company_id": _COMPANY},
        )
        assert resp.json()["status"] == "confirmed"

    async def test_wrong_secret_rejected(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start, _, token = await self._begin(emu_client, unique_id)
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max",
            json=_max_update_start(token),
            headers={"x-max-bot-api-secret": "wrong"},
        )
        assert resp.status_code == 409

    async def test_contact_without_binding_rejected(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        """Контакт без hash — номер не привязан к аккаунту (контакт «из книги»)."""
        start, phone, token = await self._begin(emu_client, unique_id)
        headers = {"x-max-bot-api-secret": MAX_WEBHOOK_SECRET}
        _ = await emu_client.post(
            f"{_AUTH}/webhooks/max", json=_max_update_start(token), headers=headers
        )
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max",
            json=_max_update_contact(phone, with_binding=False),
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_contact_phone_mismatch(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start, _, token = await self._begin(emu_client, unique_id)
        headers = {"x-max-bot-api-secret": MAX_WEBHOOK_SECRET}
        _ = await emu_client.post(
            f"{_AUTH}/webhooks/max", json=_max_update_start(token), headers=headers
        )
        resp = await emu_client.post(
            f"{_AUTH}/webhooks/max",
            json=_max_update_contact("+79990000002"),
            headers=headers,
        )
        assert resp.status_code == 409


# --- OAuth ID -----------------------------------------------------------------


class TestOAuth:
    async def _callback_from_oauth_url(
        self, client: AsyncClient, oauth_url: str
    ) -> Response:
        """Прогон браузера: GET authorize у эмулятора → 302 → GET callback."""
        parsed = urlparse(oauth_url)
        emu = AsyncClient(base_url=f"{parsed.scheme}://{parsed.netloc}")
        try:
            resp = await emu.get(oauth_url)
            assert resp.status_code == 302, resp.text
            location = resp.headers["location"]
            assert "error=" not in location, location
            cb = urlparse(location)
            qs = parse_qs(cb.query)
            assert qs.get("code") and qs.get("state")
            # callback_base: https://linnex.io<path> → path на нашем app.
            return await client.get(f"{cb.path}?{cb.query}")
        finally:
            await emu.aclose()

    @pytest.mark.parametrize(
        "provider,method",
        [("yandex", "yandex_id"), ("vk", "vk_id"), ("sber", "sber_id")],
    )
    async def test_full_oauth_flow(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        provider: str,
        method: str,
        unique_id: str,
    ) -> None:
        phone = _phone(unique_id)
        phone_verification_emulator.store.seed_oauth(
            provider, phone=phone, user_id=f"u_{provider}_1"
        )
        start = await _start(emu_client, _COMPANY, phone)
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, method,
            return_url="https://linnex.io/back",
        )
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["status"] == "awaiting_oauth"
        url = view["oauth_url"]
        q = parse_qs(urlparse(url).query)
        assert q["response_type"] == ["code"]
        assert q["client_id"] == ["emu-client-id"]
        assert q["state"] and q["redirect_uri"]
        assert q["code_challenge"] and q["code_challenge_method"] == ["S256"]
        resp = await self._callback_from_oauth_url(emu_client, url)
        # Колбэк возвращает closer-страницу: postMessage opener'у (popup) либо
        # JS-redirect на return_url — cookie ставится на оба пути.
        assert resp.status_code == 200, resp.text
        assert 'var RET = "https:\\/\\/linnex.io\\/back"' in resp.text or (
            'var RET = "https://linnex.io/back"' in resp.text
        )
        assert "customer-auth-done" in resp.text
        assert "location.replace" in resp.text
        assert "customer_token" in resp.cookies
        # Token exchange пошёл в эмулятор по официальному контракту.
        token_req = phone_verification_emulator.store.token_requests[provider][-1]
        assert token_req["grant_type"] == "authorization_code"
        assert token_req["client_id"] == "emu-client-id"
        assert token_req["client_secret"] == "emu-client-secret"
        if provider == "vk":
            assert token_req.get("code_verifier")
        me = await emu_client.get(f"{_AUTH}/me")
        assert me.status_code == 200
        assert me.json()["phone_e164"] == phone

    async def test_state_mismatch(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "yandex_id"
        )
        assert resp.status_code == 200
        resp = await emu_client.get(
            f"{_AUTH}/oauth/yandex/callback",
            params={"code": "oc_fake", "state": "forged-state"},
        )
        assert resp.status_code == 410

    async def test_missing_callback_params(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.get(f"{_AUTH}/oauth/yandex/callback")
        assert resp.status_code == 400

    async def test_unknown_oauth_provider(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.get(
            f"{_AUTH}/oauth/nosuch/callback", params={"code": "c", "state": "s"}
        )
        assert resp.status_code == 400

    async def test_account_without_phone(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """Аккаунт провайдера без верифицированного номера → provider_mismatch."""
        phone_verification_emulator.store.seed_oauth(
            "yandex", phone=None, user_id="u_nophone"
        )
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "yandex_id"
        )
        url = resp.json()["oauth_url"]
        resp = await self._callback_from_oauth_url(emu_client, url)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "provider_mismatch"

    async def test_phone_mismatch(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone_verification_emulator.store.seed_oauth(
            "sber", phone="+79990000003", user_id="u_other"
        )
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(emu_client, start["challenge_id"], _COMPANY, "sber_id")
        resp = await self._callback_from_oauth_url(emu_client, resp.json()["oauth_url"])
        assert resp.status_code == 409

    async def test_token_exchange_failure(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        phone_verification_emulator.store.seed_oauth(
            "yandex", phone=_phone(unique_id), user_id="u_fail"
        )
        phone_verification_emulator.store.oauth_token_fail["yandex"] = 500
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "yandex_id"
        )
        resp = await self._callback_from_oauth_url(emu_client, resp.json()["oauth_url"])
        assert resp.status_code == 503
        assert resp.json()["detail"] == "provider_unavailable"

    async def test_no_account_denies_at_authorize(
        self,
        emu_client: AsyncClient,
        unique_id: str,
    ) -> None:
        """Провайдер отказал в доступе: authorize → error=access_denied."""
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "vk_id"
        )
        url = resp.json()["oauth_url"]
        parsed = urlparse(url)
        async with AsyncClient(base_url=f"{parsed.scheme}://{parsed.netloc}") as emu:
            resp = await emu.get(url)
            assert resp.status_code == 302
            assert "error=access_denied" in resp.headers["location"]

    async def test_yandex_scope_is_default_phone(
        self,
        emu_client: AsyncClient,
        unique_id: str,
    ) -> None:
        """Контракт: запрашиваем только `login:default_phone` (право «номер телефона»)."""
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "yandex_id"
        )
        url = resp.json()["oauth_url"]
        q = parse_qs(urlparse(url).query)
        assert q["scope"] == ["login:default_phone"]

    async def test_yandex_invalid_scope_rejected_by_provider(
        self,
        emu_client: AsyncClient,
        phone_verification_emulator: PhoneVerificationEmulatorHandle,
        unique_id: str,
    ) -> None:
        """Регрессия прода: клиент без права на scope → `error=invalid_scope`."""
        phone_verification_emulator.store.seed_oauth(
            "yandex", phone=_phone(unique_id), user_id="u_scope_denied"
        )
        phone_verification_emulator.store.allowed_scopes["yandex"] = {"login:info"}
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await _choose(
            emu_client, start["challenge_id"], _COMPANY, "yandex_id"
        )
        url = resp.json()["oauth_url"]
        parsed = urlparse(url)
        async with AsyncClient(base_url=f"{parsed.scheme}://{parsed.netloc}") as emu:
            resp = await emu.get(url)
            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "error=invalid_scope" in location
            cb = urlparse(location)
            # Redirect без code приводит на callback → oauth_params_required.
            resp = await emu_client.get(f"{cb.path}?{cb.query}")
            assert resp.status_code == 400


# --- Эмуляторный direct / сессия ----------------------------------------------


class TestEmulatorAndSession:
    async def test_emulator_direct_verify(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        phone = _phone(unique_id)
        start = await _start(emu_client, _COMPANY, phone)
        resp = await _choose(emu_client, start["challenge_id"], _COMPANY, "emulator")
        assert resp.status_code == 200
        resp = await _verify(
            emu_client,
            start["challenge_id"],
            _COMPANY,
            direct={
                "kind": "contact_share",
                "provider": "emulator",
                "contact_phone": phone,
            },
        )
        assert resp.status_code == 200
        me = await emu_client.get(f"{_AUTH}/me")
        assert me.status_code == 200
        assert me.json()["scope_company_id"] == _COMPANY

    async def test_emulator_phone_mismatch(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        _ = await _choose(emu_client, start["challenge_id"], _COMPANY, "emulator")
        resp = await _verify(
            emu_client,
            start["challenge_id"],
            _COMPANY,
            direct={
                "kind": "contact_share",
                "provider": "emulator",
                "contact_phone": "+79990000009",
            },
        )
        assert resp.status_code == 409

    async def test_me_unauthorized(self, emu_client: AsyncClient) -> None:
        resp = await emu_client.get(f"{_AUTH}/me")
        assert resp.status_code == 401

    async def test_invalid_cookie(
        self, emu_client: AsyncClient
    ) -> None:
        emu_client.cookies.set("customer_token", "forged-token", domain="linnex.io")
        resp = await emu_client.get(f"{_AUTH}/me")
        assert resp.status_code == 401

    async def test_logout_clears_session(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        phone = _phone(unique_id)
        start = await _start(emu_client, _COMPANY, phone)
        _ = await _choose(emu_client, start["challenge_id"], _COMPANY, "emulator")
        _ = await _verify(
            emu_client,
            start["challenge_id"],
            _COMPANY,
            direct={
                "kind": "contact_share",
                "provider": "emulator",
                "contact_phone": phone,
            },
        )
        resp = await emu_client.post(f"{_AUTH}/logout")
        assert resp.status_code == 200
        resp = await emu_client.get(f"{_AUTH}/me")
        assert resp.status_code == 401

    async def test_status_unknown_challenge_expired(
        self, emu_client: AsyncClient
    ) -> None:
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": "phc_missing", "company_id": _COMPANY},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"

    async def test_status_wrong_company(
        self, emu_client: AsyncClient, unique_id: str
    ) -> None:
        start = await _start(emu_client, _COMPANY, _phone(unique_id))
        resp = await emu_client.get(
            f"{_AUTH}/status",
            params={"challenge_id": start["challenge_id"], "company_id": "cmp_other"},
        )
        assert resp.status_code == 403
