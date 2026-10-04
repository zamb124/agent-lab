"""Основной сервис авторизации."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from core.auth.utils import compare_passwords
from core.authz.group_sync import sync_user_groups
from core.authz.service import AuthzService
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.models import AuthProviderConfig
from core.db.storage import SharedStorage
from core.identity.base_provider import BaseAuthProvider
from core.identity.providers.apple import AppleProvider
from core.identity.providers.github import GithubProvider
from core.identity.providers.google import GoogleProvider
from core.identity.providers.yandex import YandexProvider
from core.logging import get_logger
from core.models.identity_models import (
    AuthCodeCache,
    AuthProvider,
    AuthRequest,
    AuthResult,
    AuthSession,
    AuthState,
    Company,
    ProviderUserInfo,
    User,
    UserProviderRecord,
)
from core.platform_brand.resolver import resolve_auth_apple_client_id
from core.utils.tokens import get_token_service

logger = get_logger(__name__)


class AuthService:
    """
    Центральный сервис авторизации.
    Управляет провайдерами, пользователями и сессиями.
    """

    def __init__(
        self,
        storage: SharedStorage,
        redis: RedisClient,
        authz: AuthzService,
    ) -> None:
        """
        Аргументы:
            authz: OpenFGA dual-write для User.groups
        """
        self._storage: SharedStorage = storage
        self._redis: RedisClient = redis
        self._authz: AuthzService = authz
        self._providers: dict[AuthProvider, BaseAuthProvider] = {}
        self._initialize_providers()

    async def _persist_user(self, user: User) -> bool:
        previous = await User.get(user.user_id)
        previous_groups = list(previous.groups) if previous is not None else []
        previous_company_ids = (
            list(previous.companies.keys()) if previous is not None else []
        )
        saved = await User.set(user)
        if saved:
            try:
                await sync_user_groups(
                    self._authz,
                    user_id=user.user_id,
                    groups=user.groups,
                    company_ids=list(user.companies.keys()),
                    previous_groups=previous_groups,
                    previous_company_ids=previous_company_ids,
                )
            except Exception:
                if previous is not None:
                    _ = await User.set(previous)
                else:
                    _ = await User.delete_by_id(user.user_id)
                raise
        return saved

    def _initialize_providers(self) -> None:
        """Инициализирует доступные провайдеры на основе конфигурации"""
        settings = get_settings()

        provider_classes: dict[AuthProvider, Callable[[AuthProviderConfig], BaseAuthProvider]] = {
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
                    logger.info("auth.provider.initialized", provider=provider_name.value)
                else:
                    logger.warning("auth.provider.misconfigured", provider=provider_name.value)
            else:
                logger.info("auth.provider.disabled", provider=provider_name.value)

    def reinitialize_providers(self) -> None:
        """Переинициализирует провайдеры на основе текущей конфигурации"""
        self._providers.clear()
        self._initialize_providers()

    def get_available_providers(self) -> list[AuthProvider]:
        """Возвращает список доступных провайдеров"""
        return list(self._providers.keys())

    @property
    def storage_configured(self) -> bool:
        db_url = self._storage.db_url
        return db_url is not None and db_url != ""

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def get_provider(self, provider_name: AuthProvider) -> BaseAuthProvider | None:
        """Получает провайдер по имени"""
        return self._providers.get(provider_name)

    async def start_auth(
        self,
        provider_name: AuthProvider,
        redirect_uri: str,
        original_host: str | None = None,
        return_path: str | None = None,
    ) -> str:
        """
        Начинает процесс авторизации.

        Аргументы:
            provider_name: Имя провайдера
            redirect_uri: URI для возврата после авторизации (на базовом домене)
            original_host: Оригинальный хост пользователя (для редиректа после авторизации)

        Возвращает:
            URL для перенаправления пользователя
        """
        provider = self.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name.value} is unavailable")

        state = secrets.token_urlsafe(32)

        await self._save_auth_state(state, provider_name, redirect_uri, original_host, return_path)

        apple_client_id: str | None = None
        if provider_name == AuthProvider.APPLE and original_host is not None and str(original_host).strip():
            apple_client_id = resolve_auth_apple_client_id(str(original_host).strip())

        if isinstance(provider, AppleProvider):
            auth_url = provider.get_authorization_url(
                state,
                redirect_uri,
                client_id=apple_client_id,
            )
        else:
            auth_url = provider.get_authorization_url(state, redirect_uri)

        logger.info("auth.oauth.started", provider=provider_name.value)
        logger.info("auth.oauth.redirect", redirect_uri=redirect_uri, original_host=original_host)
        logger.info("auth.oauth.url", auth_url=auth_url[:150])
        return auth_url

    async def complete_auth(self, auth_request: AuthRequest) -> AuthResult:
        """
        Завершает процесс авторизации.

        Аргументы:
            auth_request: Данные авторизации от провайдера

        Возвращает:
            Результат авторизации
        """
        code_key = f"oauth_code:{auth_request.provider.value}:{auth_request.code}"

        cached_result = await self._storage.get(code_key)
        if cached_result:
            logger.info("identity.oauth")
            result_cache = AuthCodeCache.model_validate_json(cached_result)

            user = await self.get_user(result_cache.user_id)
            session = await AuthSession.get(result_cache.session_id)

            if user and session:
                return AuthResult(
                    success=True, user=user, session=session, token=result_cache.token
                )

        auth_state = await self.get_auth_state(auth_request.state)
        if not auth_state:
            return AuthResult(success=False, error_message="Недействительный state авторизации")

        provider = self.get_provider(auth_request.provider)
        if not provider:
            return AuthResult(
                success=False,
                error_message=f"Провайдер {auth_request.provider.value} недоступен",
            )

        redirect_uri = auth_request.redirect_uri
        if redirect_uri is None:
            redirect_uri = auth_state.redirect_uri

        apple_client_id: str | None = None
        if (
            auth_request.provider == AuthProvider.APPLE
            and auth_state.original_host is not None
            and str(auth_state.original_host).strip()
        ):
            apple_client_id = resolve_auth_apple_client_id(str(auth_state.original_host).strip())

        try:
            if isinstance(provider, AppleProvider):
                access_token, refresh_token = await provider.exchange_code_for_token(
                    auth_request.code,
                    redirect_uri,
                    client_id=apple_client_id,
                )
            else:
                access_token, refresh_token = await provider.exchange_code_for_token(
                    auth_request.code,
                    redirect_uri,
                )
        except ValueError as e:
            error_msg = str(e)
            if "ошибку: 400" in error_msg or "ошибку: 401" in error_msg:
                return AuthResult(success=False, error_message=error_msg)
            raise

        if isinstance(provider, AppleProvider):
            user_info = await provider.get_user_info(
                access_token,
                auth_request.oauth_first_login_user_json,
                client_id=apple_client_id,
            )
        else:
            user_info = await provider.get_user_info(
                access_token, auth_request.oauth_first_login_user_json
            )

        user = await self._get_or_create_user(auth_request.provider, user_info)

        session = await self._create_session(
            user, auth_request.provider, access_token, refresh_token
        )

        token_service = get_token_service()

        # Получаем roles для активной компании
        roles = user.companies.get(user.active_company_id, []) if user.active_company_id else []

        jwt_token = token_service.create_token(
            user_id=user.user_id,
            company_id=user.active_company_id or "",
            roles=roles,
            session_id=session.session_id,
            email=user.email,
        )

        result_cache = AuthCodeCache(
            user_id=user.user_id,
            session_id=session.session_id,
            token=jwt_token,
        ).model_dump_json()
        _ = await self._storage.set(code_key, result_cache, ttl=300)

        await self._cleanup_auth_state(auth_request.state)

        logger.info("auth.oauth.completed", email=user_info.email)

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

        matched = await User.find_all_by_email_ci(demo.email)
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
            _ = await self._persist_user(user)

        session = await self._create_session(user, AuthProvider.DEMO, "demo", None)

        token_service = get_token_service()
        jwt_token = token_service.create_token(
            user_id=user.user_id,
            company_id=company_id,
            roles=roles,
            session_id=session.session_id,
            email=user.email,
        )

        return AuthResult(success=True, user=user, session=session, token=jwt_token)

    async def get_user_by_session(self, session_id: str) -> User | None:
        """Получает пользователя по ID сессии"""
        session = await AuthSession.get(session_id)
        if not session:
            return None

        return await self.get_user(session.user_id)

    async def logout(self, session_id: str) -> bool:
        """Завершает сессию пользователя"""
        _ = await AuthSession.delete_by_id(session_id)
        logger.info("auth.session.ended", session_id=session_id)
        return True

    async def _save_auth_state(
        self,
        state: str,
        provider: AuthProvider,
        redirect_uri: str,
        original_host: str | None = None,
        return_path: str | None = None,
    ) -> None:
        """Сохраняет временное состояние авторизации"""
        auth_state = AuthState(
            provider=provider,
            redirect_uri=redirect_uri,
            original_host=original_host,
            return_path=return_path,
            created_at=datetime.now(timezone.utc),
        )
        key = f"auth_state:{state}"
        _ = await self._redis.set(key, auth_state.model_dump_json(), ttl=600)

    async def get_auth_state(self, state: str) -> AuthState | None:
        """Получает временное состояние авторизации"""
        if not state:
            return None

        key = f"auth_state:{state}"
        data = await self._redis.getdel(key)
        if data is None:
            return None
        return AuthState.model_validate_json(data)

    async def peek_auth_state(self, state: str) -> AuthState | None:
        """Читает состояние без удаления — потребление одноразовое в complete_auth"""
        if not state:
            return None

        key = f"auth_state:{state}"
        data = await self._redis.get(key)
        if data is None:
            return None
        return AuthState.model_validate_json(data)

    async def _cleanup_auth_state(self, state: str) -> None:
        """Удаляет временное состояние авторизации"""
        if state:
            key = f"auth_state:{state}"
            _ = await self._redis.delete(key)

    async def _get_or_create_user(
        self, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> User:
        """Находит существующего пользователя или создает нового"""
        user_id = await self._find_user_by_provider_id(user_info.provider_user_id)

        if user_id:
            user = await User.get(user_id)

            if not user:
                logger.error("auth.user.index_orphaned", user_id=user_id)
                raise ValueError(f"User {user_id} not found")

            user.updated_at = datetime.now(timezone.utc)
            _ = await self._persist_user(user)

            await self._update_provider_data(user.user_id, provider, user_info)

            logger.info("auth.user.updated", email=user_info.email, user_id=user_id)
            return user
        else:
            if not user_info.email:
                raise ValueError(
                    f"Provider {provider.value} did not return email; cannot register a new user"
                )
            existing_list = await User.find_all_by_email_ci(user_info.email)
            if len(existing_list) > 1:
                raise ValueError(
                    f"Multiple users with email {user_info.email}: "
                    + ", ".join(u.user_id for u in existing_list)
                )
            if len(existing_list) == 1:
                user = existing_list[0]
                user.updated_at = datetime.now(timezone.utc)
                if user_info.name and not (user.name or "").strip():
                    user.name = user_info.name
                if user_info.avatar_url and not user.avatar_url:
                    user.avatar_url = user_info.avatar_url
                _ = await self._persist_user(user)
                await self._add_user_provider(user.user_id, provider, user_info)
                logger.info("identity.event", value=provider.value, user_id=user.user_id)
                return user

            user_id = f"user_{uuid.uuid4().hex[:12]}"

            user = User(
                user_id=user_id,
                name=user_info.name,
                emails=[user_info.email.strip().lower()],
                avatar_url=user_info.avatar_url,
                companies={},
                active_company_id="",
            )

            _ = await self._persist_user(user)
            await self._add_user_provider(user_id, provider, user_info)

            logger.info("auth.user.created", email=user_info.email)
            return user

    async def _find_user_by_provider_id(self, provider_user_id: str) -> str | None:
        row = await UserProviderRecord.find_by_provider_user_id(provider_user_id)
        if row is None:
            return None
        return row.user_id

    async def _add_user_provider(
        self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> None:
        record = UserProviderRecord(
            user_provider_id=f"{provider.value}:{user_info.provider_user_id}",
            user_id=user_id,
            provider_user_id=user_info.provider_user_id,
            provider_name=provider,
            email=user_info.email,
            avatar_url=user_info.avatar_url,
            metadata=user_info.raw_data,
        )
        _ = await record.save()

    async def _update_provider_data(
        self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> None:
        """Обновляет данные провайдера"""
        await self._add_user_provider(user_id, provider, user_info)

    async def link_provider(
        self, user_id: str, provider: AuthProvider, user_info: ProviderUserInfo
    ) -> bool:
        """
        Связывает нового провайдера с существующим пользователем.

        Возвращает:
            True если провайдер успешно связан
        """
        user = await self.get_user(user_id)
        if not user:
            return False

        existing_user_id = await self._find_user_by_provider_id(user_info.provider_user_id)
        if existing_user_id:
            logger.warning(
                "auth.provider.already_linked",
                provider=str(provider),
                provider_user_id=user_info.provider_user_id,
            )
            return False

        await self._add_user_provider(user.user_id, provider, user_info)

        logger.info("auth.provider.linked", provider=str(provider), email=user_info.email)
        return True

    async def get_user(self, user_id: str) -> User | None:
        """Получает пользователя по ID"""
        return await User.get(user_id)

    async def save_user(self, user: User) -> bool:
        """Сохраняет пользователя и dual-write User.groups в OpenFGA."""
        return await self._persist_user(user)

    async def get_company(self, company_id: str) -> Company | None:
        """Получает компанию по ID"""
        return await Company.get(company_id)

    async def get_user_provider_info(
        self,
        user_id: str,
        provider: AuthProvider,
    ) -> UserProviderRecord | None:
        """Получает информацию о провайдере пользователя"""
        providers = await self.get_all_user_providers_info(user_id)
        if providers is None:
            return None

        for info in providers.values():
            if info.provider_name == provider:
                return info

        return None

    async def get_all_user_providers_info(
        self, user_id: str
    ) -> dict[str, UserProviderRecord] | None:
        """Получает информацию о всех провайдерах пользователя"""
        rows = await UserProviderRecord.list_by_user_id(user_id)
        if not rows:
            return None
        return {row.provider_user_id: row for row in rows}

    async def _create_session(
        self, user: User, provider: AuthProvider, access_token: str, refresh_token: str | None
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

        _ = await AuthSession.set(session)

        logger.info("auth.session.created", session_id=session_id, user_id=user.user_id)
        return session
