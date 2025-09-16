"""
Основной сервис авторизации.
Управляет всеми провайдерами и пользователями.
"""
import logging
import uuid
import secrets
from typing import Dict, Optional, Type
from datetime import datetime, timezone, timedelta

from .models import AuthProvider, User, AuthSession, AuthResult, AuthRequest, ProviderUserInfo
from .base_provider import BaseAuthProvider
from .providers.yandex import YandexProvider
from ..core.config import settings
from ..core.storage import Storage

logger = logging.getLogger(__name__)


class AuthService:
    """
    Центральный сервис авторизации.
    Управляет провайдерами, пользователями и сессиями.
    """
    
    def __init__(self):
        self.storage = Storage()
        self._providers: Dict[AuthProvider, BaseAuthProvider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Инициализирует доступные провайдеры на основе конфигурации"""
        provider_classes: Dict[AuthProvider, Type[BaseAuthProvider]] = {
            AuthProvider.YANDEX: YandexProvider,
        }
        
        for provider_name, provider_class in provider_classes.items():
            provider_config = settings.auth.providers.get(provider_name.value)
            
            if provider_config and provider_config.enabled:
                try:
                    provider = provider_class(provider_config)
                    if provider.validate_config():
                        self._providers[provider_name] = provider
                        logger.info(f"✅ Провайдер {provider_name.value} инициализирован")
                    else:
                        logger.warning(f"❌ Провайдер {provider_name.value} некорректно настроен")
                except Exception as e:
                    logger.error(f"❌ Ошибка инициализации провайдера {provider_name.value}: {e}")
            else:
                logger.info(f"🔒 Провайдер {provider_name.value} отключен")
    
    def get_available_providers(self) -> list[AuthProvider]:
        """Возвращает список доступных провайдеров"""
        return list(self._providers.keys())
    
    def get_provider(self, provider_name: AuthProvider) -> Optional[BaseAuthProvider]:
        """Получает провайдер по имени"""
        return self._providers.get(provider_name)
    
    async def start_auth(self, provider_name: AuthProvider, redirect_uri: str) -> str:
        """
        Начинает процесс авторизации.
        
        Args:
            provider_name: Имя провайдера
            redirect_uri: URI для возврата после авторизации
            
        Returns:
            URL для перенаправления пользователя
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Провайдер {provider_name.value} недоступен")
        
        # Генерируем state для защиты от CSRF
        state = secrets.token_urlsafe(32)
        
        # Сохраняем state в временном хранилище
        await self._save_auth_state(state, provider_name, redirect_uri)
        
        # Получаем URL авторизации
        auth_url = provider.get_authorization_url(state, redirect_uri)
        
        logger.info(f"🔗 Начата авторизация через {provider_name.value}")
        return auth_url
    
    async def complete_auth(self, auth_request: AuthRequest) -> AuthResult:
        """
        Завершает процесс авторизации.
        
        Args:
            auth_request: Данные авторизации от провайдера
            
        Returns:
            Результат авторизации
        """
        try:
            # Проверяем state
            auth_state = await self._get_auth_state(auth_request.state)
            if not auth_state:
                return AuthResult(
                    success=False,
                    error_message="Недействительный state авторизации"
                )
            
            provider = self.get_provider(auth_request.provider)
            if not provider:
                return AuthResult(
                    success=False,
                    error_message=f"Провайдер {auth_request.provider.value} недоступен"
                )
            
            # Обмениваем код на токены
            access_token, refresh_token = await provider.exchange_code_for_token(
                auth_request.code, 
                auth_request.redirect_uri or auth_state["redirect_uri"]
            )
            
            # Получаем информацию о пользователе
            user_info = await provider.get_user_info(access_token)
            
            # Находим или создаем пользователя
            user = await self._get_or_create_user(auth_request.provider, user_info)
            
            # Создаем сессию
            session = await self._create_session(user, access_token, refresh_token)
            
            # Очищаем временный state
            await self._cleanup_auth_state(auth_request.state)
            
            logger.info(f"✅ Авторизация завершена для пользователя {user.email}")
            
            return AuthResult(
                success=True,
                user=user,
                session=session
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return AuthResult(
                success=False,
                error_message=str(e)
            )
    
    async def get_user_by_session(self, session_id: str) -> Optional[User]:
        """Получает пользователя по ID сессии"""
        session = await self._get_session(session_id)
        if not session:
            return None
        
        return await self._get_user(session.user_id)
    
    async def logout(self, session_id: str) -> bool:
        """Завершает сессию пользователя"""
        try:
            await self._delete_session(session_id)
            logger.info(f"✅ Сессия {session_id} завершена")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка завершения сессии {session_id}: {e}")
            return False
    
    async def _save_auth_state(self, state: str, provider: AuthProvider, redirect_uri: str):
        """Сохраняет временное состояние авторизации"""
        state_data = {
            "provider": provider.value,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Сохраняем на 10 минут
        key = f"auth_state:{state}"
        import json
        await self.storage.set(key, json.dumps(state_data), ttl=600)
    
    async def _get_auth_state(self, state: str) -> Optional[Dict]:
        """Получает временное состояние авторизации"""
        if not state:
            return None
            
        key = f"auth_state:{state}"
        data = await self.storage.get(key)
        
        if data:
            import json
            return json.loads(data)
        return None
    
    async def _cleanup_auth_state(self, state: str):
        """Удаляет временное состояние авторизации"""
        if state:
            key = f"auth_state:{state}"
            await self.storage.delete(key)
    
    async def _get_or_create_user(self, provider: AuthProvider, user_info: ProviderUserInfo) -> User:
        """Находит существующего пользователя или создает нового"""
        # Ищем пользователя по провайдеру и provider_user_id
        user_key = f"user:{provider.value}:{user_info.provider_user_id}"
        user_data = await self.storage.get(user_key)
        
        if user_data:
            # Пользователь существует, обновляем информацию
            import json
            user_dict = json.loads(user_data)
            user = User(**user_dict)
            
            # Обновляем данные пользователя
            user.name = user_info.name
            user.email = user_info.email
            user.avatar_url = user_info.avatar_url
            user.metadata = user_info.raw_data
            user.updated_at = datetime.now(timezone.utc).isoformat()
            
            await self.storage.set(user_key, user.model_dump_json())
            logger.info(f"🔄 Обновлен пользователь {user.email}")
            
            return user
        else:
            # Создаем нового пользователя
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            
            user = User(
                user_id=user_id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                email=user_info.email,
                name=user_info.name,
                avatar_url=user_info.avatar_url,
                metadata=user_info.raw_data
            )
            
            await self.storage.set(user_key, user.model_dump_json())
            
            # Также сохраняем по user_id для быстрого поиска
            await self.storage.set(f"user_by_id:{user_id}", user.model_dump_json())
            
            logger.info(f"👤 Создан новый пользователь {user.email}")
            return user
    
    async def _get_user(self, user_id: str) -> Optional[User]:
        """Получает пользователя по ID"""
        user_data = await self.storage.get(f"user_by_id:{user_id}")
        if user_data:
            import json
            return User(**json.loads(user_data))
        return None
    
    async def _create_session(self, user: User, access_token: str, refresh_token: Optional[str]) -> AuthSession:
        """Создает новую сессию для пользователя"""
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        
        # Вычисляем время истечения (по умолчанию из конфигурации)
        expires_at = (
            datetime.now(timezone.utc) + 
            timedelta(seconds=settings.auth.session_timeout)
        ).isoformat()
        
        session = AuthSession(
            session_id=session_id,
            user_id=user.user_id,
            provider=user.provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at
        )
        
        # Сохраняем сессию
        session_key = f"auth_session:{session_id}"
        await self.storage.set(session_key, session.model_dump_json())
        
        logger.info(f"🎫 Создана сессия {session_id} для пользователя {user.email}")
        return session
    
    async def _get_session(self, session_id: str) -> Optional[AuthSession]:
        """Получает сессию по ID"""
        session_data = await self.storage.get(f"auth_session:{session_id}")
        if session_data:
            import json
            return AuthSession(**json.loads(session_data))
        return None
    
    async def _delete_session(self, session_id: str):
        """Удаляет сессию"""
        await self.storage.delete(f"auth_session:{session_id}")


# Глобальный экземпляр сервиса авторизации
auth_service = AuthService()
