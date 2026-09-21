"""
Базовый класс для провайдеров авторизации.

АДАПТИРОВАНО: убраны try-except блоки, локальные импорты
"""

from abc import ABC, abstractmethod

from core.config.models import AuthProviderConfig
from core.http import request_public_oauth
from core.logging import get_logger
from core.models.identity_models import AuthProvider, ProviderUserInfo
from core.types import parse_json_object

logger = get_logger(__name__)


class BaseAuthProvider(ABC):
    """
    Базовый класс для всех провайдеров авторизации.
    Определяет единый интерфейс для работы с различными SSO провайдерами.
    """

    def __init__(self, provider_name: AuthProvider, config: AuthProviderConfig):
        self.provider_name: AuthProvider = provider_name
        self.config: AuthProviderConfig = config
        self.client_id: str | None = config.client_id
        self.client_secret: str | None = config.client_secret
        self.auth_url: str = config.auth_url
        self.token_url: str = config.token_url
        self.userinfo_url: str = config.userinfo_url
        self.scope: str = config.scope

    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """
        Формирует URL для перенаправления пользователя на авторизацию.

        Аргументы:
            state: Уникальная строка для защиты от CSRF
            redirect_uri: URI для возврата после авторизации

        Возвращает:
            URL для авторизации
        """
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[str, str | None]:
        """
        Обменивает код авторизации на токены доступа.

        Аргументы:
            code: Код авторизации от провайдера
            redirect_uri: URI который использовался при авторизации

        Возвращает:
            Tuple[access_token, refresh_token]
        """
        pass

    @abstractmethod
    async def get_user_info(
        self, access_token: str, first_login_user_json: str | None = None
    ) -> ProviderUserInfo:
        """
        Получает информацию о пользователе по токену доступа.

        Аргументы:
            access_token: Токен доступа (у Apple — id_token)
            first_login_user_json: Apple: JSON из параметра user при первой авторизации

        Возвращает:
            Информация о пользователе
        """
        pass

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str | None]:
        """
        Обновляет токен доступа используя refresh token.

        Аргументы:
            refresh_token: Токен обновления

        Возвращает:
            Tuple[new_access_token, new_refresh_token]
        """
        if not refresh_token:
            raise ValueError('Refresh token was not provided')
        if not self.client_id:
            raise ValueError(f"client_id is not configured for {self.provider_name.value}")
        if not self.client_secret:
            raise ValueError(f"client_secret is not configured for {self.provider_name.value}")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        response = await request_public_oauth("POST", self.token_url, timeout=30.0, data=data)
        _ = response.raise_for_status()
        token_data = parse_json_object(
            response.content, f"{self.provider_name.value}.refresh_token.response"
        )

        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError(f"{self.provider_name.value} did not return access_token during refresh")

        refresh_token_value = token_data.get("refresh_token")
        if refresh_token_value is None:
            new_refresh_token = refresh_token
        elif isinstance(refresh_token_value, str):
            new_refresh_token = refresh_token_value
        else:
            raise ValueError(
                f"{self.provider_name.value} returned refresh_token that is not a string during refresh"
            )

        logger.info("auth.provider.token_refreshed", provider=self.provider_name.value)
        return access_token, new_refresh_token

    def validate_config(self) -> bool:
        """Проверяет что конфигурация провайдера корректна"""
        if not self.config.enabled:
            logger.warning("auth.provider.config_disabled", provider=self.provider_name.value)
            return False

        if not self.client_id:
            logger.warning("auth.provider.missing_client_id", provider=self.provider_name.value)
            return False

        if not self.client_secret:
            logger.warning("auth.provider.missing_client_secret", provider=self.provider_name.value)
            return False

        if not self.auth_url:
            logger.warning("auth.provider.missing_auth_url", provider=self.provider_name.value)
            return False

        if not self.token_url:
            logger.warning("auth.provider.missing_token_url", provider=self.provider_name.value)
            return False

        if not self.userinfo_url:
            logger.warning("auth.provider.missing_userinfo_url", provider=self.provider_name.value)
            return False

        return True

    def _build_auth_params(self, state: str, redirect_uri: str) -> dict[str, str]:
        """Формирует базовые параметры для URL авторизации"""
        if not self.client_id:
            raise ValueError(f"client_id is not configured for {self.provider_name.value}")
        return {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
        }

    def _build_token_data(self, code: str, redirect_uri: str) -> dict[str, str]:
        """Формирует данные для обмена кода на токен"""
        if not self.client_id:
            raise ValueError(f"client_id is not configured for {self.provider_name.value}")
        if not self.client_secret:
            raise ValueError(f"client_secret is not configured for {self.provider_name.value}")
        return {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
