"""
Middleware для создания глобального контекста запроса.

Репозитории получаются через request.app.state.container.
"""

import logging
import json
from typing import List, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.responses import RedirectResponse, JSONResponse
from core.context import set_context, clear_context
from core.models.context_models import Context
from core.config import settings
from core.models.identity_models import User, AuthProvider, UserStatus, Company
from core.models.i18n_models import Language
from core.utils.tokens import get_token_service
logger = logging.getLogger(__name__)


class CompanyCreationRequired(Exception):
    """Исключение для случаев когда нужно создать компанию"""
    pass


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для создания RequestContext с пользователем"""

    def __init__(self, app):
        super().__init__(app)

    def _get_container(self, request: Request):
        """Получить контейнер из request.app.state"""
        return request.app.state.container

    async def _setup_webhook_context(self, request: Request, platform: str) -> None:
        """Устанавливает контекст для webhook запросов (Telegram/WhatsApp)"""
        flow_key = request.url.path.split(f"/api/v1/webhook/{platform}/")[1]

        parts = flow_key.split(":")
        if len(parts) < 4 or parts[0] != "company" or parts[2] != "flow":
            raise HTTPException(status_code=400, detail=f"Invalid flow key format: {flow_key}")

        company_id = parts[1]

        container = self._get_container(request)
        requested_company = await container.company_repository.get(company_id)
        if not requested_company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

        # Для GET (верификация WhatsApp) используем анонимный контекст
        # Для остальных создаем контекст с реальным пользователем
        if platform == "whatsapp" and request.method == "GET":
            context = await self._create_anonymous_context(request, requested_company)
        elif platform == "telegram":
            context = await self._create_telegram_context(request, requested_company)
        else:
            context = await self._create_whatsapp_context(request, requested_company)

        set_context(context)
        request.state.context = context
        request.state.user = context.user
        request.state.language = context.language.value
        logger.info(f"✅ {platform.title()} webhook: компания {company_id}")

    async def dispatch(self, request: Request, call_next):
        # Пропускаем middleware для статики и служебных путей
        if (
            request.url.path.startswith("/static/")
            or request.url.path.startswith("/.well-known/")
            or request.url.path.startswith("/favicon.ico")
            or request.url.path.startswith("/api/v1/payments/webhook/")
            or request.url.path == "/health"
            or request.url.path == "/api/v1/lead"
        ):
            return await call_next(request)

        # Для Telegram webhook
        if request.url.path.startswith("/api/v1/webhook/telegram/"):
            await self._setup_webhook_context(request, "telegram")
            return await call_next(request)

        # Для WhatsApp webhook
        if request.url.path.startswith("/api/v1/webhook/whatsapp/"):
            await self._setup_webhook_context(request, "whatsapp")
            return await call_next(request)
        # Для скачивания файлов - создаем минимальный контекст с компанией из поддомена
        if request.url.path.startswith("/api/v1/files/download/"):
            try:
                container = self._get_container(request)
                subdomain_repo = container.subdomain_repository
                company_repo = container.company_repository
                
                # Определяем компанию по Host - для файлов всегда требуется поддомен
                host = request.headers.get("host", "")
                domain = settings.server.domain
                requested_company = None

                # Для локальной разработки: требуем поддомен
                if settings.server.env == "local":
                    if ".localhost" in host:
                        subdomain = host.split(".")[0]
                        company_id = await subdomain_repo.get_company_id(subdomain)
                        if company_id:
                            requested_company = await company_repo.get(company_id)
                            if requested_company:
                                logger.info(f"📂 Файл: найдена компания {company_id} по поддомену {subdomain}")

                    if not requested_company:
                        logger.warning(f"⚠️ Запрос файла без поддомена: {host}")
                        raise HTTPException(status_code=400, detail="Для скачивания файла требуется указать поддомен компании (например, ssd.localhost:8001)")
                else:
                    if host.endswith(f".{domain}") and not host.startswith(domain):
                        subdomain = host.split(".")[0]
                        company_id = await subdomain_repo.get_company_id(subdomain)
                        if company_id:
                            requested_company = await company_repo.get(company_id)

                    if not requested_company:
                        raise HTTPException(status_code=400, detail="Для скачивания файла требуется указать поддомен компании")

                # Создаем минимальный анонимный контекст с этой компанией
                context = await self._create_anonymous_context(request, requested_company)
                set_context(context)
                request.state.context = context
                request.state.user = context.user
                request.state.language = context.language.value

                logger.info(f"📂 Контекст для скачивания файла: компания {requested_company.company_id}")

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"❌ Не удалось создать контекст для скачивания файла: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Ошибка определения компании")

            return await call_next(request)

        try:
            # Создаем контекст на основе типа запроса


            context = await self._create_request_context(request)

            # Устанавливаем глобальный контекст
            set_context(context)

            # Также сохраняем в request.state для совместимости
            request.state.context = context
            request.state.user = context.user
            request.state.language = context.language.value
            request.state.user_companies = getattr(context, 'user_companies', [])

            # Продолжаем обработку
            response = await call_next(request)
            return response

        except CompanyCreationRequired:
            # Редиректим на выбор компании (относительный URL сохраняет текущий хост)
            return RedirectResponse(url="/frontend/select-company", status_code=307)
        except HTTPException as e:
            # Для HTML запросов редиректим на авторизацию
            accept_header = request.headers.get("accept", "")
            if e.status_code == 401 and "text/html" in accept_header:
                return RedirectResponse(url="/frontend/auth", status_code=302)

            # Для AJAX/JSON запросов возвращаем JSON
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        finally:
            # Очищаем контекст после обработки
            clear_context()

    async def _create_request_context(self, request: Request) -> Context:
        """Создает контекст на основе типа запроса"""

        path = request.url.path
        logger.info(f"🔍 Обрабатываем путь: {path}")

        # Определяем запрашиваемую компанию по Host
        requested_company = await self._get_company_from_host(request)

        # Определяем, есть ли субдомен в запросе
        host = request.headers.get("host", "")
        has_subdomain = self._has_subdomain(host)

        # Определяем платформу по URL
        if "/webhook/telegram/" in path:
            logger.info("📱 Telegram контекст")
            return await self._create_telegram_context(request, requested_company)
        elif "/webhook/whatsapp/" in path:
            logger.info("📱 WhatsApp контекст")
            return await self._create_whatsapp_context(request, requested_company)
        elif path == "/api/v1/admin/create-my-company" or path == "/frontend/api/admin/create-my-company":
            logger.info("🏢 API создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True, has_subdomain=has_subdomain)
        elif "/api/v1/admin/" in path or "/api/v1/history/" in path or "/frontend/api/admin/" in path:
            # Frontend endpoints - используют токен из куки
            logger.info("🖥️ Frontend API контекст (токен из куки)")
            return await self._create_frontend_context(request, requested_company, has_subdomain=has_subdomain)
        elif "/api/v1/" in path:
            # Публичные API endpoints - проверяем наличие токена
            token = request.cookies.get("auth_token")
            if not token:
                auth_header = request.headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            
            if token:
                # Есть токен - используем API контекст
                logger.info("🔌 API контекст (с токеном)")
                return await self._create_api_context(request, requested_company)
            else:
                # Нет токена - создаем анонимный контекст для публичных endpoints
                logger.info("🔓 Публичный API контекст (без токена)")
                return await self._create_anonymous_context(request, requested_company)
        elif "/api/amocrm" in path:
            logger.info("🔌 AmoCRM контекст")
            return await self._create_amocrm_context(request, requested_company)
        elif path == "/frontend/auth":
            logger.info("🔐 Страница авторизации - публичная")
            return await self._create_anonymous_context(request, requested_company)
        elif path == "/frontend/create-company":
            logger.info("🏢 Страница создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True, has_subdomain=has_subdomain)
        elif path == "/frontend/select-company":
            logger.info("🏢 Страница выбора компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True, has_subdomain=has_subdomain)
        elif path.startswith("/frontend/models/create_company_form/"):
            logger.info("🏢 API для формы создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True, has_subdomain=has_subdomain)
        elif path.startswith("/frontend/chat/embed"):
            logger.info("💬 Embed чат - публичный доступ через токен в URL")
            return await self._create_anonymous_context(request, requested_company)
        elif path.startswith("/frontend/"):
            logger.info("🖥️ Frontend контекст - требует авторизации")
            return await self._create_frontend_context(request, requested_company, has_subdomain=has_subdomain)
        elif path.startswith("/auth/"):
            logger.info("🔐 OAuth контекст")
            return await self._create_anonymous_context(request, requested_company)
        elif path.startswith("/docs/") or path in ("/docs", "/api/docs", "/api/redoc"):
            logger.info("📚 Docs контекст")
            return await self._create_anonymous_context(request, requested_company)
        elif path == "/api/openapi.json":
            logger.info("📋 OpenAPI spec контекст")
            return await self._create_anonymous_context(request, requested_company)
        elif path == "/" or path == "/privacy" or path == "/terms":
            logger.info(f"🏠 Публичная страница {path} - проверяем авторизацию")
            # Для публичных страниц пытаемся создать frontend контекст, но без ошибки если пользователь не авторизован
            try:
                return await self._create_frontend_context(request, requested_company, allow_no_company=True, has_subdomain=has_subdomain)
            except HTTPException:
                # Если авторизация не удалась, создаем анонимный контекст
                logger.info(f"🏠 Пользователь не авторизован для {path}, создаем анонимный контекст")
                return await self._create_anonymous_context(request, requested_company)
        else:
            logger.warning(f"❌ Неизвестный путь: {path}")
            raise HTTPException(status_code=404, detail="Not Found")

    def _has_subdomain(self, host: str) -> bool:
        """Проверяет, содержит ли host субдомен"""
        domain = settings.server.domain

        # Для локальной разработки: проверяем наличие точки перед localhost
        if settings.server.env == "local":
            return ".localhost" in host

        # Для продакшена: проверяем, что есть субдомен перед основным доменом
        return host.endswith(f".{domain}") and not host.startswith(domain)

    async def _get_company_from_host(self, request: Request) -> Company:
        """Определяет компанию по Host заголовку"""
        container = self._get_container(request)
        subdomain_repo = container.subdomain_repository
        company_repo = container.company_repository
        
        host = request.headers.get("host", "")
        domain = settings.server.domain

        logger.info(f"🔍 Определяем компанию: host={host}, domain={domain}, env={settings.server.env}")

        # Специальная логика для локальной разработки
        if settings.server.env == "local" and ".localhost" in host:
            # Для localhost: ssd.localhost:8001 -> subdomain = ssd
            subdomain = host.split(".")[0]
            logger.info(f"Local режим: subdomain={subdomain}")
            company_id = await subdomain_repo.get_company_id(subdomain)
            if company_id:
                company = await company_repo.get(company_id)
                if company:
                    logger.info(f"Найдена компания по поддомену: {company_id}")
                    return company

        # Продакшен логика
        elif host.endswith(f".{domain}") and not host.startswith(domain):
            subdomain = host.split(".")[0]
            logger.info(f"Продакшен режим: subdomain={subdomain}")
            company_id = await subdomain_repo.get_company_id(subdomain)
            logger.info(f"company_id из subdomain: {company_id}")
            if company_id:
                company = await company_repo.get(company_id)
                if company:
                    logger.info(f"Найдена компания по поддомену: {company_id}")
                    return company

            # Если поддомен есть, но компания не найдена - это ошибка
            logger.error(f"❌ Компания не найдена для поддомена: {subdomain}")
            raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")

        # Если это основной домен (без поддомена) - возвращаем системную компанию
        logger.info("🔍 Основной домен без поддомена, возвращаем системную компанию")
        return await self._get_system_company(request)

    def _detect_user_language(self, request: Request) -> Language:
        """Определяет предпочитаемый язык пользователя"""
        # 1. Приоритет: заголовок Accept-Language (для HTMX запросов)
        accept_language = request.headers.get('Accept-Language', '').lower()
        if accept_language:
            for lang in Language:
                if lang.value == accept_language:
                    logger.debug(f"🌐 Язык определен из заголовка Accept-Language: {lang.value}")
                    return lang

        # 2. Cookie language
        language_cookie = request.cookies.get('language')
        if language_cookie:
            language_cookie = language_cookie.lower()
            for lang in Language:
                if lang.value == language_cookie:
                    logger.debug(f"🌐 Язык определен из cookie: {lang.value}")
                    return lang

        # 3. Accept-Language заголовок браузера (парсим более детально)
        browser_accept = request.headers.get('accept-language', '').lower()
        if browser_accept:
            # Парсим заголовок вида "ru-RU,ru;q=0.9,en;q=0.8"
            languages = [lang.split(';')[0].split('-')[0] for lang in browser_accept.split(',')]
            for browser_lang in languages:
                for lang in Language:
                    if lang.value == browser_lang.strip():
                        logger.debug(f"🌐 Язык определен из браузера Accept-Language: {lang.value}")
                        return lang

        # 4. По умолчанию
        logger.debug(f"🌐 Используем язык по умолчанию: {Language.RU.value}")
        return Language.RU

    async def _get_system_company(self, request: Request) -> Company:
        """Возвращает системную компанию"""
        container = self._get_container(request)
        company = await container.company_repository.get("system")
        if company:
            return company

        # Если системной компании нет - что-то пошло не так
        raise Exception("Системная компания не найдена - нужно запустить миграцию")

    async def _create_telegram_context(self, request: Request, requested_company: Company) -> Context:
        """Создает контекст для Telegram запросов"""

        body = await request.body()
        data = json.loads(body)

        # Извлекаем данные Telegram пользователя
        tg_user = data.get("message", {}).get("from", {})
        telegram_user_id = str(tg_user.get("id", "unknown"))
        username = tg_user.get("username", "")
        first_name = tg_user.get("first_name", "")
        last_name = tg_user.get("last_name", "")

        # Формируем полное имя
        full_name = (
            f"{first_name} {last_name}".strip()
            or username
            or f"User_{telegram_user_id}"
        )

        # Создаем реального Telegram пользователя
        user = User(
            user_id=f"telegram_{telegram_user_id}",
            provider=AuthProvider.YANDEX,  # Placeholder
            provider_user_id=telegram_user_id,
            email="",  # У Telegram нет email
            name=full_name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={requested_company.company_id: ["user"]},
            active_company_id=requested_company.company_id,
        )

        # Определяем язык пользователя
        language = self._detect_user_language(request)

        context = Context(
            user=user,
            platform="telegram",
            active_company=requested_company,
            user_companies=[requested_company],
            language=language,
            metadata={
                "telegram_user_id": telegram_user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )

        return context

    async def _create_whatsapp_context(self, request: Request, requested_company: Company) -> Context:
        """Создает контекст для WhatsApp запросов"""
        body = await request.body()
        data = json.loads(body)

        # Извлекаем данные WhatsApp пользователя из webhook
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])
        value = changes[0].get("value", {}) if changes else {}

        messages = value.get("messages", [])
        contacts = value.get("contacts", [])

        # Получаем информацию о пользователе
        if messages:
            wa_message = messages[0]
            phone_number = wa_message.get("from", "unknown")
        else:
            phone_number = "unknown"

        # Профиль пользователя
        profile_name = "User"
        if contacts:
            profile_name = contacts[0].get("profile", {}).get("name", "User")

        # Создаем WhatsApp пользователя
        user = User(
            user_id=f"whatsapp_{phone_number}",
            provider=AuthProvider.YANDEX,
            provider_user_id=phone_number,
            email="",
            name=profile_name,
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={requested_company.company_id: ["user"]},
            active_company_id=requested_company.company_id,
        )

        # Определяем язык пользователя
        language = self._detect_user_language(request)

        return Context(
            user=user,
            platform="whatsapp",
            active_company=requested_company,
            user_companies=[requested_company],
            language=language,
            metadata={
                "whatsapp_phone": phone_number,
                "profile_name": profile_name,
            },
        )

    async def _create_api_context(self, request: Request, requested_company: Company) -> Context:
        """Создает контекст для API запросов"""
        container = self._get_container(request)
        company_repo = container.company_repository
        user_repo = container.user_repository

        # Получаем токен из куки auth_token или заголовка Authorization
        token = request.cookies.get("auth_token")

        # Если нет куки, проверяем заголовок Authorization
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Убираем "Bearer "

        # Токен обязателен для API запросов
        if not token:
            raise HTTPException(status_code=401, detail="Token required")

        # Проверяем токен через централизованную систему
        token_service = get_token_service()
        token_data = token_service.validate_token(token)

        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Получаем пользователя по user_id из токена
        user = None
        if token_data.user_id:
            user = await self._get_user_by_id(request, token_data.user_id)

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Получаем все компании пользователя
        user_companies = await self._get_user_companies(request, user)

        # Проверяем доступ к запрашиваемой компании (если указана в токене)
        if token_data.company_id and token_data.company_id != requested_company.company_id:
            raise HTTPException(status_code=403, detail="Token company mismatch")

        # Проверяем доступ к запрашиваемой компании
        if requested_company.company_id not in user.companies:
            # Если у пользователя нет доступа к запрашиваемой компании,
            # используем его активную компанию или первую доступную
            active_company = None
            if user.active_company_id and user.active_company_id in user.companies:
                active_company = await company_repo.get(user.active_company_id)

            if not active_company and user_companies:
                active_company = user_companies[0]

            if not active_company:
                # У пользователя нет доступных компаний
                raise HTTPException(status_code=403, detail="No accessible companies")
        else:
            active_company = requested_company
            # Обновляем активную компанию у пользователя если нужно
            if user.active_company_id != requested_company.company_id:
                user.active_company_id = requested_company.company_id
                await user_repo.set(user)

        # Определяем язык пользователя
        language = self._detect_user_language(request)

        return Context(
            user=user,
            session_id=token,  # Используем токен как session_id
            platform="api",
            active_company=active_company,
            user_companies=user_companies,
            language=language,
            metadata={
                "authenticated": True,
                "api_request": True,
                "jwt_token": True
            },
        )

    async def _create_anonymous_context(self, request: Request, requested_company: Company) -> Context:
        """Создает анонимный контекст"""

        user = User(
            user_id="anonymous",
            provider=AuthProvider.YANDEX,  # Placeholder
            provider_user_id="anonymous",
            email="",
            name="Anonymous",
            status=UserStatus.ACTIVE,
            groups=["guest"],
            companies={requested_company.company_id: ["guest"]},
            active_company_id=requested_company.company_id,
        )

        # Определяем язык пользователя
        language = self._detect_user_language(request)

        context = Context(
            user=user,
            platform="api",
            active_company=requested_company,
            user_companies=[requested_company],
            language=language,
            metadata={"anonymous": True}
        )

        return context

    async def _create_amocrm_context(self, request: Request, requested_company: Company) -> Context:
        """Создает анонимный контекст"""

        user = User(
            user_id="anonymous",
            provider=None,  # TODO: сделать провайдера API?
            provider_user_id="anonymous",
            email="",
            name="Anonymous",
            status=UserStatus.ACTIVE,
            groups=["guest"],
            companies={requested_company.company_id: ["guest"]},
            active_company_id=requested_company.company_id,
        )
        language = self._detect_user_language(request)

        context = Context(
            user=user,
            platform="amocrm",
            active_company=requested_company,
            user_companies=[requested_company],
            language=language,
            metadata={"anonymous": True}
        )

        return context

    async def _create_frontend_context(self, request: Request, requested_company: Company, allow_no_company: bool = False, has_subdomain: bool = False) -> Context:
        """Создает контекст для frontend запросов на основе JWT токена"""
        container = self._get_container(request)
        user_repo = container.user_repository
        company_repo = container.company_repository
        
        # Получаем JWT токен из куки auth_token
        token = request.cookies.get("auth_token")

        logger.info(f"🍪 Проверка cookies: auth_token={'найден' if token else 'НЕ найден'}, все cookies={list(request.cookies.keys())}")

        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Проверяем JWT токен
        token_service = get_token_service()
        token_data = token_service.validate_token(token)

        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Получаем пользователя по user_id из токена
        user = await self._get_user_by_id(request, token_data.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Получаем все компании пользователя
        user_companies = await self._get_user_companies(request, user)


        # Определяем язык пользователя
        language = self._detect_user_language(request)

        # Если у пользователя нет компаний
        if not user.companies:
            if allow_no_company:
                # Разрешаем доступ к странице создания компании
                return Context(
                    user=user,
                    session_id=token_data.session_id,
                    platform="frontend",
                    active_company=None,
                    user_companies=[],
                    language=language,
                    metadata={"authenticated": True, "needs_company_creation": True, "jwt_token": True},
                )
            else:
                # Бросаем исключение для редиректа на создание компании
                raise CompanyCreationRequired()

        # Проверка: если это защищенная страница и запрос БЕЗ субдомена,
        # редиректим на выбор компании
        # Все пользователи должны работать через субдомены конкретных компаний
        if not allow_no_company and not has_subdomain:
            logger.info(f"🔄 Пользователь {user.user_id} зашел на защищенную страницу без субдомена, редиректим на выбор компании")
            raise CompanyCreationRequired()
        # Проверяем доступ к запрашиваемой компании (только если не разрешен доступ без компании)
        if not allow_no_company and requested_company.company_id not in user.companies:
            logger.warning(f"Пользователь {user.user_id} не имеет доступа к компании {requested_company.company_id}. Доступные компании: {list(user.companies.keys())}")
            # Вместо ошибки - редиректим на выбор компании
            raise CompanyCreationRequired()
        # Обновляем активную компанию у пользователя если нужно (только если не allow_no_company)
        if not allow_no_company and user.active_company_id != requested_company.company_id:
            logger.info(f"🔄 Смена активной компании: {user.active_company_id} → {requested_company.company_id}")
            user.active_company_id = requested_company.company_id
            await user_repo.set(user)
            logger.info(f"✅ Активная компания обновлена для пользователя {user.user_id}")

        # Для страниц с allow_no_company используем активную компанию пользователя или None
        active_company = None
        if not allow_no_company:
            active_company = requested_company
        elif user.active_company_id and user.active_company_id in user.companies:
            # Пытаемся загрузить активную компанию пользователя
            active_company = await company_repo.get(user.active_company_id)

        return Context(
            user=user,
            session_id=token_data.session_id,
            platform="frontend",
            active_company=active_company,
            user_companies=user_companies,
            language=language,
            metadata={"authenticated": True, "allow_no_company": allow_no_company, "jwt_token": True},
        )

    async def _get_user_companies(self, request: Request, user: User) -> List[Company]:
        """Получает все компании пользователя"""
        container = self._get_container(request)
        company_repo = container.company_repository
        companies = []
        for company_id in user.companies.keys():
            company = await company_repo.get(company_id)
            if company:
                companies.append(company)
        return companies

    async def _get_user_by_id(self, request: Request, user_id: str) -> Optional[User]:
        """Получает пользователя по ID"""
        container = self._get_container(request)
        return await container.user_repository.get(user_id)

    async def _update_user_active_company(self, request: Request, user: User):
        """Обновляет активную компанию пользователя"""
        container = self._get_container(request)
        await container.user_repository.set(user)
