"""
Отправка уведомлений через Firebase Cloud Messaging (HTTP v1 API).

Аутентификация — service account .json (ключ из Firebase Console → Project settings →
Service accounts → Generate new private key). JWT (RS256) обменивается на короткий
access_token у oauth2.googleapis.com, токен кешируется.
"""

from __future__ import annotations

import json
import time
from typing import Literal, NotRequired, Required, TypedDict

import httpx
import jwt
from jwt import PyJWTError

from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

FCM_HOST = "https://fcm.googleapis.com"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

_fcm_push_service: FcmPushService | None = None


class FcmAccessTokenResponse(StrictBaseModel):
    access_token: str
    expires_in: int
    token_type: str


class FcmNotification(TypedDict):
    title: str
    body: str


class FcmAndroidNotification(TypedDict, total=False):
    sound: Required[Literal["default"]]
    tag: NotRequired[str]
    click_action: NotRequired[str]


class FcmAndroidConfig(TypedDict):
    priority: Literal["high"]
    notification: FcmAndroidNotification


class FcmMessage(TypedDict, total=False):
    token: Required[str]
    notification: Required[FcmNotification]
    android: Required[FcmAndroidConfig]
    data: NotRequired[dict[str, str]]


class FcmSendRequest(TypedDict):
    message: FcmMessage


class FcmPushService:
    """HTTP v1 клиент FCM с OAuth 2.0 service account JWT."""

    def __init__(
        self,
        project_id: str,
        client_email: str,
        private_key_pem: str,
        token_uri: str,
    ) -> None:
        if not project_id or not client_email or not private_key_pem or not token_uri:
            raise ValueError(
                "FCM: project_id, client_email, private_key_pem и token_uri обязательны"
            )
        self._project_id: str = project_id
        self._client_email: str = client_email
        self._private_key_pem: str = private_key_pem
        self._token_uri: str = token_uri
        self._send_url: str = f"{FCM_HOST}/v1/projects/{project_id}/messages:send"
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0
        # Переиспользуемый async HTTP-клиент: FCM поддерживает keepalive,
        # и для push-нагрузки это критично — иначе на каждый алерт идёт
        # полный TLS-handshake к fcm.googleapis.com.
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        client = self._http_client
        if client is None:
            client = httpx.AsyncClient(timeout=30.0)
            self._http_client = client
        return client

    async def aclose(self) -> None:
        """Закрывает удерживаемый HTTP-клиент."""
        client = self._http_client
        if client is not None:
            await client.aclose()
            self._http_client = None

    @property
    def is_configured(self) -> bool:
        return True

    async def _ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - 60:
            return self._access_token

        iat = int(now)
        exp = iat + 3600
        claims: dict[str, str | int] = {
            "iss": self._client_email,
            "scope": FCM_SCOPE,
            "aud": self._token_uri,
            "iat": iat,
            "exp": exp,
        }
        try:
            assertion = jwt.encode(
                claims,
                self._private_key_pem,
                algorithm="RS256",
            )
        except PyJWTError as e:
            raise ValueError(f"FCM: не удалось подписать JWT: {e}") from e

        response = await self._get_http_client().post(
            self._token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            raise ValueError(
                f"FCM: получение access_token провалилось status={response.status_code} body={response.text[:300]}"
            )
        token_data = FcmAccessTokenResponse.model_validate_json(response.text)
        self._access_token = token_data.access_token
        self._access_token_expires_at = now + token_data.expires_in
        return self._access_token

    async def send_alert(
        self,
        registration_token: str,
        title: str,
        body: str,
        url: str | None = None,
        tag: str | None = None,
        extra: JsonObject | None = None,
    ) -> tuple[bool, bool]:
        """
        Returns:
            (доставлено, удалить_подписку_из_БД)
        """
        token = registration_token.strip()
        if not token:
            return False, True

        notification: FcmNotification = {"title": title, "body": body}
        android_notification: FcmAndroidNotification = {"sound": "default"}
        if tag:
            android_notification["tag"] = tag
        if url:
            android_notification["click_action"] = url
        android_block: FcmAndroidConfig = {
            "priority": "high",
            "notification": android_notification,
        }

        data_payload: dict[str, str] = {}
        if url:
            data_payload["url"] = url
        if tag:
            data_payload["tag"] = tag
        if extra:
            for key, value in extra.items():
                data_payload[key] = _json_value_to_fcm_data_value(value)

        message: FcmMessage = {
            "token": token,
            "notification": notification,
            "android": android_block,
        }
        if data_payload:
            message["data"] = data_payload

        access_token = await self._ensure_access_token()
        response = await self._get_http_client().post(
            self._send_url,
            headers={
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
            },
            json=FcmSendRequest(message=message),
        )

        if response.status_code == 200:
            return True, False

        if response.status_code in (400, 404):
            error_status = _error_status_from_body(response.text)
            if error_status in {
                "UNREGISTERED",
                "INVALID_ARGUMENT",
                "NOT_FOUND",
            }:
                logger.info(
                    "FCM: токен невалиден (%s, status=%s), подписка будет удалена",
                    error_status,
                    response.status_code,
                )
                return False, True

        logger.error(
            "FCM: ошибка отправки status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        return False, False


def _error_status_from_body(body: str) -> str | None:
    parsed = parse_json_object(body, "fcm error response")
    error = require_json_object(parsed["error"], "fcm error response.error")
    details_value = error.get("details")
    if details_value is not None:
        details = require_json_array(details_value, "fcm error response.error.details")
        for detail_value in details:
            detail = require_json_object(detail_value, "fcm error response.error.details[]")
            error_code = detail.get("errorCode")
            if isinstance(error_code, str) and error_code:
                return error_code
    status = error.get("status")
    if isinstance(status, str) and status:
        return status
    return None


def _json_value_to_fcm_data_value(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def init_fcm_push_service(
    project_id: str,
    client_email: str,
    private_key_pem: str,
    token_uri: str,
) -> FcmPushService:
    global _fcm_push_service
    _fcm_push_service = FcmPushService(
        project_id=project_id,
        client_email=client_email,
        private_key_pem=private_key_pem,
        token_uri=token_uri,
    )
    return _fcm_push_service


def get_fcm_push_service() -> FcmPushService | None:
    return _fcm_push_service
