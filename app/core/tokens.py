"""
Единая система токенов для платформы Agent Lab
"""
import jwt
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TokenData(BaseModel):
    """Данные токена"""
    
    user_id: str = Field(description="ID пользователя")
    company_id: Optional[str] = Field(default=None, description="ID компании")
    session_id: Optional[str] = Field(default=None, description="ID сессии")
    
    # Временные рамки
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время создания")
    exp: datetime = Field(description="Время истечения")
    
    # Метаданные
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные")


class TokenService:
    """Единый сервис управления токенами"""
    
    def __init__(self):
        # Получаем секретный ключ из настроек
        self.secret_key = settings.auth.jwt_secret_key or 'your-secret-key-change-in-production'
        self.algorithm = 'HS256'
    
    def create_token(
        self,
        user_id: str,
        company_id: Optional[str] = None,
        session_id: Optional[str] = None,
        expires_in: int = 86400 * 7,  # 7 дней по умолчанию
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Создает JWT токен
        
        Args:
            user_id: ID пользователя
            company_id: ID компании
            session_id: ID сессии
            expires_in: Время жизни в секундах
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
        
        # Создаем JWT токен
        payload = token_data.model_dump()
        # Конвертируем datetime в timestamp для JWT
        payload['iat'] = int(now.timestamp())
        payload['exp'] = int(expires_at.timestamp())
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(f"🔑 Создан JWT токен для пользователя {user_id}")
        
        return token
    
    def validate_token(self, token: str) -> Optional[TokenData]:
        """
        Проверяет JWT токен и возвращает данные
        
        Args:
            token: JWT токен для проверки
            
        Returns:
            Данные токена или None если недействителен
        """
        if not token:
            return None
        
        try:
            # Декодируем JWT токен
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Конвертируем timestamp обратно в datetime
            payload['iat'] = datetime.fromtimestamp(payload['iat'], tz=timezone.utc)
            payload['exp'] = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
            
            token_data = TokenData.model_validate(payload)
            
            # Проверяем срок действия
            if token_data.exp < datetime.now(timezone.utc):
                logger.warning(f"⚠️ JWT токен истек")
                return None
            
            logger.debug(f"✅ JWT токен валиден для пользователя {token_data.user_id}")
            
            return token_data
            
        except jwt.ExpiredSignatureError:
            logger.warning(f"⚠️ JWT токен истек")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"⚠️ Недействительный JWT токен: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка валидации JWT токена: {e}")
            return None


# Глобальный экземпляр сервиса
_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """Получает глобальный экземпляр сервиса токенов"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service