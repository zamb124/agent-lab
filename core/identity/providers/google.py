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
            logger.error("auth.google.token_failed", body=response.text)
            raise ValueError(f"Google returned an error: {response.status_code}")

        token_data = parse_json_object(response.content, "google.token.response")

        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError('Google did not return access_token')

        refresh_token = token_data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ValueError('Google returned refresh_token that is not a string')

        logger.info("identity.google")
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
            logger.error("auth.google.userinfo_failed", body=response.text)
            raise ValueError(f"Failed to fetch user data: {response.status_code}")

        user_data = parse_json_object(response.content, "google.userinfo.response")
        logger.info("auth.google.userinfo", user_data=user_data)

        provider_user_id = user_data.get("sub")
        if provider_user_id is None:
            provider_user_id = user_data.get("id")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            logger.error("auth.google.missing_provider_user_id", user_data=user_data)
            raise ValueError(
                'Google did not provide required user data (provider_user_id is missing)'
            )

        email = user_data.get("email")
        if not isinstance(email, str) or not email:
            logger.error("auth.google.missing_email", user_data=user_data)
            raise ValueError(
                'Google did not provide required user data (email is missing)'
            )

        name_value = user_data.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise ValueError('Google returned name that is not a string')
        name = "" if name_value is None else name_value

        if not name:
            name = email.split("@")[0]

        avatar_url = user_data.get("picture")
        if avatar_url is not None and not isinstance(avatar_url, str):
            raise ValueError('Google returned picture that is not a string')

        logger.info("auth.google.userinfo_ok", email=email)

        return ProviderUserInfo(
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            raw_data=user_data,
        )
