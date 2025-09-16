"""
Базовый класс для провайдеров авторизации.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import httpx

from .models import ProviderUserInfo, AuthProvider
from ..core.config import AuthProviderConfig

logger = logging.getLogger(__name__)


class BaseAuthProvider(ABC):
    """
    Базовый класс для всех провайдеров авторизации.
    Определяет единый интерфейс для работы с различными SSO провайдерами.
    """
    
    def __init__(self, provider_name: AuthProvider, config: AuthProviderConfig):
        self.provider_name = provider_name
        self.config = config
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.auth_url = config.auth_url
        self.token_url = config.token_url
        self.userinfo_url = config.userinfo_url
        self.scope = config.scope
    
    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """
        Формирует URL для перенаправления пользователя на авторизацию.
        
        Args:
            state: Уникальная строка для защиты от CSRF
            redirect_uri: URI для возврата после авторизации
            
        Returns:
            URL для авторизации
        """
        pass
    
    @abstractmethod
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Tuple[str, Optional[str]]:
        """
        Обменивает код авторизации на токены доступа.
        
        Args:
            code: Код авторизации от провайдера
            redirect_uri: URI который использовался при авторизации
            
        Returns:
            Tuple[access_token, refresh_token]
        """
        pass
    
    @abstractmethod
    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Получает информацию о пользователе по токену доступа.
        
        Args:
            access_token: Токен доступа
            
        Returns:
            Информация о пользователе
        """
        pass
    
    async def refresh_access_token(self, refresh_token: str) -> Tuple[str, Optional[str]]:
        """
        Обновляет токен доступа используя refresh token.
        Базовая реализация - может быть переопределена в наследниках.
        
        Args:
            refresh_token: Токен обновления
            
        Returns:
            Tuple[new_access_token, new_refresh_token]
        """
        if not refresh_token:
            raise ValueError("Refresh token не предоставлен")
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data)
            
            if response.status_code != 200:
                logger.error(f"Ошибка обновления токена для {self.provider_name}: {response.text}")
                raise ValueError(f"Не удалось обновить токен: {response.status_code}")
            
            token_data = response.json()
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", refresh_token)
            
            if not new_access_token:
                raise ValueError("Провайдер не вернул новый access_token")
            
            return new_access_token, new_refresh_token
    
    def validate_config(self) -> bool:
        """
        Проверяет корректность конфигурации провайдера.
        
        Returns:
            True если конфигурация корректна
        """
        if not self.config.enabled:
            return False
            
        required_fields = [
            self.client_id,
            self.client_secret,
            self.auth_url,
            self.token_url,
            self.userinfo_url
        ]
        
        if not all(required_fields):
            logger.warning(f"Провайдер {self.provider_name} некорректно настроен")
            return False
            
        return True
    
    def _build_auth_params(self, state: str, redirect_uri: str) -> Dict[str, str]:
        """
        Строит базовые параметры для URL авторизации.
        Может быть расширен в наследниках.
        
        Args:
            state: State для CSRF защиты
            redirect_uri: URI для редиректа
            
        Returns:
            Словарь параметров
        """
        return {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "response_type": "code"
        }
    
    def _build_token_data(self, code: str, redirect_uri: str) -> Dict[str, str]:
        """
        Строит данные для запроса токена.
        Может быть расширен в наследниках.
        
        Args:
            code: Код авторизации
            redirect_uri: URI для редиректа
            
        Returns:
            Словарь данных для запроса
        """
        return {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
