"""
Фабрика FastAPI-приложения сервиса.

``create_service_app`` — единственный вход HTTP-процесса: настройки, логирование, middleware,
платформенные роутеры и lifespan, который eagerly собирает ``<Svc>Di`` через ``open_di``.

Пример:
    from core.app import create_service_app
    from apps.secrets.config import SecretsSettings
    from apps.secrets.di import SecretsDi
    from apps.secrets.realtime.command_router import SECRETS_OPERATIONS

    app = create_service_app(
        "secrets",
        SecretsSettings,
        SecretsDi,
        database="secrets_url",
        operations=SECRETS_OPERATIONS,
        routers=[get_api_router()],
    )
"""

from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError
from starlette.types import ExceptionHandler

from core.api.auth import router as core_auth_router
from core.api.calendar import router as core_calendar_router
from core.api.companies import router as core_companies_router
from core.api.customer_auth import customer_auth_router
from core.api.integrations import router as core_integrations_router
from core.api.mail import router as core_mail_router
from core.api.platform_brand import router as platform_brand_router
from core.api.team import router as core_team_router
from core.app.file_types_route import register_platform_file_types_route
from core.app.health_payload import build_health_payload
from core.app.i18n_routes import register_platform_i18n_routes
from core.app.pwa_routes import register_platform_pwa_routes
from core.authz.errors import AuthzConfigError, AuthzDenied, AuthzUnavailable
from core.billing import set_billing_service
from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro
from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once
from core.billing.exceptions import BillingBalanceBlockedError
from core.config import BaseSettings as PlatformBaseSettings
from core.config import set_settings
from core.config.loader import get_project_root, load_merged_config
from core.config.testing import is_testing
from core.di.kit import ProcessIdentity, Recipe, ServiceDi
from core.di.platform import PlatformDi
from core.di.process import open_di
from core.di.state import reset_app_di, set_app_di
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.events import store_registered_platform_events
from core.events.publisher import close_publisher_client
from core.files.api import build_files_router
from core.files.processors import initialize_default_processors
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.frontend.documentation_mount import mount_documentation_static
from core.logging import (
    SystemLogScope,
    get_logger,
)
from core.logging.setup import setup_logging
from core.middleware.access_log import AccessLogMiddleware
from core.middleware.auth import AuthMiddleware
from core.middleware.deployment_headers import DeploymentHeadersMiddleware
from core.middleware.dev_inter_service_proxy import (
    DevInterServiceProxyMiddleware,
    DevInterServiceWsProxyMiddleware,
)
from core.middleware.platform_error_envelope import PlatformHttpErrorEnvelopeMiddleware
from core.middleware.proxy_headers import ProxyHeadersMiddleware
from core.middleware.static_core_module_cors import StaticCoreModuleCorsMiddleware
from core.push.apns_credentials import resolve_apns_credentials
from core.push.apns_service import init_apns_push_service
from core.push.fcm_credentials import resolve_fcm_credentials
from core.push.fcm_service import init_fcm_push_service
from core.push.router import router as push_router
from core.push.service import init_web_push_service
from core.realtime.command_http import router as realtime_command_router
from core.tracing import setup_tracing
from core.tracing.tracer import set_tracing_service_name
from core.types import JsonObject, JsonValue, MigrationDatabaseUrlKey
from core.utils.background import run_with_log_context
from core.websocket import WsCommandError, command_failure_payload
from core.websocket.operation import (
    WS_COMMAND_ERROR_HTTP_STATUS,
    RegisteredOperation,
    register_operations,
    ws_command_error_status,
)

logger = get_logger(__name__)

SettingsT = TypeVar("SettingsT", bound=PlatformBaseSettings)
DiT = TypeVar("DiT", bound=ServiceDi)
ServiceLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def load_service_settings(
    service_name: str, settings_class: type[SettingsT]
) -> tuple[SettingsT, Path]:
    """
    Загружает настройки сервиса (merge без логов до setup_logging).

    Вызов set_settings(settings) — ответственность create_service_app после
    setup_logging.

    Возвращает:
        (settings, project_root)
    """
    project_root = get_project_root()

    merged_config = load_merged_config(service_name=service_name, silent=True)

    settings = settings_class.model_validate(merged_config)

    return settings, project_root


