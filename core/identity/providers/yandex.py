"""
Yandex OAuth провайдер авторизации.

АДАПТИРОВАНО: убраны локальные импорты, try-except блоки
"""

from typing import override
from urllib.parse import urlencode

from core.config.models import AuthProviderConfig
from core.http import request_public_oauth
from core.identity.base_provider import BaseAuthProvider
from core.logging import get_logger
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.types import parse_json_object

logger = get_logger(__name__)


class YandexProvider(BaseAuthProvider):
    """Провайдер авторизации через Yandex OAuth"""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.YANDEX, config)

    @override
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через Yandex"""
        params = self._build_auth_params(state, redirect_uri)

        params.update(
            {
                "force_confirm": "yes",
            }
        )

        return f"{self.auth_url}?{urlencode(params)}"

    @override
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[str, str | None]:
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

        token_data = parse_json_object(response.content, "yandex.token.response")

        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Yandex не вернул access_token")

        refresh_token = token_data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ValueError("Yandex вернул refresh_token не строкой")

        logger.info("Токены Yandex получены успешно")
        return access_token, refresh_token

    @override
    async def get_user_info(
        self, access_token: str, first_login_user_json: str | None = None
    ) -> ProviderUserInfo:
        """Получает информацию о пользователе из Yandex"""
        headers = {"Authorization": f"OAuth {access_token}"}

        response = await request_public_oauth("GET", self.userinfo_url, headers=headers)

        if response.status_code != 200:
            logger.error(f"Ошибка получения данных пользователя Yandex: {response.text}")
            raise ValueError(f"Не удалось получить данные пользователя: {response.status_code}")

        user_data = parse_json_object(response.content, "yandex.userinfo.response")

        provider_user_id = user_data.get("id")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            raise ValueError("Yandex не предоставил обязательные данные пользователя")

        email = user_data.get("default_email", "")
        if not isinstance(email, str) or not email:
            raise ValueError("Yandex не предоставил обязательные данные пользователя")

        first_name_value = user_data.get("first_name")
        if first_name_value is not None and not isinstance(first_name_value, str):
            raise ValueError("Yandex вернул first_name не строкой")
        first_name = "" if first_name_value is None else first_name_value

        last_name_value = user_data.get("last_name")
        if last_name_value is not None and not isinstance(last_name_value, str):
            raise ValueError("Yandex вернул last_name не строкой")
        last_name = "" if last_name_value is None else last_name_value

        display_name_value = user_data.get("display_name")
        if display_name_value is not None and not isinstance(display_name_value, str):
            raise ValueError("Yandex вернул display_name не строкой")
        display_name = "" if display_name_value is None else display_name_value

        full_name = f"{first_name} {last_name}".strip()
        if display_name:
            name = display_name
        elif full_name:
            name = full_name
        else:
            name = email.split("@")[0]

        avatar_url = None
        if "default_avatar_id" in user_data:
            avatar_id = user_data["default_avatar_id"]
            if not isinstance(avatar_id, str) or not avatar_id:
                raise ValueError("Yandex вернул default_avatar_id не строкой")
            avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"

        logger.info(f"Данные пользователя Yandex получены: {email}")

        return ProviderUserInfo(
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            raw_data=user_data,
        )
