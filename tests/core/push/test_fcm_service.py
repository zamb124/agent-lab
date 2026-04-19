"""
FcmPushService: успешная доставка, истекший токен, серверная ошибка.

Внешние зависимости (oauth2 token endpoint и FCM HTTP v1 send) подменяются
через httpx.MockTransport — ключ Google не нужен. JWT-подпись считает pyjwt
с тестовым RSA-ключом, сгенерированным на лету.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.push.fcm_service import FcmPushService


@pytest.fixture(scope="module")
def rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def _make_async_client_factory(handler):
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

    return factory


def _build_service(rsa_pem: str) -> FcmPushService:
    return FcmPushService(
        project_id="humanitec-app",
        client_email="firebase-adminsdk-x@humanitec-app.iam.gserviceaccount.com",
        private_key_pem=rsa_pem,
        token_uri="https://oauth2.googleapis.com/token",
    )


@pytest.mark.asyncio
async def test_send_alert_delivers_via_fcm(rsa_pem):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "oauth2.googleapis.com" in str(request.url):
            return httpx.Response(200, json={"access_token": "ya29.fake", "expires_in": 3600})
        if "fcm.googleapis.com" in str(request.url):
            assert request.headers.get("authorization") == "Bearer ya29.fake"
            payload = json.loads(request.content)
            assert payload["message"]["token"] == "fake-token-aaaaaaaaaaaaaaaaaa"
            assert payload["message"]["notification"]["title"] == "Привет"
            return httpx.Response(200, json={"name": "projects/humanitec-app/messages/123"})
        raise AssertionError(f"unexpected url {request.url}")

    service = _build_service(rsa_pem)
    with patch("core.push.fcm_service.httpx.AsyncClient", _make_async_client_factory(handler)):
        delivered, drop = await service.send_alert(
            registration_token="fake-token-aaaaaaaaaaaaaaaaaa",
            title="Привет",
            body="Сообщение",
            url="/sync/c/abc",
            tag="sync_msg",
            extra={"channel_id": "abc"},
        )
    assert delivered is True
    assert drop is False
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_send_alert_drops_unregistered_token(rsa_pem):
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com" in str(request.url):
            return httpx.Response(200, json={"access_token": "ya29.fake", "expires_in": 3600})
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": 404,
                    "status": "NOT_FOUND",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                            "errorCode": "UNREGISTERED",
                        }
                    ],
                }
            },
        )

    service = _build_service(rsa_pem)
    with patch("core.push.fcm_service.httpx.AsyncClient", _make_async_client_factory(handler)):
        delivered, drop = await service.send_alert(
            registration_token="dead-token-aaaaaaaaaaaaaaaaaa",
            title="t",
            body="b",
        )
    assert delivered is False
    assert drop is True


@pytest.mark.asyncio
async def test_send_alert_keeps_subscription_on_server_error(rsa_pem):
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com" in str(request.url):
            return httpx.Response(200, json={"access_token": "ya29.fake", "expires_in": 3600})
        return httpx.Response(500, json={"error": {"code": 500, "status": "INTERNAL"}})

    service = _build_service(rsa_pem)
    with patch("core.push.fcm_service.httpx.AsyncClient", _make_async_client_factory(handler)):
        delivered, drop = await service.send_alert(
            registration_token="another-token-aaaaaaaaaaaaaaaaaa",
            title="t",
            body="b",
        )
    assert delivered is False
    assert drop is False
