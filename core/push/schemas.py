"""
Pydantic-схемы для API push-подписок.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, PushSubscriptionKeys, require_json_object

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


def _parse_transport(raw: JsonValue | None) -> PushTransport:
    if raw is None:
        return "web_vapid"
    if raw == "web_vapid":
        return "web_vapid"
    if raw == "ios_apns":
        return "ios_apns"
    if raw == "android_fcm":
        return "android_fcm"
    raise ValueError("transport должен быть web_vapid, ios_apns или android_fcm")


def _parse_optional_string(raw: JsonValue | None, field_name: str, default: str) -> str:
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} должен быть строкой")
    return raw


def _parse_push_keys(raw: JsonValue | None) -> PushSubscriptionKeys:
    if raw is None:
        return {}
    raw_keys = require_json_object(raw, "keys")
    keys: PushSubscriptionKeys = {}
    for key, value in raw_keys.items():
        if not isinstance(value, str):
            raise ValueError(f"keys.{key} должен быть строкой")
        keys[key] = value
    return keys


class SubscribeRequest(StrictBaseModel):
    """Тело POST /api/push/subscribe."""

    transport: PushTransport = "web_vapid"
    endpoint: str = ""
    keys: PushSubscriptionKeys = Field(default_factory=dict)
    platform: str = "unknown"

    @model_validator(mode="before")
    @classmethod
    def normalize_by_transport(cls, data: JsonValue) -> JsonObject:
        payload = require_json_object(data, "SubscribeRequest")
        transport = _parse_transport(payload.get("transport"))
        endpoint = _parse_optional_string(payload.get("endpoint"), "endpoint", "")
        keys = _parse_push_keys(payload.get("keys"))
        platform = _parse_optional_string(payload.get("platform"), "platform", "unknown")

        if transport == "web_vapid":
            ep = endpoint.strip()
            if not ep.startswith("https://"):
                raise ValueError("web_vapid: endpoint должен начинаться с https://")
            for key_name in ("p256dh", "auth"):
                value = keys.get(key_name)
                if not value or not value.strip():
                    raise ValueError(f"web_vapid: keys.{key_name} обязателен")
            payload["transport"] = transport
            payload["endpoint"] = ep
            payload["keys"] = {
                "p256dh": keys["p256dh"].strip(),
                "auth": keys["auth"].strip(),
            }
            payload["platform"] = platform
            return payload

        if transport == "ios_apns":
            token_raw = keys.get("device_token")
            if not token_raw:
                raise ValueError("ios_apns: keys.device_token обязателен")
            normalized = _normalize_apns_device_token(token_raw)
            payload["transport"] = transport
            payload["endpoint"] = f"apns:{normalized}"
            payload["keys"] = {"device_token": normalized}
            payload["platform"] = "ios_native" if platform == "unknown" else platform
            return payload

        token_raw = keys.get("device_token")
        if not token_raw:
            raise ValueError("android_fcm: keys.device_token обязателен")
        normalized = _normalize_fcm_registration_token(token_raw)
        payload["transport"] = transport
        payload["endpoint"] = f"fcm:{normalized}"
        payload["keys"] = {"device_token": normalized}
        payload["platform"] = "android_native" if platform == "unknown" else platform
        return payload


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