def prepare_service_settings(
    service_name: str,
    settings_class: type[SettingsT],
    *,
    documentation_gateway_prefix: str | None,
) -> tuple[SettingsT, Path, str]:
    """Настройки процесса, логирование и Files-сегмент — до создания приложения."""
    settings, project_root = load_service_settings(service_name, settings_class)
    setup_logging(service_name, settings.logging)
    set_settings(settings)
    files_segment = resolve_files_route_segment(
        service_name,
        documentation_gateway_prefix=documentation_gateway_prefix,
    )
    set_files_route_segment(files_segment)
    return settings, project_root, files_segment


async def start_platform_process(
    settings: PlatformBaseSettings,
    *,
    service_name: str,
    tracing: bool,
    platform: bool,
) -> None:
    """Tracing, каталог событий, курс ЦБ, file processors и push процесса."""
    # Лёгкие sandbox-сервисы пишут spans, но не поднимают billing/push.
    if tracing and settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled:
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled requires database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name(service_name)
        logger.info("app.event")

    if not platform:
        return

    await store_registered_platform_events()

    # Курс USD/RUB от ЦБ РФ: один запрос при старте, затем фоновое обновление каждые 5 минут.
    # Резерв при недоступности ЦБ — billing.usd_to_rub_rate из конфига.
    cbr_fallback = settings.billing.usd_to_rub_rate
    if is_testing():
        logger.info("billing.cbr_rate.skipped_testing", fallback=cbr_fallback)
    else:
        await _cbr_refresh_once(fallback=cbr_fallback)
        _ = run_with_log_context(
            _cbr_loop_coro(fallback=cbr_fallback),
            name="billing.cbr_rate_refresh",
            background_kind="startup",
        )
        logger.info("billing.cbr_rate.loop_scheduled")

    initialize_default_processors()
    logger.info("app.initialize_default_processors")

    if settings.push.enabled:
        if not settings.push.vapid_private_key or not settings.push.vapid_public_key:
            raise ValueError(
                "push.enabled=true requires push.vapid_private_key and push.vapid_public_key"
            )
        _ = init_web_push_service(
            vapid_private_key=settings.push.vapid_private_key,
            vapid_public_key=settings.push.vapid_public_key,
            vapid_email=settings.push.vapid_email,
        )
        logger.info("app.webpushservice")

    apns = resolve_apns_credentials(settings)
    if apns:
        _ = init_apns_push_service(
            team_id=apns.team_id,
            key_id=apns.key_id,
            private_key_pem=apns.private_key_pem,
            bundle_id=apns.bundle_id,
            use_sandbox=apns.use_sandbox,
        )
        logger.info("app.apnspushservice")

    fcm = resolve_fcm_credentials(settings.push)
    if fcm:
        _ = init_fcm_push_service(
            project_id=fcm.project_id,
            client_email=fcm.client_email,
            private_key_pem=fcm.private_key_pem,
            token_uri=fcm.token_uri,
        )
        logger.info("app.fcmpushservice.project_id", project_id=fcm.project_id)


async def stop_platform_process(*, platform: bool) -> None:
    # В одном процессе pytest поднимается несколько приложений; Redis-клиент шины
    # (publish/catalog) привязан к event loop TestClient — на shutdown в тестах он
    # закрывается, иначе следующий TestClient ловит «Event loop is closed».
    if platform and is_testing():
        await close_publisher_client()


