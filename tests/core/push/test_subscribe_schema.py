"""
Валидация тела POST /api/push/subscribe (SubscribeRequest).
"""

import pytest
from pydantic import ValidationError

from core.push.schemas import SubscribeRequest


def test_web_vapid_defaults_and_keys():
    body = SubscribeRequest(
        endpoint="https://fcm.googleapis.com/fcm/send/x",
        keys={"p256dh": "abc", "auth": "def"},
        platform="desktop",
    )
    assert body.transport == "web_vapid"
    assert body.endpoint.startswith("https://")


def test_web_vapid_rejects_non_https_endpoint():
    with pytest.raises(ValidationError):
        SubscribeRequest(
            transport="web_vapid",
            endpoint="http://wrong.example/push",
            keys={"p256dh": "a", "auth": "b"},
        )


def test_ios_apns_normalizes_endpoint_and_keys():
    token = "a" * 64
    body = SubscribeRequest(
        transport="ios_apns",
        endpoint="",
        keys={"device_token": token},
    )
    assert body.endpoint == f"apns:{token}"
    assert body.keys == {"device_token": token}
    assert body.platform == "ios_native"


def test_ios_apns_rejects_invalid_token():
    with pytest.raises(ValidationError):
        SubscribeRequest(
            transport="ios_apns",
            keys={"device_token": "not-hex!!!"},
        )
