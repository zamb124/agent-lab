"""
Google OAuth провайдер авторизации.

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


class GoogleProvider(BaseAuthProvider):
    """Провайдер авторизации через Google OAuth 2.0"""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.GOOGLE, config)

    @override
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через Google"""
        params = self._build_auth_params(state, redirect_uri)

        params.update(
            {
                "access_type": "offline",
                "prompt": "consent",
            }
        )

        return f"{self.auth_url}?{urlencode(params)}"

    @override
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[str, str | None]:
        """Обменивает код на токены Google"""
        data = self._build_token_data(code, redirect_uri)

        response = await request_public_oauth(
            "POST",
            self.token_url,
            timeout=30.0,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Ошибка получения токена Google: {response.text}")
            raise ValueError(f"Google вернул ошибку: {response.status_code}")

        token_data = parse_json_object(response.content, "google.token.response")

        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Google не вернул access_token")

        refresh_token = token_data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ValueError("Google вернул refresh_token не строкой")

        logger.info("Токены Google получены успешно")
        return access_token, refresh_token

    @override
    async def get_user_info(
        self, access_token: str, first_login_user_json: str | None = None
    ) -> ProviderUserInfo:
        """Получает информацию о пользователе из Google"""
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await request_public_oauth(
            "GET", self.userinfo_url, timeout=30.0, headers=headers
        )

        if response.status_code != 200:
            logger.error(f"Ошибка получения данных пользователя Google: {response.text}")
            raise ValueError(f"Не удалось получить данные пользователя: {response.status_code}")

        user_data = parse_json_object(response.content, "google.userinfo.response")
        logger.info(f"Ответ от Google UserInfo API: {user_data}")

        provider_user_id = user_data.get("sub")
        if provider_user_id is None:
            provider_user_id = user_data.get("id")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            logger.error(f"Google не вернул provider_user_id (sub/id). Данные: {user_data}")
            raise ValueError(
                "Google не предоставил обязательные данные пользователя (provider_user_id отсутствует)"
            )

        email = user_data.get("email")
        if not isinstance(email, str) or not email:
            logger.error(f"Google не вернул email. Данные: {user_data}")
            raise ValueError(
                "Google не предоставил обязательные данные пользователя (email отсутствует)"
            )

        name_value = user_data.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise ValueError("Google вернул name не строкой")
        name = "" if name_value is None else name_value

        if not name:
            name = email.split("@")[0]

        avatar_url = user_data.get("picture")
        if avatar_url is not None and not isinstance(avatar_url, str):
            raise ValueError("Google вернул picture не строкой")

        logger.info(f"Данные пользователя Google получены: {email}")

        return ProviderUserInfo(
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            raw_data=user_data,
        )
