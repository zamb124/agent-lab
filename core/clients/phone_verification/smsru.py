"""SMS.RU — платный SMS-фолбек, расходы несёт платформа (не мерчант).

API: `https://sms.ru/sms/send` (док: https://sms.ru/api/send).
Стоимость фиксируется в billing-спане с `cost_origin=platform`
(`billing.pending_settlement` не выставляется — settlement идёт на
платформенный аккаунт, не в баланс компании).
"""

from __future__ import annotations

from typing import ClassVar

from core.config.models import CustomerAuthSmsruConfig
from core.customers.contracts import CodeDelivery
from core.customers.enums import (
    CustomerIdentityProvider,
    PhoneVerificationChannel,
    PhoneVerificationErrorCode,
)
from core.customers.errors import ProviderError
from core.http.client import request_public_oauth
from core.types import JsonValue, parse_json_object, require_json_object

_SEND_URL = "https://sms.ru/sms/send"


class SmsruCodeSender:
    provider: ClassVar[CustomerIdentityProvider] = CustomerIdentityProvider.PHONE
    channel: ClassVar[PhoneVerificationChannel] = PhoneVerificationChannel.SMS

    def __init__(self, cfg: CustomerAuthSmsruConfig | None) -> None:
        self._cfg: CustomerAuthSmsruConfig | None = cfg

    def available(self) -> bool:
        c = self._cfg
        return bool(c is not None and c.enabled and c.api_id)

    async def send(self, phone_e164: str, *, code: str) -> CodeDelivery:
        c = self._cfg
        if c is None or not c.api_id:
            raise ProviderError(PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED)
        params: dict[str, str] = {
            "api_id": c.api_id,
            "to": phone_e164.lstrip("+"),
            "msg": f"Ваш код: {code}",
            "json": "1",
        }
        if c.sender:
            params["from"] = c.sender
        if c.test_mode:
            params["test"] = "1"
        try:
            resp = await request_public_oauth("GET", _SEND_URL, params=params, timeout=20.0)
        except Exception as exc:
            raise ProviderError(
                PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE,
                f"sms.ru send: {exc}",
                retryable=True,
            ) from exc
        body = parse_json_object(resp.text, "smsru.send")
        status_code = body.get("status_code")
        if body.get("status") != "OK" or status_code != 100:
            sms_raw = body.get("sms")
            sms_obj = (
                require_json_object(sms_raw, "smsru.sms")
                if isinstance(sms_raw, dict)
                else {}
            )
            inner: JsonValue = next(iter(sms_obj.values()), None)
            inner_obj = (
                require_json_object(inner, "smsru.sms[]") if isinstance(inner, dict) else {}
            )
            code_val = inner_obj.get("status_code", status_code)
            mapped = (
                PhoneVerificationErrorCode.NOT_DELIVERABLE
                if code_val in (207, 301, 302)
                else PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE
            )
            raise ProviderError(
                mapped, f"sms.ru status_code={code_val}", retryable=mapped is PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE
            )
        sms_data = body.get("sms")
        message_id: str | None = None
        cost: float | None = None
        if isinstance(sms_data, dict):
            first: JsonValue = next(
                iter(require_json_object(sms_data, "smsru.sms").values()), None
            )
            if isinstance(first, dict):
                first_obj = require_json_object(first, "smsru.sms[]")
                message_id = str(first_obj["sms_id"]) if first_obj.get("sms_id") else None
                balance = first_obj.get("cost")
                if balance is not None:
                    try:
                        cost = float(str(balance))
                    except ValueError:
                        cost = None
        return CodeDelivery(
            channel=self.channel,
            provider=self.provider,
            status="sent",
            provider_message_id=message_id,
            price=cost,
            currency="RUB" if cost is not None else None,
            meta={"test": "1"} if c.test_mode else None,
        )
