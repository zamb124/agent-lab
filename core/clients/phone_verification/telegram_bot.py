"""Telegram-бот «Поделиться контактом» (contact share).

Провайдер не звонит наружу в момент верификации: пользователь уходит по
deep link `t.me/<bot>?start=<token>`, жмёт «Поделиться номером», и
Telegram присылает update на webhook. `parse_update` валидирует
`contact.user_id == message.from.id` — чужой контакт отклоняется
(`provider_mismatch`), — а номер сравнивается сервисом с `challenge.phone`.

Webхук защищён заголовком `X-Telegram-Bot-Api-Secret-Token`
(конфиг `brands.<apex>.telegram.webhook_secret`, док: core.telegram.org/bots/api#setwebhook).
"""

from __future__ import annotations

from typing import ClassVar

from core.config.models import CustomerAuthTelegramBotConfig
from core.customers.contracts import DirectVerificationRequest, ProviderPhone
from core.customers.enums import (
    CustomerIdentityProvider,
    DirectAuthorizationKind,
    PhoneVerificationErrorCode,
    PhoneVerificationMethod,
)
from core.customers.errors import ProviderError
from core.customers.phone import normalize_phone_e164
from core.http.client import request_public_oauth
from core.types import JsonObject, require_json_object


class TelegramContactProvider:
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.TELEGRAM
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.TELEGRAM_CONTACT
    direct_kind: ClassVar[DirectAuthorizationKind] = DirectAuthorizationKind.CONTACT_SHARE

    def __init__(self, cfg: CustomerAuthTelegramBotConfig | None) -> None:
        self._cfg: CustomerAuthTelegramBotConfig | None = cfg

    def available(self) -> bool:
        c = self._cfg
        return bool(
            c is not None and c.enabled and c.bot_token and c.bot_username
        )

    def contact_link(self, token: str) -> str:
        if not self.available():
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        assert self._cfg is not None
        return f"https://t.me/{self._cfg.bot_username}?start={token}"

    def verify_secret(self, header_token: str | None) -> None:
        """Сверка `X-Telegram-Bot-Api-Secret-Token` с webhook_secret бренда."""
        assert self._cfg is not None
        secret = self._cfg.webhook_secret
        if secret and header_token != secret:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_MISMATCH)

    def parse_start(self, payload: JsonObject) -> tuple[str, str] | None:
        """`message.text == "/start <token>"` → (chat_id, token)."""
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        msg = require_json_object(message, "tg.update.message")
        text = str(msg.get("text") or "")
        if not text.startswith("/start"):
            return None
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return None
        chat = msg.get("chat")
        chat_id = (
            str(require_json_object(chat, "tg.chat").get("id"))
            if isinstance(chat, dict)
            else None
        )
        if chat_id is None:
            return None
        return chat_id, parts[1].strip()

    async def send_contact_request(self, chat_id: str) -> None:
        """`sendMessage` с кнопкой request_contact (Bot API)."""
        assert self._cfg is not None
        if not self._cfg.bot_token:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        url = f"https://api.telegram.org/bot{self._cfg.bot_token}/sendMessage"
        body = {
            "chat_id": chat_id,
            "text": "Нажмите кнопку, чтобы поделиться номером телефона",
            "reply_markup": {
                "keyboard": [
                    [{"text": "Поделиться номером", "request_contact": True}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        }
        try:
            _ = await request_public_oauth("POST", url, json=body, timeout=20.0)
        except Exception as exc:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                f"telegram sendMessage: {exc}",
                retryable=True,
            ) from exc

    def parse_update(self, payload: JsonObject) -> DirectVerificationRequest | None:
        """`message.contact` → доказательство; не contact-сообщение — None."""
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        msg = require_json_object(message, "tg.update.message")
        contact = msg.get("contact")
        if not isinstance(contact, dict):
            return None
        contact_obj = require_json_object(contact, "tg.contact")
        sender = msg.get("from")
        sender_id = (
            str(require_json_object(sender, "tg.from").get("id"))
            if isinstance(sender, dict)
            else None
        )
        contact_user_id = (
            str(contact_obj["user_id"]) if contact_obj.get("user_id") is not None else None
        )
        phone = str(contact_obj.get("phone_number") or "")
        # Контакт должен принадлежать отправителю — иначе это чужой номер.
        if sender_id is None or contact_user_id is None or sender_id != contact_user_id:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_MISMATCH,
                "contact.user_id != from.id",
            )
        if normalize_phone_e164(phone) is None:
            raise ProviderError(PhoneVerificationErrorCode.INVALID_PHONE)
        return DirectVerificationRequest(
            kind=DirectAuthorizationKind.CONTACT_SHARE,
            provider=self.provider,
            contact_phone=phone,
            provider_user_id=sender_id,
            contact_user_id=contact_user_id,
        )

    async def fetch_phones(
        self, proof: DirectVerificationRequest
    ) -> list[ProviderPhone]:
        """Номер уже валидирован webhook'ом; здесь — только E.164 и привязка."""
        if proof.provider_user_id != proof.contact_user_id:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_MISMATCH,
                "contact.user_id != from.id",
            )
        phone = normalize_phone_e164(proof.contact_phone or "")
        if phone is None:
            raise ProviderError(PhoneVerificationErrorCode.INVALID_PHONE)
        return [ProviderPhone(phone_e164=phone, verified=True, default=True)]
