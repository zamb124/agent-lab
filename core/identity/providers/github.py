"""
GitHub OAuth провайдер авторизации.

АДАПТИРОВАНО: убраны локальные импорты, try-except блоки
"""

from core.logging import get_logger
from typing import Tuple, Optional
from urllib.parse import urlencode

from core.identity.base_provider import BaseAuthProvider
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.config.models import AuthProviderConfig
from core.http import request_public_oauth

logger = get_logger(__name__)
class GithubProvider(BaseAuthProvider):
    """Провайдер авторизации через GitHub OAuth 2.0"""

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.GITHUB, config)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через GitHub"""
        params = self._build_auth_params(state, redirect_uri)
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Tuple[str, Optional[str]]:
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

        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token:
            raise ValueError("GitHub не вернул access_token")

        logger.info("Токен GitHub получен успешно")
        return access_token, refresh_token

    async def get_user_info(
        self, access_token: str, first_login_user_json: Optional[str] = None
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

        user_data = user_response.json()

        email = user_data.get("email")
        if not email:
            emails_response = await request_public_oauth(
                "GET",
                f"{self.userinfo_url}/emails",
                timeout=30.0,
                headers=headers,
            )
            if emails_response.status_code == 200:
                emails_data = emails_response.json()
                for email_info in emails_data:
                    if email_info.get("primary") and email_info.get("verified"):
                        email = email_info.get("email")
                        break

        if not email:
            logger.warning("Не удалось получить email пользователя GitHub")
            raise ValueError("GitHub не вернул email пользователя")

        name_field = user_data.get("name") or ""
        parts = name_field.split(" ") if name_field else []
        first_name = parts[0] if parts else (email.split("@")[0])

        return ProviderUserInfo(
            provider_user_id=str(user_data.get("id")),
            email=email,
            name=(name_field or first_name).strip(),
            avatar_url=user_data.get("avatar_url"),
            raw_data=user_data,
        )
