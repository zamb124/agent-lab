"""
Единая система токенов для платформы Humanitec.
"""

import jwt
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from core.config import get_settings

logger = logging.getLogger(__name__)


class TokenType(str, Enum):
    """Тип токена"""
    SESSION = "session"  # Обычный токен авторизации (7 дней)
    API = "api"          # Перманентный API токен (до 2 лет)
    EMBED_SESSION = "embed_session"  # Короткоживущий токен встраиваемого чата


class TokenData(BaseModel):
    """Данные токена"""
    
    user_id: str = Field(description="ID пользователя")
    company_id: str = Field(description="ID компании")
    roles: List[str] = Field(default_factory=list, description="Роли пользователя в компании")
    token_type: TokenType = Field(default=TokenType.SESSION, description="Тип токена")
    exp: datetime = Field(description="Время истечения")
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время создания")
    session_id: Optional[str] = Field(default=None, description="ID OAuth сессии (опционально)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")


class TokenService:
    """Единый сервис управления токенами"""
    
    SESSION_EXPIRES = 86400 * 7           # 7 дней
    API_TOKEN_EXPIRES = 86400 * 365 * 2   # 2 года
    EMBED_SESSION_EXPIRES = 300           # 5 минут
    
    def __init__(self):
        settings = get_settings()
        self.secret_key = settings.auth.jwt_secret_key
        
        if not self.secret_key:
            raise ValueError("JWT secret key не настроен в конфигурации (auth.jwt_secret_key)")
        
        self.algorithm = 'HS256'
    
    def create_token(
        self,
        user_id: str,
        company_id: str = "",
        roles: Optional[List[str]] = None,
        token_type: TokenType = TokenType.SESSION,
        expires_in: Optional[int] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Создает JWT токен.
        
        Args:
            user_id: ID пользователя
            company_id: ID компании
            roles: Роли пользователя в компании
            token_type: Тип токена (SESSION или API)
            expires_in: Время жизни в секундах (по умолчанию зависит от типа)
            session_id: ID OAuth сессии (опционально)
            metadata: Дополнительные данные (provider, user_name и т.д.)
            
        Returns:
            JWT токен
        """
        if expires_in is None:
            if token_type == TokenType.API:
                expires_in = self.API_TOKEN_EXPIRES
            elif token_type == TokenType.EMBED_SESSION:
                expires_in = self.EMBED_SESSION_EXPIRES
            else:
                expires_in = self.SESSION_EXPIRES
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in)
        
        token_data = TokenData(
            user_id=user_id,
            company_id=company_id,
            roles=roles or [],
            token_type=token_type,
            iat=now,
            exp=expires_at,
            session_id=session_id,
            metadata=metadata or {},
        )
        
        payload = token_data.model_dump()
        payload['iat'] = int(now.timestamp())
        payload['exp'] = int(expires_at.timestamp())
        payload['token_type'] = token_data.token_type.value
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(f"Создан {token_type.value} токен для пользователя {user_id}, компания {company_id}")
        
        return token
    
    def create_api_token(
        self,
        user_id: str,
        company_id: str,
        roles: Optional[List[str]] = None,
        expires_in: int = API_TOKEN_EXPIRES,
    ) -> str:
        """
        Создает долгоживущий API токен для интеграций.
        
        Args:
            user_id: ID пользователя
            company_id: ID компании
            roles: Роли пользователя
            expires_in: Время жизни (по умолчанию 2 года)
            
        Returns:
            JWT токен
        """
        return self.create_token(
            user_id=user_id,
            company_id=company_id,
            roles=roles,
            token_type=TokenType.API,
            expires_in=expires_in,
        )

    def create_embed_session_token(
        self,
        *,
        user_id: str,
        company_id: str,
        roles: Optional[List[str]] = None,
        expires_in: int = EMBED_SESSION_EXPIRES,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Создает короткоживущий токен для внешнего embed-чата."""
        return self.create_token(
            user_id=user_id,
            company_id=company_id,
            roles=roles,
            token_type=TokenType.EMBED_SESSION,
            expires_in=expires_in,
            metadata=metadata,
        )
    
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
        
        logger.debug(f"JWT токен валиден: user={token_data.user_id}, company={token_data.company_id}")
        
        return token_data


_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """Получает глобальный экземпляр сервиса токенов"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
