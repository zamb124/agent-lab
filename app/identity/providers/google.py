"""
Google OAuth провайдер авторизации.
"""

import logging
from typing import Tuple, Optional
from urllib.parse import urlencode
import httpx

from ..base_provider import BaseAuthProvider
from ..models import ProviderUserInfo, AuthProvider
from ...core.config import AuthProviderConfig
import httpx

logger = logging.getLogger(__name__)


class GoogleProvider(BaseAuthProvider):
    """
    Провайдер авторизации через Google OAuth 2.0.
    """

    def __init__(self, config: AuthProviderConfig):
        super().__init__(AuthProvider.GOOGLE, config)

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Формирует URL для авторизации через Google"""
        params = self._build_auth_params(state, redirect_uri)
        
        params.update({
            "access_type": "offline",
            "prompt": "consent",
        })
        
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Tuple[str, Optional[str]]:
        """Обменивает код на токены Google"""
        data = self._build_token_data(code, redirect_uri)

        logger.info("🔍 Начинаем обмен кода на токены Google (без прокси)")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if response.status_code != 200:
                logger.error(f"Ошибка получения токена Google: {response.text}")
                raise ValueError(f"Google вернул ошибку: {response.status_code}")
            
            token_data = response.json()
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            
            if not access_token:
                raise ValueError("Google не вернул access_token")
            
            logger.info("✅ Токены Google получены успешно")
            return access_token, refresh_token

    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """Получает информацию о пользователе из Google"""
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(self.userinfo_url, headers=headers)
            
            if response.status_code != 200:
                logger.error(
                    f"Ошибка получения данных пользователя Google: {response.text}"
                )
                raise ValueError(
                    f"Не удалось получить данные пользователя: {response.status_code}"
                )
            
            user_data = response.json()
            logger.info(f"Ответ от Google UserInfo API: {user_data}")
            
            provider_user_id = user_data.get("sub") or user_data.get("id", "")
            email = user_data.get("email", "")
            name = user_data.get("name", "")
            
            if not name and email:
                name = email.split("@")[0]
            elif not name:
                name = provider_user_id
            
            avatar_url = user_data.get("picture")
            
            if not provider_user_id:
                logger.error(f"Google не вернул provider_user_id (sub/id). Данные: {user_data}")
                raise ValueError(
                    "Google не предоставил обязательные данные пользователя (provider_user_id отсутствует)"
                )
            
            if not email:
                logger.error(f"Google не вернул email. Данные: {user_data}")
                raise ValueError(
                    "Google не предоставил обязательные данные пользователя (email отсутствует)"
                )
            
            logger.info(f"✅ Данные пользователя Google получены: {email}")
            
            return ProviderUserInfo(
                provider_user_id=provider_user_id,
                email=email,
                name=name,
                avatar_url=avatar_url,
                raw_data=user_data,
            )

