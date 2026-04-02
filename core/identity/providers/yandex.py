"""
Yandex OAuth провайдер авторизации.

АДАПТИРОВАНО: убраны локальные импорты, try-except блоки
"""

import logging
from typing import Tuple, Optional
from urllib.parse import urlencode

from core.identity.base_provider import BaseAuthProvider
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.config.models import AuthProviderConfig
from core.http import request_public_oauth

logger = logging.getLogger(__name__)


class YandexProvider(BaseAuthProvider):
    """Провайдер авторизации через Yandex OAuth"""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.YANDEX, config)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через Yandex"""
        params = self._build_auth_params(state, redirect_uri)

        params.update({
            "force_confirm": "yes",
        })

        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Tuple[str, Optional[str]]:
        """Обменивает код на токены Yandex"""
        data = self._build_token_data(code, redirect_uri)
        
        response = await request_public_oauth(
            "POST",
            self.token_url,
            timeout=20,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Ошибка получения токена Yandex: {response.text}")
            raise ValueError(f"Yandex вернул ошибку: {response.status_code}")

        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token:
            raise ValueError("Yandex не вернул access_token")

        logger.info("Токены Yandex получены успешно")
        return access_token, refresh_token

    async def get_user_info(
        self, access_token: str, first_login_user_json: Optional[str] = None
    ) -> ProviderUserInfo:
        """Получает информацию о пользователе из Yandex"""
        headers = {"Authorization": f"OAuth {access_token}"}

        response = await request_public_oauth("GET", self.userinfo_url, headers=headers)

        if response.status_code != 200:
            logger.error(f"Ошибка получения данных пользователя Yandex: {response.text}")
            raise ValueError(f"Не удалось получить данные пользователя: {response.status_code}")

        user_data = response.json()

        provider_user_id = str(user_data.get("id", ""))
        email = user_data.get("default_email", "")

        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        display_name = user_data.get("display_name", "")

        name = (
            display_name
            or f"{first_name} {last_name}".strip()
            or email.split("@")[0]
        )

        avatar_url = None
        if "default_avatar_id" in user_data:
            avatar_id = user_data["default_avatar_id"]
            avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"

        if not provider_user_id or not email:
            raise ValueError("Yandex не предоставил обязательные данные пользователя")

        logger.info(f"Данные пользователя Yandex получены: {email}")

        return ProviderUserInfo(
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            raw_data=user_data,
        )

