"""
Отправка уведомлений через Apple Push Notification service (HTTP/2).
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx
import jwt
from jwt import PyJWTError

from core.logging import get_logger

logger = get_logger(__name__)

APNS_PROD_HOST = "https://api.push.apple.com"
APNS_SANDBOX_HOST = "https://api.sandbox.push.apple.com"

_apns_push_service: Optional["ApnsPushService"] = None


class ApnsPushService:
    """HTTP/2 клиент APNs с JWT (.p8, ES256)."""

    def __init__(
        self,
        team_id: str,
        key_id: str,
        private_key_pem: str,
        bundle_id: str,
        use_sandbox: bool,
    ) -> None:
        pem = private_key_pem.strip()
        if not team_id or not key_id or not pem or not bundle_id:
            raise ValueError(
                "APNs: apns_team_id, apns_key_id, apns_private_key и apns_bundle_id обязательны"
            )
        self._team_id = team_id
        self._key_id = key_id
        self._private_key_pem = pem
        self._bundle_id = bundle_id
        self._base_url = APNS_SANDBOX_HOST if use_sandbox else APNS_PROD_HOST
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return True

    def _ensure_jwt(self) -> str:
        now = time.time()
        if self._jwt_token and now < self._jwt_expires_at - 60:
            return self._jwt_token
        headers = {"kid": self._key_id, "alg": "ES256"}
        payload: dict[str, Any] = {"iss": self._team_id, "iat": int(now)}
        try:
            self._jwt_token = jwt.encode(
                payload,
                self._private_key_pem,
                algorithm="ES256",
                headers=headers,
            )
        except PyJWTError as e:
            raise ValueError(f"APNs: не удалось подписать JWT: {e}") from e
        self._jwt_expires_at = now + 3500
        return self._jwt_token

    async def send_alert(
        self,
        device_token_hex: str,
        title: str,
        body: str,
        url: Optional[str] = None,
        tag: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, bool]:
        """
        Returns:
            (доставлено, удалить_подписку_из_БД)
        """
        token = device_token_hex.lower().replace(" ", "")
        apns_body: dict[str, Any] = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            }
        }
        if url:
            apns_body["url"] = url
        if tag:
            apns_body["tag"] = tag
        if extra:
            apns_body["data"] = extra

        req_url = f"{self._base_url}/3/device/{token}"
        bearer = self._ensure_jwt()
        async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
            response = await client.post(
                req_url,
                headers={
                    "authorization": f"bearer {bearer}",
                    "apns-topic": self._bundle_id,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "content-type": "application/json",
                },
                json=apns_body,
            )

        if response.status_code == 200:
            return True, False

        if response.status_code == 410:
            logger.info("APNs: токен неактивен (410), подписка будет удалена")
            return False, True

        if response.status_code == 400:
            logger.info(
                "APNs: 400 — вероятно неверный токен, подписка будет удалена: %s",
                response.text[:200],
            )
            return False, True

        logger.error(
            "APNs: ошибка отправки status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        return False, False


def init_apns_push_service(
    team_id: str,
    key_id: str,
    private_key_pem: str,
    bundle_id: str,
    use_sandbox: bool,
) -> ApnsPushService:
    global _apns_push_service
    _apns_push_service = ApnsPushService(
        team_id=team_id,
        key_id=key_id,
        private_key_pem=private_key_pem,
        bundle_id=bundle_id,
        use_sandbox=use_sandbox,
    )
    return _apns_push_service


def get_apns_push_service() -> Optional[ApnsPushService]:
    return _apns_push_service
