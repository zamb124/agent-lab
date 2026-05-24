"""
GitHub OAuth провайдер авторизации.

АДАПТИРОВАНО: убраны локальные импорты, try-except блоки
"""

from typing import override
from urllib.parse import urlencode

from core.config.models import AuthProviderConfig
from core.http import request_public_oauth
from core.identity.base_provider import BaseAuthProvider
from core.logging import get_logger
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.types import parse_json_array, parse_json_object, require_json_object

logger = get_logger(__name__)


class GithubProvider(BaseAuthProvider):
    """Провайдер авторизации через GitHub OAuth 2.0"""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.GITHUB, config)

    @override
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через GitHub"""
        params = self._build_auth_params(state, redirect_uri)
        return f"{self.auth_url}?{urlencode(params)}"

    @override
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[str, str | None]:
        """Обменивает авторизационный код на токен доступа"""
        data = self._build_token_data(code, redirect_uri)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = await request_public_oauth(
            "POST",
            self.token_url,
            timeout=30.0,
            data=data,
            headers=headers,
        )

        if response.status_code != 200:
            logger.error(f"Ошибка получения токена GitHub: {response.text}")
            raise ValueError(f"GitHub вернул ошибку: {response.status_code}")

        token_data = parse_json_object(response.content, "github.token.response")
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("GitHub не вернул access_token")

        refresh_token = token_data.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise ValueError("GitHub вернул refresh_token не строкой")

        logger.info("Токен GitHub получен успешно")
        return access_token, refresh_token

    @override
    async def get_user_info(
        self, access_token: str, first_login_user_json: str | None = None
    ) -> ProviderUserInfo:
        """Получает информацию о пользователе из GitHub"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        user_response = await request_public_oauth(
            "GET", self.userinfo_url, timeout=30.0, headers=headers
        )

        if user_response.status_code != 200:
            logger.error(f"Ошибка получения профиля GitHub: {user_response.text}")
            raise ValueError(f"Не удалось получить профиль GitHub: {user_response.status_code}")

        user_data = parse_json_object(user_response.content, "github.user.response")

        email_raw = user_data.get("email")
        if email_raw is not None and not isinstance(email_raw, str):
            raise ValueError("GitHub вернул email не строкой")
        email = email_raw
        if not email:
            emails_response = await request_public_oauth(
                "GET",
                f"{self.userinfo_url}/emails",
                timeout=30.0,
                headers=headers,
            )
            if emails_response.status_code == 200:
                emails_data = parse_json_array(emails_response.content, "github.emails.response")
                for email_info in emails_data:
                    email_object = require_json_object(email_info, "github.emails.item")
                    primary = email_object.get("primary")
                    verified = email_object.get("verified")
                    item_email = email_object.get("email")
                    if not isinstance(primary, bool):
                        raise ValueError("GitHub вернул primary не bool")
                    if not isinstance(verified, bool):
                        raise ValueError("GitHub вернул verified не bool")
                    if item_email is not None and not isinstance(item_email, str):
                        raise ValueError("GitHub вернул email не строкой")
                    if primary and verified and item_email:
                        email = item_email
                        break

        if not email:
            logger.warning("Не удалось получить email пользователя GitHub")
            raise ValueError("GitHub не вернул email пользователя")

        name_raw = user_data.get("name")
        if name_raw is not None and not isinstance(name_raw, str):
            raise ValueError("GitHub вернул name не строкой")
        name_field = "" if name_raw is None else name_raw
        parts = name_field.split(" ") if name_field else []
        first_name = parts[0] if parts else (email.split("@")[0])

        provider_user_id_raw = user_data.get("id")
        if isinstance(provider_user_id_raw, bool):
            raise ValueError("GitHub вернул id не строкой и не числом")
        if isinstance(provider_user_id_raw, int):
            provider_user_id = str(provider_user_id_raw)
        elif isinstance(provider_user_id_raw, str) and provider_user_id_raw:
            provider_user_id = provider_user_id_raw
        else:
            raise ValueError("GitHub не вернул id пользователя")

        avatar_url = user_data.get("avatar_url")
        if avatar_url is not None and not isinstance(avatar_url, str):
            raise ValueError("GitHub вернул avatar_url не строкой")

        provider_name = name_field.strip() if name_field else first_name.strip()

        return ProviderUserInfo(
            provider_user_id=provider_user_id,
            email=email,
            name=provider_name,
            avatar_url=avatar_url,
            raw_data=user_data,
        )
