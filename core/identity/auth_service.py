"""
Основной сервис авторизации.
Управляет всеми провайдерами и пользователями.

АДАПТИРОВАНО: убраны try-except блоки (кроме критичных с raise), локальные импорты
"""

import json
import logging
import uuid
import secrets
from typing import Dict, Optional, Type, TYPE_CHECKING
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

from core.models.identity_models import (
    AuthProvider,
    User,
    AuthSession,
    AuthResult,
    AuthRequest,
    ProviderUserInfo,
)
from core.identity.base_provider import BaseAuthProvider
from core.identity.providers.yandex import YandexProvider
from core.identity.providers.google import GoogleProvider
from core.identity.providers.github import GithubProvider
from core.identity.providers.apple import AppleProvider
from core.auth.utils import compare_passwords
from core.config import get_settings
from core.utils.tokens import get_token_service

if TYPE_CHECKING:
    from core.db.repositories.user_repository import UserRepository
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.auth_session_repository import AuthSessionRepository

logger = logging.getLogger(__name__)


class AuthService:
    """
    Центральный сервис авторизации.
    Управляет провайдерами, пользователями и сессиями.
    """

    def __init__(
        self,
        user_repository: "UserRepository",
        company_repository: "CompanyRepository",
        auth_session_repository: "AuthSessionRepository"
    ):
        """
        Args:
            user_repository: Репозиторий для работы с пользователями
            company_repository: Репозиторий для работы с компаниями
            auth_session_repository: Репозиторий для работы с сессиями
        """
        self._user_repository = user_repository
        self._company_repository = company_repository
        self._auth_session_repository = auth_session_repository
        self._storage = user_repository._storage
        self._providers: Dict[AuthProvider, BaseAuthProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """Инициализирует доступные провайдеры на основе конфигурации"""
        settings = get_settings()
        
        provider_classes: Dict[AuthProvider, Type[BaseAuthProvider]] = {
            AuthProvider.YANDEX: YandexProvider,
            AuthProvider.GOOGLE: GoogleProvider,
            AuthProvider.GITHUB: GithubProvider,
            AuthProvider.APPLE: AppleProvider,
        }

        for provider_name, provider_class in provider_classes.items():
            provider_config = settings.auth.providers.get(provider_name.value)

            if provider_config and provider_config.enabled:
                provider = provider_class(provider_config)
                if provider.validate_config():
                    self._providers[provider_name] = provider
                    logger.info(f"Провайдер {provider_name.value} инициализирован")
                else:
                    logger.warning(f"Провайдер {provider_name.value} некорректно настроен")
            else:
                logger.info(f"Провайдер {provider_name.value} отключен")

    def reinitialize_providers(self):
        """Переинициализирует провайдеры на основе текущей конфигурации"""
        self._providers.clear()
        self._initialize_providers()

    def get_available_providers(self) -> list[AuthProvider]:
        """Возвращает список доступных провайдеров"""
        return list(self._providers.keys())

    def get_provider(self, provider_name: AuthProvider) -> Optional[BaseAuthProvider]:
        """Получает провайдер по имени"""
        return self._providers.get(provider_name)

    async def start_auth(
        self,
        provider_name: AuthProvider,
        redirect_uri: str,
        original_host: str = None,
        return_path: str = None,
    ) -> str:
        """
        Начинает процесс авторизации.

        Args:
            provider_name: Имя провайдера
            redirect_uri: URI для возврата после авторизации (на базовом домене)
            original_host: Оригинальный хост пользователя (для редиректа после авторизации)

        Returns:
            URL для перенаправления пользователя
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Провайдер {provider_name.value} недоступен")

        state = secrets.token_urlsafe(32)

        await self._save_auth_state(state, provider_name, redirect_uri, original_host, return_path)

        auth_url = provider.get_authorization_url(state, redirect_uri)

        logger.info(f"Начата авторизация через {provider_name.value}")
        logger.info(f"   redirect_uri: {redirect_uri}, original_host: {original_host}")
        logger.info(f"   auth_url: {auth_url[:150]}...")
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

        cached_result = await self._storage.get(code_key)
        if cached_result:
            logger.info("OAuth код уже использован - возвращаем кешированный результат")
            result_data = json.loads(cached_result)

            user = await self._get_user(result_data["user_id"])
            session = await self._get_session(result_data["session_id"])

            if user and session:
                cached_token = result_data.get("token")
                return AuthResult(success=True, user=user, session=session, token=cached_token)

        auth_state = await self._get_auth_state(auth_request.state)
        if not auth_state:
            return AuthResult(success=False, error_message="Недействительный state авторизации")

        provider = self.get_provider(auth_request.provider)
        if not provider:
            return AuthResult(success=False, error_message=f"Провайдер {auth_request.provider.value} недоступен")

        try:
            access_token, refresh_token = await provider.exchange_code_for_token(
                auth_request.code,
                auth_request.redirect_uri or auth_state["redirect_uri"],
            )
        except ValueError as e:
            error_msg = str(e)
            if "ошибку: 400" in error_msg or "ошибку: 401" in error_msg:
                return AuthResult(success=False, error_message=error_msg)
            raise

        user_info = await provider.get_user_info(
            access_token, auth_request.oauth_first_login_user_json
        )

        user = await self._get_or_create_user(auth_request.provider, user_info)

        session = await self._create_session(user, auth_request.provider, access_token, refresh_token)

        token_service = get_token_service()
        
        # Получаем roles для активной компании
        roles = user.companies.get(user.active_company_id, []) if user.active_company_id else []
        
        jwt_token = token_service.create_token(
            user_id=user.user_id,
            company_id=user.active_company_id or "",
            roles=roles,
            session_id=session.session_id,
        )

        result_cache = json.dumps({
            "user_id": user.user_id,
            "session_id": session.session_id,
            "token": jwt_token
        })
        await self._storage.set(code_key, result_cache, ttl=300)

        await self._cleanup_auth_state(auth_request.state)

        logger.info(f"Авторизация завершена для пользователя {user_info.email}")

        return AuthResult(success=True, user=user, session=session, token=jwt_token)

    async def login_demo(self, email: str, password: str) -> AuthResult:
        settings = get_settings()
        demo = settings.auth.demo
        if not demo.login_enabled:
            return AuthResult(success=False, error_message="Демо-вход отключён")

        def norm(value: str) -> str:
            return value.strip().lower()

        if norm(email) != norm(demo.email):
            return AuthResult(success=False, error_message="Неверные учётные данные")

        users = await self._user_repository.list_all(limit=10000)
        matched = [
            u
            for u in users
            if any(norm(e) == norm(demo.email) for e in u.emails)
        ]
        if len(matched) != 1:
            return AuthResult(success=False, error_message="Неверные учётные данные")

        user = matched[0]
        if not compare_passwords(password, user.password_hash):
            return AuthResult(success=False, error_message="Неверные учётные данные")

        company_id = demo.company_id
        roles = user.companies.get(company_id)
        if not roles:
            return AuthResult(success=False, error_message="Неверные учётные данные")

        if user.active_company_id != company_id:
            user.active_company_id = company_id
            await self._user_repository.set(user)

        session = await self._create_session(user, AuthProvider.DEMO, "demo", None)

        token_service = get_token_service()
        jwt_token = token_service.create_token(
            user_id=user.user_id,
            company_id=company_id,
            roles=roles,
            session_id=session.session_id,
        )

        return AuthResult(success=True, user=user, session=session, token=jwt_token)

    async def get_user_by_session(self, session_id: str) -> Optional[User]:
        """Получает пользователя по ID сессии"""
        session = await self._get_session(session_id)
        if not session:
            return None

        return await self._get_user(session.user_id)

    async def logout(self, session_id: str) -> bool:
        """Завершает сессию пользователя"""
        await self._delete_session(session_id)
        logger.info(f"Сессия {session_id} завершена")
        return True

    async def _save_auth_state(
        self,
        state: str,
        provider: AuthProvider,
        redirect_uri: str,
        original_host: str = None,
        return_path: str = None,
    ):
        """Сохраняет временное состояние авторизации"""
        state_data = {
            "provider": provider.value,
            "redirect_uri": redirect_uri,
            "original_host": original_host,
            "return_path": return_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        key = f"auth_state:{state}"
        await self._storage.set(key, json.dumps(state_data), ttl=600)

    async def _get_auth_state(self, state: str) -> Optional[Dict]:
        """Получает временное состояние авторизации"""
        if not state:
            return None

        key = f"auth_state:{state}"
        data = await self._storage.get(key)

        if data:
            return json.loads(data)
        return None

    async def _cleanup_auth_state(self, state: str):
        """Удаляет временное состояние авторизации"""
        if state:
            key = f"auth_state:{state}"
            await self._storage.delete(key)

    async def _get_or_create_user(
        self, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> User:
        """Находит существующего пользователя или создает нового"""
        user_id = await self._find_user_by_provider_id(user_info.provider_user_id)

        if user_id:
            user = await self._user_repository.get(user_id)

            if not user:
                logger.error(f"Пользователь {user_id} найден по индексу, но не существует")
                raise ValueError(f"Пользователь {user_id} не найден")

            user.updated_at = datetime.now(timezone.utc)
            await self._user_repository.set(user)

            await self._update_provider_data(user.user_id, provider, user_info)

            logger.info(f"Обновлен пользователь {user_info.email or user_id}")
            return user
        else:
            if not user_info.email:
                raise ValueError(
                    f"Провайдер {provider.value} не вернул email; регистрация нового пользователя невозможна"
                )
            user_id = f"user_{uuid.uuid4().hex[:12]}"

            user = User(
                user_id=user_id,
                name=user_info.name,
                emails=[user_info.email] if user_info.email else [],
                avatar_url=user_info.avatar_url,
                companies={},
                active_company_id="",
            )

            await self._user_repository.set(user)
            await self._add_user_provider(user_id, provider, user_info)

            logger.info(f"Создан новый пользователь {user_info.email}")
            return user

    async def _find_user_by_provider_id(self, provider_user_id: str) -> Optional[str]:
        """Находит user_id по provider_user_id через индекс JSONB"""
        async with self._storage._get_session() as session:
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
        # user_providers глобальные - пользователь может быть в нескольких компаниях
        providers_data = await self._storage.get(providers_key, force_global=True)

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

        await self._storage.set(providers_key, json.dumps(providers), force_global=True)

    async def _update_provider_data(self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo):
        """Обновляет данные провайдера"""
        await self._add_user_provider(user_id, provider, user_info)

    async def link_provider(self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo) -> bool:
        """
        Связывает нового провайдера с существующим пользователем.

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

        logger.info(f"Связан провайдер {provider} с пользователем {user_info.email}")
        return True

    async def _get_user(self, user_id: str) -> Optional[User]:
        """Получает пользователя по ID"""
        return await self.user_repository.get(user_id)

    async def get_user_provider_info(self, user_id: str, provider: AuthProvider) -> Optional[dict]:
        """Получает информацию о провайдере пользователя"""
        providers_key = f"user_providers:{user_id}"
        providers_data = await self._storage.get(providers_key)

        if not providers_data:
            return None

        providers = json.loads(providers_data)
        for provider_user_id, info in providers.items():
            if info.get("provider_name") == provider.value:
                return info

        return None

    async def get_all_user_providers_info(self, user_id: str) -> Optional[dict]:
        """Получает информацию о всех провайдерах пользователя"""
        providers_key = f"user_providers:{user_id}"
        providers_data = await self._storage.get(providers_key)

        if not providers_data:
            return None

        return json.loads(providers_data)

    async def _create_session(
        self, user: User, provider: AuthProvider, access_token: str, refresh_token: Optional[str]
    ) -> AuthSession:
        """Создает новую сессию для пользователя"""
        settings = get_settings()
        session_id = f"session_{uuid.uuid4().hex[:16]}"

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=settings.auth.session_timeout)
        ).isoformat()

        session = AuthSession(
            session_id=session_id,
            user_id=user.user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        await self._auth_session_repository.set(session)

        logger.info(f"Создана сессия {session_id} для пользователя {user.user_id}")
        return session

    async def _get_session(self, session_id: str) -> Optional[AuthSession]:
        """Получает сессию по ID"""
        return await self._auth_session_repository.get(session_id)

    async def _delete_session(self, session_id: str):
        """Удаляет сессию"""
        await self._auth_session_repository.delete(session_id)

