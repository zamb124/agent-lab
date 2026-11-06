"""MAX-бот «Поделиться контактом» (request_contact, dev.max.ru).

Протокол аналогичен Telegram: deep link → кнопка «Поделиться номером» →
webhook update с `contact` и `vcf_info`/hash, связывающим номер с аккаунтом.
Канал выключен по умолчанию (`brands.<apex>.max.enabled=false`) — включается
после верификационного спайка протокола (customers.mdc § Инварианты).
"""

from __future__ import annotations

import re
from typing import ClassVar

from core.clients.phone_verification.base import credential_configured
from core.config.models import CustomerAuthMaxBotConfig
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

_VCF_TEL = re.compile(r"TEL[^:\r\n]*:([+\d][\d\s\-()]{5,20})")


def _phone_from_vcf(vcf_info: str) -> str | None:
    """`vcf_info` контакта — VCF-текст, номер в строке `TEL;TYPE=...:<num>`."""
    if not vcf_info:
        return None
    match = _VCF_TEL.search(vcf_info)
    if match is None:
        return None
    return normalize_phone_e164(match.group(1))


class MaxContactProvider:
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.MAX
    method: ClassVar[PhoneVerificationMethod] = PhoneVerificationMethod.MAX_CONTACT
    direct_kind: ClassVar[DirectAuthorizationKind] = DirectAuthorizationKind.CONTACT_SHARE

    def __init__(self, cfg: CustomerAuthMaxBotConfig | None) -> None:
        self._cfg: CustomerAuthMaxBotConfig | None = cfg

    def available(self) -> bool:
        c = self._cfg
        return bool(
            c is not None
            and c.enabled
            and credential_configured(c.access_token)
            and credential_configured(c.bot_name)
        )

    def contact_link(self, token: str) -> str:
        if not self.available():
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        assert self._cfg is not None
        return f"https://max.ru/{self._cfg.bot_name}?start={token}"

    def verify_secret(self, header_token: str | None) -> None:
        assert self._cfg is not None
        secret = self._cfg.webhook_secret
        if not secret or header_token != secret:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_MISMATCH)

    def parse_start(self, payload: JsonObject) -> tuple[str, str] | None:
        """Старт сессии → (chat_id, token).

        Deep link `max.ru/<bot>?start=<token>` производит update
        `bot_started` с токеном в `payload` и `chat_id` верхнего уровня;
        ручной ввод `/start <token>` приходит как `message_created` с
        `message.body.text`.
        """
        if payload.get("update_type") == "bot_started":
            token = str(payload.get("payload") or "").strip()
            chat_id = str(payload.get("chat_id") or "")
            if not token or not chat_id:
                return None
            return chat_id, token
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        msg = require_json_object(message, "max.update.message")
        body = msg.get("body")
        recipient = msg.get("recipient")
        text = ""
        if isinstance(body, dict):
            text = str(require_json_object(body, "max.body").get("text") or "")
        if not text.startswith("/start"):
            return None
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return None
        chat_id = (
            str(require_json_object(recipient, "max.recipient").get("chat_id"))
            if isinstance(recipient, dict)
            else None
        )
        if chat_id is None:
            return None
        return chat_id, parts[1].strip()

    async def send_contact_request(self, chat_id: str) -> None:
        """`POST /messages` с клавиатурой request_contact (botapi.max.ru)."""
        assert self._cfg is not None
        if not self._cfg.access_token:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        body = {
            "text": "Нажмите кнопку, чтобы поделиться номером телефона",
            "attachments": [
                {
                    "type": "inline_keyboard",
                    "payload": {
                        "buttons": [
                            [
                                {
                                    "type": "request_contact",
                                    "text": "Поделиться номером",
                                }
                            ]
                        ]
                    },
                }
            ],
        }
        try:
            _ = await request_public_oauth(
                "POST",
                f"{self._cfg.api_base_url}/messages",
                params={"chat_id": chat_id},
                headers={"Authorization": self._cfg.access_token},
                json=body,
                timeout=20.0,
            )
        except Exception as exc:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                f"max sendMessage: {exc}",
                retryable=True,
            ) from exc

    async def set_webhook(self, url: str, secret: str) -> None:
        """`POST /subscriptions` — подписка webhook; Authorization header, идемпотентно."""
        assert self._cfg is not None
        if not self._cfg.access_token:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        try:
            _ = await request_public_oauth(
                "POST",
                f"{self._cfg.api_base_url}/subscriptions",
                headers={"Authorization": self._cfg.access_token},
                json={
                    "url": url,
                    "update_types": ["bot_started", "message_created"],
                    "secret": secret,
                },
                timeout=20.0,
            )
        except Exception as exc:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                f"max setWebhook: {exc}",
                retryable=True,
            ) from exc

    def parse_update(self, payload: JsonObject) -> DirectVerificationRequest | None:
        """`message.body.attachments[contact]` → доказательство."""
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        msg = require_json_object(message, "max.update.message")
        body = msg.get("body")
        sender = msg.get("sender")
        if not isinstance(body, dict) or not isinstance(sender, dict):
            return None
        sender_id = str(require_json_object(sender, "max.sender").get("user_id") or "")
        attachments = require_json_object(body, "max.body").get("attachments")
        if not isinstance(attachments, list):
            return None
        for att in attachments:
            if not isinstance(att, dict):
                continue
            att_obj = require_json_object(att, "max.attachment")
            if att_obj.get("type") != "contact":
                continue
            payload_obj = att_obj.get("payload")
            if not isinstance(payload_obj, dict):
                continue
            contact = require_json_object(payload_obj, "max.contact")
            # Официальный контракт request_contact: `hash` в payload подтверждает,
            # что номер привязан к аккаунту MAX; контакт «из телефонной книги»
            # приходит без hash и отклоняется.
            contact_hash = str(contact.get("hash") or "")
            if not sender_id or not contact_hash:
                raise ProviderError(
                    PhoneVerificationErrorCode.PROVIDER_MISMATCH,
                    "max contact has no hash binding",
                )
            phone = _phone_from_vcf(str(contact.get("vcf_info") or ""))
            if phone is None:
                raise ProviderError(PhoneVerificationErrorCode.INVALID_PHONE)
            return DirectVerificationRequest(
                kind=DirectAuthorizationKind.CONTACT_SHARE,
                provider=self.provider,
                contact_phone=phone,
                provider_user_id=sender_id,
                contact_user_id=sender_id,
            )
        return None

    async def fetch_phones(
        self, proof: DirectVerificationRequest
    ) -> list[ProviderPhone]:
        phone = normalize_phone_e164(proof.contact_phone or "")
        if phone is None:
            raise ProviderError(PhoneVerificationErrorCode.INVALID_PHONE)
        return [ProviderPhone(phone_e164=phone, verified=True, default=True)]
