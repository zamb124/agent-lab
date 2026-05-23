"""
Декораторы для авторизации.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar, cast

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _string_list(value: object) -> list[str]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        return []
    return [item for item in value if isinstance(item, str)]


def _user_email(value: object) -> str:
    if isinstance(value, str):
        return value
    return "unknown"


def require_admin(
    handler: Callable[Concatenate[Request, P], Awaitable[R]],
) -> Callable[Concatenate[Request, P], Awaitable[R | JSONResponse]]:
    """
    Декоратор для защищённых admin endpoints.
    Проверяет, что пользователь авторизован (если проверка permissions отключена).
    Если permissions включены - проверяет группу "admin".
    """

    @wraps(handler)
    async def wrapper(request: Request, *args: P.args, **kwargs: P.kwargs) -> R | JSONResponse:

        settings = get_settings()

        # Проверяем, что пользователь авторизован
        user: object | None = getattr(request.state, "user", None)
        if user is None:
            logger.warning("require_admin: no user in request.state")
            return JSONResponse(
                {"error": "Unauthorized: invalid or missing Authorization header"},
                status_code=401,
            )

        # Если проверка permissions отключена - просто проверяем авторизацию
        if not settings.auth.permissions_enabled:
            return await handler(request, *args, **kwargs)

        # Если permissions включены - проверяем группу admin
        if isinstance(user, Mapping):
            user_mapping = cast(Mapping[object, object], user)
            user_groups = _string_list(user_mapping.get("grps") or user_mapping.get("groups") or [])
            user_email = _user_email(user_mapping.get("email"))
        else:
            user_groups = _string_list(
                getattr(user, "grps", None) or getattr(user, "groups", None) or []
            )
            user_email = _user_email(getattr(user, "email", None))

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


def require_auth(
    handler: Callable[Concatenate[Request, P], Awaitable[R]],
) -> Callable[Concatenate[Request, P], Awaitable[R | JSONResponse]]:
    """
    Декоратор для проверки наличия авторизованного пользователя.
    Проверяет наличие request.state.user (устанавливается AuthMiddleware).
    """

    @wraps(handler)
    async def wrapper(request: Request, *args: P.args, **kwargs: P.kwargs) -> R | JSONResponse:
        user: object | None = getattr(request.state, "user", None)
        if user is None:
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
            )

        return await handler(request, *args, **kwargs)

    return wrapper


def validate_body(
    schema: type[BaseModel],
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R | JSONResponse]]]:
    """
    Декоратор для валидации тела запроса через Pydantic-схему.
    Передаёт провалидированный объект как аргумент `body`.
    """

    def decorator(handler: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R | JSONResponse]]:
        @wraps(handler)
        async def wrapper(request: Request, *args: object, **kwargs: object) -> R | JSONResponse:
            try:
                body_data = cast(object, await request.json())
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


def validate_params(
    schema: type[BaseModel],
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R | JSONResponse]]]:
    """
    Декоратор для валидации query-параметров через Pydantic-схему.
    Передаёт провалидированный объект как аргумент `params`.
    """

    def decorator(handler: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R | JSONResponse]]:
        @wraps(handler)
        async def wrapper(request: Request, *args: object, **kwargs: object) -> R | JSONResponse:
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