def create_service_app(
    service_name: str,
    settings_class: type[SettingsT],
    di_class: type[DiT],
    *,
    database: MigrationDatabaseUrlKey,
    operations: Mapping[str, RegisteredOperation[DiT]] | None = None,
    lifecycle: tuple[Recipe, ...] = (),
    routers: list[APIRouter] | None = None,
    pages_routers: list[APIRouter] | None = None,
    cors_origins: list[str] | None = None,
    cors_allow_origin_regex: str | None = None,
    extra_middlewares: Sequence[tuple[type, Mapping[str, JsonValue]]] | None = None,
    outer_middlewares: Sequence[tuple[type, Mapping[str, JsonValue]]] | None = None,
    extra_exception_handlers: Sequence[tuple[type[Exception], ExceptionHandler]] | None = None,
    static_mounts: list[tuple[str, str, str]] | None = None,
    title: str | None = None,
    description: str | None = None,
    version: str = "1.0.0",
    api_version: str | None = "v1",
    docs_url: str = "/docs",
    redoc_url: str = "/redoc",
    openapi_url: str = "/openapi.json",
    include_auth_middleware: bool = True,
    include_tracing_lifecycle: bool | None = None,
    include_platform_lifecycle: bool = True,
    include_platform_routers: bool = True,
    mount_repo_documentation: bool = True,
    documentation_gateway_prefix: str | None = None,
    include_platform_pwa: bool | None = None,
    services_spa_index: Path | None = None,
) -> FastAPI:
    """
    Создаёт FastAPI приложение сервиса на Service Kit.

    Аргументы:
        service_name: Имя сервиса (например, "secrets")
        settings_class: Класс настроек (наследник BaseSettings)
        di_class: Класс ``<Svc>Di`` процесса; сервис с платформенными роутерами или
            AuthMiddleware наследует ``PlatformDi``
        database: Ключ URL базы процесса (``secrets_url``, ``shared_url``, …)
        operations: Каталог команд ``<SVC>_OPERATIONS``; DI команда берёт из этого приложения
        lifecycle: Процессные ресурсы (фоновые циклы, seeds): autowired ``@recipe`` с ``None``
        routers: Список API роутеров (prefix зависит от api_version)
        pages_routers: Список page роутеров (без prefix - они имеют свой)
        cors_origins: Разрешенные origins для CORS (конкретные URL; с credentials нельзя звёздочку как единственный origin)
        cors_allow_origin_regex: Regex для Origin (Starlette CORSMiddleware), суммируется с allow_origins
        extra_middlewares: Дополнительные middleware [(MiddlewareClass, {kwargs}), ...]
            внутри общего CORSMiddleware.
        outer_middlewares: Middleware снаружи CORSMiddleware. Нужны, когда preflight
            конкретного пути не должен отвечать общий CORS (embed A2A).
        extra_exception_handlers: Обработчики внешних wire-спек поверх платформенных [(ExcType, handler), ...]
            (например OpenAI error envelope на LLM proxy flows); платформенный JSON-конверт они не заменяют.
        static_mounts: Статические директории [(path, directory, name), ...]
        api_version: Версия API ("v1" для flows и др., None для frontend)
        docs_url, redoc_url, openapi_url: Пути для документации
        include_auth_middleware: Включать ли AuthMiddleware
        include_tracing_lifecycle: Включать ли tracing startup hooks. None — вместе с include_platform_lifecycle.
        include_platform_lifecycle: Включать ли каталог событий/курс ЦБ/push startup hooks
        include_platform_routers: Включать ли общие платформенные роутеры (files/auth/calendar/ws/i18n)
        mount_repo_documentation: Смонтировать статическую документацию (Zensical) из корня репозитория ``documentation-dist/`` на ``/documentation/``.
        documentation_gateway_prefix: Если задан (например ``documents`` для office), первый сегмент публичных путей HTTP API и платформенных роутеров (team, files, auth, …); плюс дублирование документации на ``/{prefix}/documentation/`` за ingress. Internal command hop всегда ``/{service_name}/api/internal/realtime/command``.
        include_platform_pwa: Маршруты ``/manifest.json``, ``/sw.js``, ``/offline.html``. None: выключено при ``TESTING=true``, иначе включено.
        services_spa_index: Путь к ``index.html`` SPA; если файл существует, регистрируются
            ``GET /{public_segment}/services`` и ``GET /{public_segment}/services/`` с тем же HTML.
    """
    if (include_platform_routers or include_auth_middleware) and not issubclass(
        di_class, PlatformDi
    ):
        raise TypeError(
            f"{di_class.__qualname__} must inherit PlatformDi: the app mounts platform routers or AuthMiddleware"
        )
    tracing_lifecycle_enabled = (
        include_platform_lifecycle
        if include_tracing_lifecycle is None
        else include_tracing_lifecycle
    )
    settings, project_root, files_segment = prepare_service_settings(
        service_name,
        settings_class,
        documentation_gateway_prefix=documentation_gateway_prefix,
    )
    identity = ProcessIdentity(service_name=service_name, files_route_segment=files_segment)
    if operations is not None:
        register_operations(operations, di_class)

    # Lifespan: системный скоуп — нет request_id/user_id, но нужен canonical service.name
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            async with SystemLogScope(lifecycle_phase="startup"):
                logger.info("service.starting", service=service_name)
                await start_platform_process(
                    settings,
                    service_name=service_name,
                    tracing=tracing_lifecycle_enabled,
                    platform=include_platform_lifecycle,
                )
                di = await stack.enter_async_context(
                    open_di(
                        di_class,
                        settings=settings,
                        identity=identity,
                        database=database,
                        lifecycle=lifecycle,
                    )
                )
                if isinstance(di, PlatformDi):
                    set_billing_service(di.billing_service)
                outer_di = set_app_di(app, di)
                logger.info("service.started", service=service_name)
            yield
            async with SystemLogScope(lifecycle_phase="shutdown"):
                logger.info("service.stopping", service=service_name)
                reset_app_di(app, outer_di)
                await stack.aclose()
                await stop_platform_process(platform=include_platform_lifecycle)

    return assemble_service_app(
        service_name=service_name,
        settings=settings,
        project_root=project_root,
        lifespan=lifespan,
        routers=routers,
        pages_routers=pages_routers,
        cors_origins=cors_origins,
        cors_allow_origin_regex=cors_allow_origin_regex,
        extra_middlewares=extra_middlewares,
        outer_middlewares=outer_middlewares,
        extra_exception_handlers=extra_exception_handlers,
        static_mounts=static_mounts,
        title=title,
        description=description,
        version=version,
        api_version=api_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        include_auth_middleware=include_auth_middleware,
        include_platform_routers=include_platform_routers,
        mount_repo_documentation=mount_repo_documentation,
        documentation_gateway_prefix=documentation_gateway_prefix,
        include_platform_pwa=include_platform_pwa,
        services_spa_index=services_spa_index,
    )


