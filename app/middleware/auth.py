"""
Middleware для создания глобального контекста запроса
"""

import logging
import json
from typing import List, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.responses import RedirectResponse, JSONResponse
from ..core.context import set_context, clear_context
from ..models import Context
from ..core.config import settings
from ..identity.models import User, AuthProvider, UserStatus, Company
from ..identity.auth_service import AuthService
from ..core.storage import Storage
from ..models.i18n_models import Language
from fastapi.responses import RedirectResponse
logger = logging.getLogger(__name__)


class CompanyCreationRequired(Exception):
    """Исключение для случаев когда нужно создать компанию"""
    pass


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для создания RequestContext с пользователем"""

    def __init__(self, app):
        super().__init__(app)
        self.storage = Storage()

    async def dispatch(self, request: Request, call_next):
        # Пропускаем middleware для статики и служебных путей
        if (
            request.url.path.startswith("/static/")
            or request.url.path.startswith("/.well-known/")
            or request.url.path.startswith("/favicon.ico")
            or request.url.path.startswith("/api/v1/payments/webhook/")  # Webhook публичные
        ):
            return await call_next(request)

        # Для скачивания файлов - создаем минимальный контекст с компанией из поддомена
        if request.url.path.startswith("/api/v1/files/download/"):
            try:
                # Определяем компанию по Host
                requested_company = await self._get_company_from_host(request)

                # Создаем минимальный анонимный контекст с этой компанией
                context = await self._create_anonymous_context(request, requested_company)
                set_context(context)
                request.state.context = context
                request.state.user = context.user

                request.state.language = context.language.value

                logger.info(f"📂 Контекст для скачивания файла: компания {requested_company.company_id}")

            except Exception as e:
                logger.error(f"❌ Не удалось создать контекст для скачивания файла: {e}")
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

            # Продолжаем обработку
            response = await call_next(request)
            return response

        except CompanyCreationRequired:
            # Всегда редиректим на выбор компании на основном домене
            # Страница сама разберется - если компаний нет, перенаправит на создание
            base_url = f"https://{settings.server.domain}" if settings.server.env != "local" else f"http://{settings.server.domain}:{settings.server.port}"
            return RedirectResponse(url=f"{base_url}/frontend/select-company", status_code=307)
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

        # НОВОЕ: Определяем запрашиваемую компанию по Host
        requested_company = await self._get_company_from_host(request)

        # Определяем платформу по URL
        if "/webhook/telegram/" in path:
            logger.info("📱 Telegram контекст")
            return await self._create_telegram_context(request, requested_company)
        elif path == "/api/v1/admin/create-my-company":
            logger.info("🏢 API создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True)
        elif "/api/v1/" in path:
            logger.info("🔌 API контекст")
            return await self._create_api_context(request, requested_company)
        elif "/api/amocrm" in path:
            logger.info("🔌 AmoCRM контекст")
            return await self._create_amocrm_context(request, requested_company)
        elif path == "/frontend/auth":
            logger.info("🔐 Страница авторизации - публичная")
            return await self._create_anonymous_context(request, requested_company)
        elif path == "/frontend/create-company":
            logger.info("🏢 Страница создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True)
        elif path == "/frontend/select-company":
            logger.info("🏢 Страница выбора компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True)
        elif path.startswith("/frontend/models/create_company_form/"):
            logger.info("🏢 API для формы создания компании - требует авторизации")
            return await self._create_frontend_context(request, requested_company, allow_no_company=True)
        elif path.startswith("/frontend/"):
            logger.info("🖥️ Frontend контекст - требует авторизации")
            return await self._create_frontend_context(request, requested_company)
        elif path.startswith("/auth/"):
            logger.info("🔐 OAuth контекст")
            return await self._create_anonymous_context(request, requested_company)
        elif path == "/":
            logger.info("🏠 Корневой путь - пропускаем через middleware")
            # Для главной страницы пытаемся создать frontend контекст, но без ошибки если пользователь не авторизован
            try:
                return await self._create_frontend_context(request, requested_company, allow_no_company=True)
            except HTTPException:
                # Если авторизация не удалась, создаем анонимный контекст
                logger.info("🏠 Пользователь не авторизован, создаем анонимный контекст")
                return await self._create_anonymous_context(request, requested_company)
        elif path in ("/docs", "/redoc", "/openapi.json") and settings.server.env == "local":
            logger.info("🔍 Docs контекст")
            return await self._create_anonymous_context(request, requested_company)
            logger.info("🏠 Корневой путь - проверяем авторизацию")
        else:
            logger.warning(f"❌ Неизвестный путь: {path}")
            raise HTTPException(status_code=404, detail="Not Found")

    async def _get_company_from_host(self, request: Request) -> Company:
        """Определяет компанию по Host заголовку"""
        host = request.headers.get("host", "")
        domain = settings.server.domain

        logger.info(f"🔍 Определяем компанию: host={host}, domain={domain}, env={settings.server.env}")

        # Специальная логика для локальной разработки
        if settings.server.env == "local" and ".localhost" in host:
            # Для localhost: ssd.localhost:8001 -> subdomain = ssd
            subdomain = host.split(".")[0]
            logger.info(f"🔍 Local режим: subdomain={subdomain}")
            company_id = await self.storage.get(f"subdomain:{subdomain}", force_global=True)
            if company_id:
                # Убираем кавычки если они есть
                clean_company_id = company_id.strip('"') if isinstance(company_id, str) else company_id
                company_data = await self.storage.get(f"company:{clean_company_id}", force_global=True)
                if company_data:
                    logger.info(f"✅ Найдена компания по поддомену: {clean_company_id}")
                    return Company.model_validate_json(company_data)

        # Продакшен логика
        elif host.endswith(f".{domain}") and not host.startswith(domain):
            subdomain = host.split(".")[0]
            logger.info(f"🔍 Продакшен режим: subdomain={subdomain}")
            company_id = await self.storage.get(f"subdomain:{subdomain}", force_global=True)
            logger.info(f"🔍 company_id из storage: {company_id}")
            if company_id:
                clean_company_id = company_id.strip('"') if isinstance(company_id, str) else company_id
                company_data = await self.storage.get(f"company:{clean_company_id}", force_global=True)
                if company_data:
                    logger.info(f"✅ Найдена компания по поддомену: {clean_company_id}")
                    return Company.model_validate_json(company_data)

            # Если поддомен есть, но компания не найдена - это ошибка
            logger.error(f"❌ Компания не найдена для поддомена: {subdomain}")
            raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")

        # Если это основной домен (без поддомена) - возвращаем системную компанию
        logger.info(f"🔍 Основной домен без поддомена, возвращаем системную компанию")
        return await self._get_system_company()

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

    async def _get_default_company(self) -> Company:
        """Возвращает главную компанию по умолчанию"""
        # Ищем главную компанию или создаем если не существует
        company_data = await self.storage.get("company:main", force_global=True)
        if company_data:
            return Company.model_validate_json(company_data)

        # Создаем главную компанию
        main_company = Company(
            company_id="main",
            subdomain="main",
            name="Agents Lab",
            status="active"
        )
        await self.storage.set("company:main", main_company.model_dump_json(), force_global=True)
        await self.storage.set("subdomain:main", "main", force_global=True)
        return main_company

    async def _get_system_company(self) -> Company:
        """Возвращает системную компанию"""
        company_data = await self.storage.get("company:system", force_global=True)
        if company_data:
            return Company.model_validate_json(company_data)

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

        return Context(
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


    async def _create_api_context(self, request: Request, requested_company: Company) -> Context:
        """Создает контекст для API запросов"""

        # Получаем session_id из куки или заголовка Authorization
        session_id = request.cookies.get("session_id")

        # Если нет куки, проверяем заголовок Authorization
        if not session_id:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                session_id = auth_header[7:]  # Убираем "Bearer "

        # Сессия обязательна для API запросов
        if not session_id:
            raise HTTPException(status_code=401, detail="Session required")

        # Получаем пользователя по сессии
        auth_service = AuthService()
        user = await auth_service.get_user_by_session(session_id)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")

        # Получаем все компании пользователя
        user_companies = await self._get_user_companies(user)

        # Проверяем доступ к запрашиваемой компании
        if requested_company.company_id not in user.companies:
            # Если у пользователя нет доступа к запрашиваемой компании,
            # используем его активную компанию или первую доступную
            active_company = None
            if user.active_company_id and user.active_company_id in user.companies:
                company_data = await self.storage.get(f"company:{user.active_company_id}", force_global=True)
                if company_data:
                    active_company = Company.model_validate_json(company_data)

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
                await self._update_user_active_company(user)

        # Определяем язык пользователя
        language = self._detect_user_language(request)

        return Context(
            user=user,
            session_id=session_id,
            platform="api",
            active_company=active_company,
            user_companies=user_companies,
            language=language,
            metadata={"authenticated": True},
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

        return Context(
            user=user,
            platform="amocrm",
            active_company=requested_company,
            user_companies=[requested_company],
            metadata={"anonymous": True}
        )

    async def _create_amocrm_context(self, request: Request, requested_company: Company) -> Context:
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

        return Context(
            user=user,
            platform="amocrm",
            active_company=requested_company,
            user_companies=[requested_company],
            language=language,
            metadata={"anonymous": True}
        )

    async def _create_frontend_context(self, request: Request, requested_company: Company, allow_no_company: bool = False) -> Context:
        """Создает контекст для frontend запросов на основе куки"""
        # Получаем session_id из куки
        session_id = request.cookies.get("session_id")

        if not session_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Пытаемся найти пользователя по сессии
        auth_service = AuthService()

        user = await auth_service.get_user_by_session(session_id)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")

        # Получаем все компании пользователя
        user_companies = await self._get_user_companies(user)


        # Определяем язык пользователя
        language = self._detect_user_language(request)

        # Если у пользователя нет компаний
        if not user.companies:
            if allow_no_company:
                # Разрешаем доступ к странице создания компании
                return Context(
                    user=user,
                    session_id=session_id,
                    platform="frontend",
                    active_company=None,
                    user_companies=[],
                    language=language,
                    metadata={"authenticated": True, "needs_company_creation": True},
                )
            else:
                # Бросаем исключение для редиректа на создание компании
                raise CompanyCreationRequired()

        # Проверяем доступ к запрашиваемой компании (только если не разрешен доступ без компании)
        if not allow_no_company and requested_company.company_id not in user.companies:
            logger.warning(f"Пользователь {user.user_id} не имеет доступа к компании {requested_company.company_id}. Доступные компании: {list(user.companies.keys())}")
            # Вместо ошибки - редиректим на выбор компании
            raise CompanyCreationRequired()  # Переиспользуем исключение для редиректа

        # Обновляем активную компанию у пользователя если нужно (только если не allow_no_company)
        if not allow_no_company and user.active_company_id != requested_company.company_id:
            logger.info(f"🔄 Смена активной компании: {user.active_company_id} → {requested_company.company_id}")
            user.active_company_id = requested_company.company_id
            await self._update_user_active_company(user)
            logger.info(f"✅ Активная компания обновлена для пользователя {user.user_id}")

        # Для страниц с allow_no_company используем активную компанию пользователя или None
        active_company = None
        if not allow_no_company:
            active_company = requested_company
        elif user.active_company_id and user.active_company_id in user.companies:
            # Пытаемся загрузить активную компанию пользователя
            company_data = await self.storage.get(f"company:{user.active_company_id}", force_global=True)
            if company_data:
                active_company = Company.model_validate_json(company_data)

        return Context(
            user=user,
            session_id=session_id,
            platform="frontend",
            active_company=active_company,
            user_companies=user_companies,
            language=language,
            metadata={"authenticated": True, "allow_no_company": allow_no_company},
        )

    async def _get_user_companies(self, user: User) -> List[Company]:
        """Получает все компании пользователя"""
        companies = []
        for company_id in user.companies.keys():
            company_data = await self.storage.get(f"company:{company_id}", force_global=True)
            if company_data:
                companies.append(Company.model_validate_json(company_data))
        return companies

    async def _update_user_active_company(self, user: User):
        """Обновляет активную компанию пользователя в БД"""
        user_key = f"user:{user.user_id}"
        await self.storage.set(user_key, user.model_dump_json(), force_global=True)
