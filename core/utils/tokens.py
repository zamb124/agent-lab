"""
Единая система токенов для платформы Humanitec.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

import jwt
from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)
class TokenType(str, Enum):
    """Тип токена"""
    SESSION = "session"  # Обычный токен авторизации (7 дней)
    API = "api"          # Перманентный API токен (до 2 лет)
    EMBED_SESSION = "embed_session"  # Короткоживущий токен встраиваемого чата

class TokenData(BaseModel):
    """Данные токена"""

    user_id: str = Field(description="ID пользователя")
    company_id: str = Field(description="ID компании")
    roles: list[str] = Field(default_factory=list, description="Роли пользователя в компании")
    token_type: TokenType = Field(default=TokenType.SESSION, description="Тип токена")
    exp: datetime = Field(description="Время истечения")
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время создания")
    session_id: str | None = Field(default=None, description="ID OAuth сессии (опционально)")
    email: str = Field(default="", description="Email пользователя")
    metadata: JsonObject = Field(default_factory=dict, description="Дополнительные данные")

class TokenService:
    """Единый сервис управления токенами"""

    SESSION_EXPIRES: ClassVar[int] = 86400 * 7           # 7 дней
    API_TOKEN_EXPIRES: ClassVar[int] = 86400 * 365 * 2   # 2 года
    EMBED_SESSION_EXPIRES: ClassVar[int] = 300           # 5 минут

    def __init__(self) -> None:
        settings = get_settings()
        secret_key = settings.auth.jwt_secret_key

        if not secret_key:
            raise ValueError("JWT secret key не настроен в конфигурации (auth.jwt_secret_key)")

        self.secret_key: str = secret_key
        self.algorithm: str = "HS256"

    def create_token(
        self,
        user_id: str,
        company_id: str = "",
        roles: list[str] | None = None,
        token_type: TokenType = TokenType.SESSION,
        expires_in: int | None = None,
        session_id: str | None = None,
        metadata: JsonObject | None = None,
        email: str = "",
    ) -> str:
        """
        Создает JWT токен.

        Аргументы:
            user_id: ID пользователя
            company_id: ID компании
            roles: Роли пользователя в компании
            token_type: Тип токена (SESSION или API)
            expires_in: Время жизни в секундах (по умолчанию зависит от типа)
            session_id: ID OAuth сессии (опционально)
            metadata: Дополнительные данные (provider, user_name и т.д.)
            email: Email пользователя

        Возвращает:
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
            email=email,
            metadata=metadata or {},
        )

        payload = require_json_object(token_data.model_dump(mode="json"), "token.payload")
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
        roles: list[str] | None = None,
        expires_in: int = API_TOKEN_EXPIRES,
    ) -> str:
        """
        Создает долгоживущий API токен для интеграций.

        Аргументы:
            user_id: ID пользователя
            company_id: ID компании
            roles: Роли пользователя
            expires_in: Время жизни (по умолчанию 2 года)

        Возвращает:
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
        roles: list[str] | None = None,
        expires_in: int = EMBED_SESSION_EXPIRES,
        metadata: JsonObject | None = None,
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

    def validate_token(self, token: str) -> TokenData | None:
        """
        Проверяет JWT токен и возвращает данные.

        Аргументы:
            token: JWT токен для проверки

        Возвращает:
            Данные токена или None если недействителен
        """
        if not token:
            return None

        try:
            decoded_payload: JsonValue = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError:
            logger.warning("JWT токен истек")
            return None
        except jwt.DecodeError as e:
            logger.warning(f"JWT токен недействителен: {e}")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT токен имеет неверный формат: {e}")
            return None

        payload = require_json_object(decoded_payload, "jwt.payload")
        token_data = TokenData.model_validate(payload)

        if token_data.exp < datetime.now(timezone.utc):
            logger.warning("JWT токен истек")
            return None

        logger.debug(f"JWT токен валиден: user={token_data.user_id}, company={token_data.company_id}")

        return token_data

_token_service: TokenService | None = None

def get_token_service() -> TokenService:
    """Получает глобальный экземпляр сервиса токенов"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
