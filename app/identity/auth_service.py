"""
Основной сервис авторизации.
Управляет всеми провайдерами и пользователями.
"""

import json
import logging
import uuid
import secrets
from typing import Dict, Optional, Type
from datetime import datetime, timezone, timedelta
from .models import (
    AuthProvider,
    User,
    AuthSession,
    AuthResult,
    AuthRequest,
    ProviderUserInfo,
)
from .base_provider import BaseAuthProvider
from .providers.yandex import YandexProvider
from .providers.google import GoogleProvider
from ..core.config import settings
from app.db.repositories import Storage

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
            AuthProvider.GOOGLE: GoogleProvider,
        }

        for provider_name, provider_class in provider_classes.items():
            provider_config = settings.auth.providers.get(provider_name.value)

            if provider_config and provider_config.enabled:
                try:
                    provider = provider_class(provider_config)
                    if provider.validate_config():
                        self._providers[provider_name] = provider
                        logger.info(
                            f"✅ Провайдер {provider_name.value} инициализирован"
                        )
                    else:
                        logger.warning(
                            f"❌ Провайдер {provider_name.value} некорректно настроен"
                        )
                except Exception as e:
                    logger.error(
                        f"❌ Ошибка инициализации провайдера {provider_name.value}: {e}"
                    )
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
        code_key = f"oauth_code:{auth_request.provider.value}:{auth_request.code}"
        
        try:
            # Проверяем, не использован ли уже этот код
            cached_result = await self.storage.get(code_key)
            if cached_result:
                logger.info("⚠️ OAuth код уже использован - возвращаем кешированный результат")
                result_data = json.loads(cached_result)
                
                user = await self._get_user(result_data["user_id"])
                session = await self._get_session(result_data["session_id"])
                
                if user and session:
                    return AuthResult(success=True, user=user, session=session)
            
            # Проверяем state
            auth_state = await self._get_auth_state(auth_request.state)
            if not auth_state:
                return AuthResult(
                    success=False, error_message="Недействительный state авторизации"
                )

            provider = self.get_provider(auth_request.provider)
            if not provider:
                return AuthResult(
                    success=False,
                    error_message=f"Провайдер {auth_request.provider.value} недоступен",
                )

            try:
                # Обмениваем код на токены
                access_token, refresh_token = await provider.exchange_code_for_token(
                    auth_request.code,
                    auth_request.redirect_uri or auth_state["redirect_uri"],
                )
            except ValueError as e:
                # Если код уже использован - пробуем вернуть кешированный результат
                error_text = str(e).lower()
                if "expired" in error_text or "invalid" in error_text:
                    logger.warning("⚠️ Код уже использован или истек, проверяем кеш")
                    cached_result = await self.storage.get(code_key)
                    if cached_result:
                        logger.info("✅ Найден кешированный результат")
                        result_data = json.loads(cached_result)
                        
                        user = await self._get_user(result_data["user_id"])
                        session = await self._get_session(result_data["session_id"])
                        
                        if user and session:
                            return AuthResult(success=True, user=user, session=session)
                raise

            # Получаем информацию о пользователе
            user_info = await provider.get_user_info(access_token)

            # Находим или создаем пользователя
            user = await self._get_or_create_user(auth_request.provider, user_info)

            # Создаем сессию
            session = await self._create_session(user, auth_request.provider, access_token, refresh_token)

            # Кешируем результат на 5 минут
            result_cache = json.dumps({
                "user_id": user.user_id,
                "session_id": session.session_id
            })
            await self.storage.set(code_key, result_cache, ttl=300)

            # Очищаем временный state
            await self._cleanup_auth_state(auth_request.state)

            logger.info(f"✅ Авторизация завершена для пользователя {user_info.email}")

            return AuthResult(success=True, user=user, session=session)

        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return AuthResult(success=False, error_message=str(e))

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

    async def _save_auth_state(
        self, state: str, provider: AuthProvider, redirect_uri: str
    ):
        """Сохраняет временное состояние авторизации"""
        state_data = {
            "provider": provider.value,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Сохраняем на 10 минут
        key = f"auth_state:{state}"
        await self.storage.set(key, json.dumps(state_data), ttl=600)

    async def _get_auth_state(self, state: str) -> Optional[Dict]:
        """Получает временное состояние авторизации"""
        if not state:
            return None

        key = f"auth_state:{state}"
        data = await self.storage.get(key)

        if data:
            return json.loads(data)
        return None

    async def _cleanup_auth_state(self, state: str):
        """Удаляет временное состояние авторизации"""
        if state:
            key = f"auth_state:{state}"
            await self.storage.delete(key)

    async def _get_or_create_user(
        self, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> User:
        """Находит существующего пользователя или создает нового"""
        user_id = await self._find_user_by_provider_id(user_info.provider_user_id)

        if user_id:
            user = await self._get_user(user_id)
            
            if not user:
                logger.error(f"Пользователь {user_id} найден по индексу, но не существует")
                raise Exception(f"Пользователь {user_id} не найден")
            
            user.updated_at = datetime.now(timezone.utc)
            await self.storage.set(f"user:{user.user_id}", user.model_dump_json(), force_global=True)
            
            await self._update_provider_data(user.user_id, provider, user_info)
            
            logger.info(f"🔄 Обновлен пользователь {user_info.email}")
            return user
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"

            user = User(
                user_id=user_id,
                name=user_info.name,
                companies={},
                active_company_id="",
            )

            await self.storage.set(f"user:{user_id}", user.model_dump_json(), force_global=True)
            await self._add_user_provider(user_id, provider, user_info)

            logger.info(f"👤 Создан новый пользователь {user_info.email}")
            return user
    
    async def _find_user_by_provider_id(self, provider_user_id: str) -> Optional[str]:
        """Находит user_id по provider_user_id через индекс JSONB"""
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            query = text("""
                SELECT substring(key from 16) as user_id
                FROM users
                WHERE key LIKE 'user_providers:%'
                AND value ? :provider_user_id
                LIMIT 1
            """)
            result = await session.execute(query, {"provider_user_id": provider_user_id})
            row = result.first()
            return row[0] if row else None
    
    async def _add_user_provider(self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo):
        """Добавляет провайдера в список провайдеров пользователя"""
        providers_key = f"user_providers:{user_id}"
        providers_data = await self.storage.get(providers_key, force_global=True)
        
        if providers_data:
            providers = json.loads(providers_data)
        else:
            providers = {}
        
        providers[user_info.provider_user_id] = {
            "provider_name": provider.value,
            "email": user_info.email,
            "avatar_url": user_info.avatar_url,
            "metadata": user_info.raw_data
        }
        
        await self.storage.set(providers_key, json.dumps(providers), force_global=True)
    
    async def _update_provider_data(self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo):
        """Обновляет данные провайдера"""
        await self._add_user_provider(user_id, provider, user_info)
    
    async def link_provider(self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo) -> bool:
        """
        Связывает нового провайдера с существующим пользователем.
        Полезно когда пользователь хочет добавить Google после входа через Yandex.
        
        Returns:
            True если провайдер успешно связан
        """
        user = await self._get_user(user_id)
        if not user:
            return False
        
        existing_user_id = await self._find_user_by_provider_id(user_info.provider_user_id)
        if existing_user_id:
            logger.warning(f"Провайдер {provider}:{user_info.provider_user_id} уже используется другим пользователем")
            return False
        
        await self._add_user_provider(user.user_id, provider, user_info)
        
        logger.info(f"🔗 Связан провайдер {provider} с пользователем {user_info.email}")
        return True

    async def _get_user(self, user_id: str) -> Optional[User]:
        """Получает пользователя по ID - прямое чтение O(1)"""
        user_key = f"user:{user_id}"
        user_data = await self.storage.get(user_key, force_global=True)
        
        if not user_data:
            return None
        
        user_dict = json.loads(user_data)
        
        if "companies" not in user_dict:
            user_dict["companies"] = {}
        if "active_company_id" not in user_dict:
            user_dict["active_company_id"] = ""
        
        return User(**user_dict)
    
    async def get_user_provider_info(self, user_id: str, provider: AuthProvider) -> Optional[dict]:
        """Получает информацию о провайдере пользователя"""
        providers_key = f"user_providers:{user_id}"
        providers_data = await self.storage.get(providers_key, force_global=True)
        
        if not providers_data:
            return None
        
        providers = json.loads(providers_data)
        for provider_user_id, info in providers.items():
            if info.get("provider_name") == provider.value:
                return info
        
        return None

    async def _create_session(
        self, user: User, provider: AuthProvider, access_token: str, refresh_token: Optional[str]
    ) -> AuthSession:
        """Создает новую сессию для пользователя"""
        session_id = f"session_{uuid.uuid4().hex[:16]}"

        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=settings.auth.session_timeout)
        ).isoformat()

        session = AuthSession(
            session_id=session_id,
            user_id=user.user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        session_key = f"auth_session:{session_id}"
        await self.storage.set(session_key, session.model_dump_json())

        logger.info(f"🎫 Создана сессия {session_id} для пользователя {user.user_id}")
        return session

    async def _get_session(self, session_id: str) -> Optional[AuthSession]:
        """Получает сессию по ID"""
        session_data = await self.storage.get(f"auth_session:{session_id}")
        if session_data:
            return AuthSession(**json.loads(session_data))
        return None

    async def _delete_session(self, session_id: str):
        """Удаляет сессию"""
        await self.storage.delete(f"auth_session:{session_id}")


# Глобальный экземпляр сервиса авторизации
auth_service = AuthService()
