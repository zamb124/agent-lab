"""Device JWT validation для HumanitecAgent HTTP endpoints."""

from fastapi import Request

from apps.agent.service import is_device_token_denied_shared
from apps.flows.src.dependencies import ContainerDep
from core.utils.tokens import TokenService
from core.websocket import WsCommandError


def extract_device_id_from_bearer(request: Request) -> str | None:
    """Возвращает device_id из Bearer device JWT или None (session/без токена)."""
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        return None
    token_data = TokenService().validate_token(token)
    if token_data is None:
        return None
    metadata = token_data.metadata
    if metadata.get("token_purpose") != "device":
        return None
    device_id = metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        return None
    return device_id.strip()


async def reject_revoked_device_bearer_if_present(request: Request, container: ContainerDep) -> None:
    """Отклоняет отозванный device JWT, если Authorization передан (optional auth)."""
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return
    if not authorization.lower().startswith("bearer "):
        return
    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        return
    token_data = TokenService().validate_token(token)
    if token_data is None:
        return
    metadata = token_data.metadata
    token_purpose = metadata.get("token_purpose")
    if token_purpose != "device":
        return
    device_id = metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise WsCommandError(
            "unauthorized",
            "device_id is missing from token",
            error_code="device_id_missing",
        )
    device_jti = metadata.get("jti")
    resolved_jti = device_jti if isinstance(device_jti, str) and device_jti else None
    if await is_device_token_denied_shared(
        container.shared_storage,
        device_id,
        device_jti=resolved_jti,
    ):
        raise WsCommandError(
            "unauthorized",
            "device token revoked",
            error_code="device_token_revoked",
        )


async def require_active_device_bearer(request: Request, container: ContainerDep) -> None:
    """
    Проверяет Bearer device JWT и отклоняет отозванные токены.
    Контекст user/company должен быть уже установлен AuthMiddleware.
    """
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )
    if not authorization.lower().startswith("bearer "):
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )

    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        raise WsCommandError(
            "unauthorized",
            "Authorization Bearer is required",
            error_code="authorization_bearer_required",
        )

    token_data = TokenService().validate_token(token)
    if token_data is None:
        raise WsCommandError(
            "unauthorized",
            "device token is invalid",
            error_code="device_token_invalid",
        )

    metadata = token_data.metadata
    token_purpose = metadata.get("token_purpose")
    if token_purpose != "device":
        raise WsCommandError(
            "forbidden",
            "device token required",
            error_code="device_token_required",
        )

    device_id = metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise WsCommandError(
            "unauthorized",
            "device_id is missing from token",
            error_code="device_id_missing",
        )

    device_jti = metadata.get("jti")
    resolved_jti = device_jti if isinstance(device_jti, str) and device_jti else None
    if await is_device_token_denied_shared(
        container.shared_storage,
        device_id,
        device_jti=resolved_jti,
    ):
        raise WsCommandError(
            "unauthorized",
            "device token revoked",
            error_code="device_token_revoked",
        )
