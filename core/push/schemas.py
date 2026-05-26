"""
Pydantic-схемы для API push-подписок.
"""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import PushSubscriptionKeys

PushTransport = Literal["web_vapid", "ios_apns", "android_fcm"]


def _normalize_apns_device_token(raw: str) -> str:
    s = raw.strip().replace(" ", "").lower()
    if s.startswith("0x"):
        s = s[2:]
    if not re.fullmatch(r"[0-9a-f]{8,200}", s):
        raise ValueError("keys.device_token должен быть hex-строкой (8–200 символов)")
    return s


def _normalize_fcm_registration_token(raw: str) -> str:
    s = raw.strip()
    if not re.fullmatch(r"[A-Za-z0-9_:\-]{20,4096}", s):
        raise ValueError(
            "android_fcm: keys.device_token должен быть FCM registration token (буквы, цифры, _, -, :, длиной 20–4096 символов)"
        )
    return s


class SubscribeRequest(StrictBaseModel):
    """Тело POST /api/push/subscribe."""

    transport: PushTransport = "web_vapid"
    endpoint: str = ""
    keys: PushSubscriptionKeys = Field(default_factory=dict)
    platform: str = "unknown"

    @model_validator(mode="after")
    def validate_by_transport(self) -> Self:
        if self.transport == "web_vapid":
            ep = self.endpoint.strip()
            if not ep.startswith("https://"):
                raise ValueError("web_vapid: endpoint должен начинаться с https://")
            self.endpoint = ep
            for key_name in ("p256dh", "auth"):
                v = self.keys.get(key_name)
                if not v or not str(v).strip():
                    raise ValueError(f"web_vapid: keys.{key_name} обязателен")
            self.keys = {
                "p256dh": str(self.keys["p256dh"]).strip(),
                "auth": str(self.keys["auth"]).strip(),
            }
            return self

        if self.transport == "ios_apns":
            token_raw = self.keys.get("device_token")
            if not token_raw:
                raise ValueError("ios_apns: keys.device_token обязателен")
            normalized = _normalize_apns_device_token(str(token_raw))
            self.endpoint = f"apns:{normalized}"
            self.keys = {"device_token": normalized}
            if self.platform == "unknown":
                self.platform = "ios_native"
            return self

        token_raw = self.keys.get("device_token")
        if not token_raw:
            raise ValueError("android_fcm: keys.device_token обязателен")
        normalized = _normalize_fcm_registration_token(str(token_raw))
        self.endpoint = f"fcm:{normalized}"
        self.keys = {"device_token": normalized}
        if self.platform == "unknown":
            self.platform = "android_native"
        return self


class VapidPublicKeyResponse(StrictBaseModel):
    publicKey: str


class SubscribeResponse(StrictBaseModel):
    success: bool
    subscription_id: str


class PushSuccessResponse(StrictBaseModel):
    success: bool


class TestPushRequest(StrictBaseModel):
    title: str = "Тестовое уведомление"
    message: str = "Это тестовое push-уведомление от Humanitec"


class TestPushResponse(StrictBaseModel):
    success: bool
    sent_to_devices: int
    expired_subscriptions: int
