"""
Единая система токенов для платформы Agent Lab.

АДАПТИРОВАНО: убраны try-except блоки (используем fail-fast)
"""

import jwt
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from core.config import get_settings

logger = logging.getLogger(__name__)


class TokenData(BaseModel):
    """Данные токена"""
    
    user_id: str = Field(description="ID пользователя")
    company_id: Optional[str] = Field(default=None, description="ID компании")
    session_id: Optional[str] = Field(default=None, description="ID сессии")
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время создания")
    exp: datetime = Field(description="Время истечения")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")


class TokenService:
    """Единый сервис управления токенами"""
    
    def __init__(self):
        settings = get_settings()
        self.secret_key = settings.auth.jwt_secret_key
        
        if not self.secret_key:
            raise ValueError("JWT secret key не настроен в конфигурации (auth.jwt_secret_key)")
        
        self.algorithm = 'HS256'
    
    def create_token(
        self,
        user_id: str,
        company_id: Optional[str] = None,
        session_id: Optional[str] = None,
        expires_in: int = 86400 * 7,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Создает JWT токен.
        
        Args:
            user_id: ID пользователя
            company_id: ID компании
            session_id: ID сессии
            expires_in: Время жизни в секундах (по умолчанию 7 дней)
            metadata: Дополнительные данные
            
        Returns:
            JWT токен
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in)
        
        token_data = TokenData(
            user_id=user_id,
            company_id=company_id,
            session_id=session_id,
            iat=now,
            exp=expires_at,
            metadata=metadata or {}
        )
        
        payload = token_data.model_dump()
        payload['iat'] = int(now.timestamp())
        payload['exp'] = int(expires_at.timestamp())
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(f"Создан JWT токен для пользователя {user_id}")
        
        return token
    
    def validate_token(self, token: str) -> Optional[TokenData]:
        """
        Проверяет JWT токен и возвращает данные.
        
        Args:
            token: JWT токен для проверки
            
        Returns:
            Данные токена или None если недействителен
        """
        if not token:
            return None
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            logger.warning("JWT токен истек")
            return None
        except jwt.DecodeError as e:
            logger.warning(f"JWT токен недействителен: {e}")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT токен имеет неверный формат: {e}")
            return None
        
        payload['iat'] = datetime.fromtimestamp(payload['iat'], tz=timezone.utc)
        payload['exp'] = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
        
        token_data = TokenData.model_validate(payload)
        
        if token_data.exp < datetime.now(timezone.utc):
            logger.warning("JWT токен истек")
            return None
        
        logger.debug(f"JWT токен валиден для пользователя {token_data.user_id}")
        
        return token_data


_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """Получает глобальный экземпляр сервиса токенов"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service