def assemble_service_app(
    *,
    service_name: str,
    settings: PlatformBaseSettings,
    project_root: Path,
    lifespan: ServiceLifespan,
    routers: list[APIRouter] | None,
    pages_routers: list[APIRouter] | None,
    cors_origins: list[str] | None,
    cors_allow_origin_regex: str | None,
    extra_middlewares: Sequence[tuple[type, Mapping[str, JsonValue]]] | None,
    outer_middlewares: Sequence[tuple[type, Mapping[str, JsonValue]]] | None,
    extra_exception_handlers: Sequence[tuple[type[Exception], ExceptionHandler]] | None,
    static_mounts: list[tuple[str, str, str]] | None,
    title: str | None,
    description: str | None,
    version: str,
    api_version: str | None,
    docs_url: str,
    redoc_url: str,
    openapi_url: str,
    include_auth_middleware: bool,
    include_platform_routers: bool,
    mount_repo_documentation: bool,
    documentation_gateway_prefix: str | None,
    include_platform_pwa: bool | None,
    services_spa_index: Path | None,
) -> FastAPI:
    """Middleware, обработчики ошибок, роутеры и статика — одинаково для каждого сервиса."""
    # Создание приложения
    app = FastAPI(
        title=title or f"{service_name.title()} Service",
        version=version,
        description=description or f"Сервис {service_name}",
        lifespan=lifespan,
        debug=settings.server.debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    app.state.settings = settings

    @app.exception_handler(BillingBalanceBlockedError)
    async def _billing_balance_blocked_handler(
        _request: Request, exc: BillingBalanceBlockedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "code": "billing_balance_blocked"},
        )

    _ = _billing_balance_blocked_handler

    @app.exception_handler(AuthzDenied)
    async def _authz_denied_handler(_request: Request, exc: AuthzDenied) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": str(exc), "code": "authz_denied"},
        )

    _ = _authz_denied_handler

    @app.exception_handler(AuthzUnavailable)
    async def _authz_unavailable_handler(_request: Request, exc: AuthzUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "code": "authz_unavailable"},
        )

    _ = _authz_unavailable_handler

    @app.exception_handler(AuthzConfigError)
    async def _authz_config_error_handler(_request: Request, exc: AuthzConfigError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "code": "authz_unavailable"},
        )

    _ = _authz_config_error_handler

    def _boundary_error_response(
        transport_code: str,
        detail: str,
        *,
        error_code: str,
        error_params: JsonObject,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=WS_COMMAND_ERROR_HTTP_STATUS[transport_code],
            content=command_failure_payload(
                WsCommandError(
                    transport_code,
                    detail,
                    error_code=error_code,
                    error_params=error_params,
                )
            ),
        )

    def _platform_boundary_response(
        transport_code: str, exc: PlatformBoundaryError
    ) -> JSONResponse:
        return _boundary_error_response(
            transport_code,
            str(exc),
            error_code=exc.error_code,
            error_params=exc.error_params,
        )

    @app.exception_handler(WsCommandError)
    async def _ws_command_error_handler(_request: Request, exc: WsCommandError) -> JSONResponse:
        return JSONResponse(
            status_code=ws_command_error_status(exc),
            content=command_failure_payload(exc),
        )

    _ = _ws_command_error_handler

    @app.exception_handler(PlatformNotFoundError)
    async def _platform_not_found_handler(
        _request: Request, exc: PlatformNotFoundError
    ) -> JSONResponse:
        return _platform_boundary_response("not_found", exc)

    _ = _platform_not_found_handler

    @app.exception_handler(PlatformConflictError)
    async def _platform_conflict_handler(
        _request: Request, exc: PlatformConflictError
    ) -> JSONResponse:
        return _platform_boundary_response("conflict", exc)

    _ = _platform_conflict_handler

    @app.exception_handler(PlatformAccessDeniedError)
    async def _platform_access_denied_handler(
        _request: Request, exc: PlatformAccessDeniedError
    ) -> JSONResponse:
        return _platform_boundary_response("forbidden", exc)

    _ = _platform_access_denied_handler

    @app.exception_handler(PlatformUnavailableError)
    async def _platform_unavailable_handler(
        _request: Request, exc: PlatformUnavailableError
    ) -> JSONResponse:
        return _platform_boundary_response("unavailable", exc)

    _ = _platform_unavailable_handler

    @app.exception_handler(PydanticValidationError)
    async def _payload_validation_handler(
        _request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        """REST-зеркало собирает payload `op_*` вручную — ошибка модели равна ошибке валидации запроса."""
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "ws_invalid_payload",
                "error_detail": str(exc),
                "detail": jsonable_encoder(exc.errors(include_url=False)),
            },
        )

    _ = _payload_validation_handler

    for exception_type, exception_handler in extra_exception_handlers or ():
        app.add_exception_handler(exception_type, exception_handler)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Гарантирует одну structured-запись на каждое необработанное исключение.

        Не глотает: после логирования возвращает 500 JSON. Тело по умолчанию без
        текста исключения (клиент / межсервис). При ``server.debug=True`` добавляется
        ``exception_detail`` (локальная отладка). ``exception_type`` — всегда, имя класса.
        """
        exc_cls = type(exc).__name__
        logger.exception(
            "http_unhandled_exception",
            **{
                "exception.type": exc_cls,
                "http.path": request.url.path,
                "http.method": request.method,
            },
        )
        payload: JsonObject = {
            "detail": "Internal Server Error",
            "code": "internal_error",
            "exception_type": exc_cls,
        }
        if settings.server.debug:
            payload["exception_detail"] = str(exc)[:4096]
        return JSONResponse(status_code=500, content=payload)

    _ = _unhandled_exception_handler

    # CORS собираем здесь, подключаем в конце create_service_app (внешний слой стека).
    # Иначе preflight OPTIONS обрабатывает AuthMiddleware раньше и отдаёт 404 без ACAO.
    cors_allow_origins = list(cors_origins) if cors_origins else []
    cors_allow_methods = ["*"]
    cors_allow_headers = ["*"]
    resolved_cors_allow_origin_regex = (
        cors_allow_origin_regex.strip()
        if cors_allow_origin_regex and cors_allow_origin_regex.strip()
        else None
    )

    # Заголовки прокси
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

    # Auth middleware (внутренний слой: bind user/company/session, set_context)
    if include_auth_middleware:
        app.add_middleware(AuthMiddleware)

    # Access log (внешний слой: вход в request-скоуп — request_id/trace_id;
    # видит финальный status_code и duration_ms; снимает скоуп в finally).
    app.add_middleware(AccessLogMiddleware, service_name=service_name)

    # Дополнительные middleware
    if extra_middlewares:
        for middleware_class, kwargs in extra_middlewares:
            app.add_middleware(middleware_class, **dict(kwargs))

    app.add_middleware(DeploymentHeadersMiddleware)

    # Локальный dev/test: браузер на :8002 с путём /flows/... без ingress — пересылаем на flows_service_url
    app.add_middleware(DevInterServiceProxyMiddleware, service_name=service_name)
    # Тот же прокси, но для WebSocket-апгрейдов: ASGI-уровневый, BaseHTTPMiddleware WS не покрывает.
    app.add_middleware(DevInterServiceWsProxyMiddleware, service_name=service_name)

    # Наружный слой — обогащение JSON ошибок (последний в цепочке add_middleware).
    app.add_middleware(PlatformHttpErrorEnvelopeMiddleware, service_name=service_name)

    # Первый сегмент публичного URL: обычно совпадает с service_name.
    # Исключение — office (документы): в браузере /documents/..., задаётся
    # documentation_gateway_prefix (см. office.mdc, SERVICE_PUBLIC_NAME в CI).
    url_route_segment = documentation_gateway_prefix or service_name

    # api_version="v1" → /{segment}/api/v1 (REST API)
    # api_version=None → /{segment} (сайт без /api/)
    if api_version:
        api_prefix = f"/{url_route_segment}/api/{api_version}"
    else:
        api_prefix = f"/{url_route_segment}"
    logger.info("service.api_prefix", api_prefix=api_prefix)

    # API роутеры (с prefix /service_name/api/v1)
    if routers:
        for router in routers:
            tags = router.tags or [service_name]
            app.include_router(router, prefix=api_prefix, tags=tags)

    public_segment = url_route_segment

    if include_platform_routers:
        files_api_prefix = f"/{url_route_segment}/api/{api_version or 'v1'}/files"
        _files_router = build_files_router(files_route_segment=url_route_segment)
        app.include_router(_files_router, prefix=files_api_prefix)
        logger.info("service.router_attached", router="files", prefix=files_api_prefix)

        auth_prefix = f"/{public_segment}/api/auth"
        logger.info("service.router_attached", router="core_auth", prefix=auth_prefix)
        app.include_router(core_auth_router, prefix=auth_prefix, tags=["auth"])
        if service_name == "frontend":
            logger.info("service.router_attached", router="core_auth_oauth", prefix="/auth")
            app.include_router(core_auth_router, prefix="/auth", tags=["auth"])

        calendar_prefix = f"/{public_segment}/api/calendar"
        logger.info("service.router_attached", router="core_calendar", prefix=calendar_prefix)
        app.include_router(core_calendar_router, prefix=calendar_prefix, tags=["calendar"])

        mail_prefix = f"/{public_segment}/api/mail"
        logger.info("service.router_attached", router="core_mail", prefix=mail_prefix)
        app.include_router(core_mail_router, prefix=mail_prefix, tags=["mail"])

        integrations_prefix = f"/{public_segment}"
        logger.info(
            "service.router_attached", router="core_integrations", prefix=integrations_prefix
        )
        app.include_router(
            core_integrations_router, prefix=integrations_prefix, tags=["integrations"]
        )

        team_prefix = f"/{public_segment}/api/team"
        logger.info("service.router_attached", router="core_team", prefix=team_prefix)
        app.include_router(core_team_router, prefix=team_prefix, tags=["team"])

        if service_name == "frontend":
            companies_prefix = "/frontend/api/companies"
        else:
            companies_prefix = f"/{public_segment}/api/companies"
        logger.info("service.router_attached", router="core_companies", prefix=companies_prefix)
        app.include_router(core_companies_router, prefix=companies_prefix, tags=["companies"])

        push_prefix = f"/{public_segment}"
        logger.info("service.router_attached", router="push", prefix=f"{push_prefix}/api/push")
        app.include_router(push_router, prefix=push_prefix, tags=["push"])

        # Customer-auth — платформенная авторизация покупателя по телефону.
        # Анонимность решает route_config (`/{seg}/api/v1/public/*`), не mount.
        customer_auth_prefix = f"{api_prefix}/public"
        logger.info(
            "service.router_attached",
            router="customer_auth",
            prefix=f"{customer_auth_prefix}/customer-auth",
        )
        app.include_router(
            customer_auth_router, prefix=customer_auth_prefix, tags=["customer-auth"]
        )

        brand_prefix = "/frontend"
        logger.info(
            "service.router_attached",
            router="platform_brand",
            prefix=f"{brand_prefix}/api/platform",
        )
        app.include_router(platform_brand_router, prefix=brand_prefix, tags=["platform-brand"])

    # Internal hop bus realtime → владелец команды: монтируется на каждом сервисе,
    # включая те, что без платформенных роутеров (search).
    command_prefix = f"/{service_name}/api"
    logger.info(
        "service.router_attached",
        router="realtime_command",
        path=f"{command_prefix}/internal/realtime/command",
    )
    app.include_router(realtime_command_router, prefix=command_prefix, tags=["realtime-command"])

    # Pages роутеры (добавляем префикс сервиса к их собственному префиксу)
    if pages_routers:
        for router in pages_routers:
            tags = router.tags or [f"{service_name}-pages"]
            # Добавляем только префикс публичного пути (public_segment), FastAPI сам добавит его к prefix роутера
            if hasattr(router, "prefix") and router.prefix:
                app.include_router(router, prefix=f"/{public_segment}", tags=tags)
            else:
                # Роутер без префикса подключается как есть
                app.include_router(router, tags=tags)

    # Статические файлы
    if static_mounts:
        for mount_path, directory, name in static_mounts:
            if not Path(directory).is_dir():
                raise FileNotFoundError(f"static mount {name}: directory not found: {directory}")
            app.mount(mount_path, StaticFiles(directory=directory), name=name)

    if mount_repo_documentation:
        mount_documentation_static(
            app,
            project_root,
            gateway_prefix=documentation_gateway_prefix,
        )

    if include_platform_pwa is None:
        include_platform_pwa = not is_testing()

    if include_platform_routers and include_platform_pwa:
        register_platform_pwa_routes(app, project_root)
        logger.info("app.pwa.manifest.json.sw.js")

    if include_platform_routers:
        register_platform_i18n_routes(app, project_root)
        logger.info("app.i18n.api.i18n.locale")

        register_platform_file_types_route(app)
        logger.info("app.filetypes.api.platform.file.types")

    if services_spa_index is not None and services_spa_index.is_file():
        _services_spa_html = services_spa_index.read_text(encoding="utf-8")

        @app.get(f"/{public_segment}/services", response_class=HTMLResponse)
        @app.get(f"/{public_segment}/services/", response_class=HTMLResponse)
        async def platform_services_spa() -> HTMLResponse:
            return HTMLResponse(content=_services_spa_html)

        _ = platform_services_spa

        logger.info(
            "app.platform.services.spa.services.services",
            public_segment=public_segment,
            public_segment_2=public_segment,
            services_spa_index=services_spa_index,
        )

    # Health-эндпоинты
    @app.get("/health")
    @app.get(f"/{service_name}/health")
    async def health() -> dict[str, str]:
        return build_health_payload(settings)

    _ = health

    @app.get("/")
    async def root() -> JsonObject:
        return {"service": service_name, "version": version, "status": "running"}

    _ = root

    if resolved_cors_allow_origin_regex is None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=True,
            allow_methods=cors_allow_methods,
            allow_headers=cors_allow_headers,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=True,
            allow_methods=cors_allow_methods,
            allow_headers=cors_allow_headers,
            allow_origin_regex=resolved_cors_allow_origin_regex,
        )

    # Публичные embed-ассеты `/static/core/...` открыты любому Origin, включая preflight:
    # внешний слой над общим CORSMiddleware, одинаково на каждом сервисе.
    app.add_middleware(StaticCoreModuleCorsMiddleware)

    # Ещё снаружи: путь, чей preflight не должен закрывать общий CORS (embed A2A).
    if outer_middlewares:
        for middleware_class, kwargs in outer_middlewares:
            app.add_middleware(middleware_class, **dict(kwargs))

    logger.info("service.created", service=service_name)

    return app
