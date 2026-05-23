"""
Отправка уведомлений через Firebase Cloud Messaging (HTTP v1 API).

Аутентификация — service account .json (ключ из Firebase Console → Project settings →
Service accounts → Generate new private key). JWT (RS256) обменивается на короткий
access_token у oauth2.googleapis.com, токен кешируется.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWTError

from core.logging import get_logger

logger = get_logger(__name__)

FCM_HOST = "https://fcm.googleapis.com"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

_fcm_push_service: FcmPushService | None = None


class FcmPushService:
    """HTTP v1 клиент FCM с OAuth 2.0 service account JWT."""

    def __init__(
        self,
        project_id: str,
        client_email: str,
        private_key_pem: str,
        token_uri: str,
    ) -> None:
        if not project_id or not client_email or not private_key_pem:
            raise ValueError(
                "FCM: project_id, client_email и private_key_pem обязательны"
            )
        self._project_id = project_id
        self._client_email = client_email
        self._private_key_pem = private_key_pem
        self._token_uri = token_uri or "https://oauth2.googleapis.com/token"
        self._send_url = f"{FCM_HOST}/v1/projects/{project_id}/messages:send"
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return True

    async def _ensure_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - 60:
            return self._access_token

        iat = int(now)
        exp = iat + 3600
        claims: dict[str, Any] = {
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
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
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("FCM: oauth2 ответ без access_token")
        expires_in = int(token_data.get("expires_in", 3600))
        self._access_token = str(access_token)
        self._access_token_expires_at = now + expires_in
        return self._access_token

    async def send_alert(
        self,
        registration_token: str,
        title: str,
        body: str,
        url: str | None = None,
        tag: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[bool, bool]:
        """
        Returns:
            (доставлено, удалить_подписку_из_БД)
        """
        token = registration_token.strip()
        if not token:
            return False, True

        notification: dict[str, Any] = {"title": title, "body": body}
        android_block: dict[str, Any] = {
            "priority": "high",
            "notification": {"sound": "default"},
        }
        if tag:
            android_block["notification"]["tag"] = tag
        if url:
            android_block["notification"]["click_action"] = url

        data_payload: dict[str, str] = {}
        if url:
            data_payload["url"] = url
        if tag:
            data_payload["tag"] = tag
        if extra:
            for key, value in extra.items():
                data_payload[str(key)] = "" if value is None else str(value)

        message: dict[str, Any] = {
            "token": token,
            "notification": notification,
            "android": android_block,
        }
        if data_payload:
            message["data"] = data_payload

        access_token = await self._ensure_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._send_url,
                headers={
                    "authorization": f"Bearer {access_token}",
                    "content-type": "application/json",
                },
                json={"message": message},
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
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    error = parsed.get("error")
    if not isinstance(error, dict):
        return None
    details = error.get("details")
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            error_code = item.get("errorCode")
            if isinstance(error_code, str):
                return error_code
    status = error.get("status")
    return str(status) if status else None


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
