"""
Декораторы для авторизации.
"""

from functools import wraps

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


def require_admin(handler):
    """
    Декоратор для защищённых admin endpoints.
    Проверяет, что пользователь авторизован (если проверка permissions отключена).
    Если permissions включены - проверяет группу "admin".
    """

    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):

        settings = get_settings()

        # Проверяем, что пользователь авторизован
        if not hasattr(request.state, "user") or request.state.user is None:
            logger.warning("require_admin: no user in request.state")
            return JSONResponse(
                {"error": "Unauthorized: invalid or missing Authorization header"},
                status_code=401,
            )

        # Если проверка permissions отключена - просто проверяем авторизацию
        if not settings.auth.permissions_enabled:
            return await handler(request, *args, **kwargs)

        # Если permissions включены - проверяем группу admin
        user = request.state.user
        if isinstance(user, dict):
            user_groups = user.get("grps", []) or user.get("groups", []) or []
            user_email = user.get("email", "unknown")
        else:
            user_groups = getattr(user, "grps", []) or getattr(user, "groups", []) or []
            user_email = getattr(user, "email", "unknown")

        logger.info(f"require_admin: user={user_email}, groups={user_groups}")

        # Проверяем, что пользователь в группе admin
        if "admin" not in user_groups:
            logger.warning(f"require_admin: user {user_email} not in admin group, groups={user_groups}")
            return JSONResponse(
                {"error": f"Forbidden: admin access required. User groups: {user_groups}"},
                status_code=403,
            )

        return await handler(request, *args, **kwargs)

    return wrapper


def require_auth(handler):
    """
    Декоратор для проверки наличия авторизованного пользователя.
    Проверяет наличие request.state.user (устанавливается AuthMiddleware).
    """

    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        if not hasattr(request.state, "user") or request.state.user is None:
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
            )

        return await handler(request, *args, **kwargs)

    return wrapper


def validate_body(schema: type[BaseModel]):
    """
    Декоратор для валидации тела запроса через Pydantic-схему.
    Передаёт провалидированный объект как аргумент `body`.
    """

    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                body_data = await request.json()
                validated = schema.model_validate(body_data)
            except ValidationError as e:
                return JSONResponse(
                    {
                        "error": "Validation error",
                        "details": e.errors(),
                    },
                    status_code=422,
                )
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            kwargs["body"] = validated
            return await handler(request, *args, **kwargs)

        return wrapper

    return decorator


def validate_params(schema: type[BaseModel]):
    """
    Декоратор для валидации query-параметров через Pydantic-схему.
    Передаёт провалидированный объект как аргумент `params`.
    """

    def decorator(handler):
        @wraps(handler)
        async def wrapper(request: Request, *args, **kwargs):
            query_dict = dict(request.query_params)
            try:
                validated = schema.model_validate(query_dict, strict=False)
            except ValidationError as e:
                logger.error(
                    f"Validation error for {schema.__name__}: {e.errors()}, query_dict: {query_dict}"
                )
                return JSONResponse(
                    {
                        "error": "Invalid query parameters",
                        "details": e.errors(),
                    },
                    status_code=422,
                )
            kwargs["params"] = validated
            return await handler(request, *args, **kwargs)

        return wrapper

    return decorator
