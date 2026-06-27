"""Device JWT validation для HumanitecAgent HTTP endpoints."""

from fastapi import HTTPException, Request

from apps.agent.service import is_device_token_denied_shared
from apps.flows.src.dependencies import ContainerDep
from core.utils.tokens import TokenService


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
        raise HTTPException(status_code=401, detail="device_id отсутствует в токене")
    device_jti = metadata.get("jti")
    resolved_jti = device_jti if isinstance(device_jti, str) and device_jti else None
    if await is_device_token_denied_shared(
        container.shared_storage,
        device_id,
        device_jti=resolved_jti,
    ):
        raise HTTPException(status_code=401, detail="Device token revoked")


async def require_active_device_bearer(request: Request, container: ContainerDep) -> None:
    """
    Проверяет Bearer device JWT и отклоняет отозванные токены.
    Контекст user/company должен быть уже установлен AuthMiddleware.
    """
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")

    token = authorization.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization Bearer обязателен")

    token_data = TokenService().validate_token(token)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Недействительный device token")

    metadata = token_data.metadata
    token_purpose = metadata.get("token_purpose")
    if token_purpose != "device":
        raise HTTPException(status_code=403, detail="Требуется device token")

    device_id = metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise HTTPException(status_code=401, detail="device_id отсутствует в токене")

    device_jti = metadata.get("jti")
    resolved_jti = device_jti if isinstance(device_jti, str) and device_jti else None
    if await is_device_token_denied_shared(
        container.shared_storage,
        device_id,
        device_jti=resolved_jti,
    ):
        raise HTTPException(status_code=401, detail="Device token revoked")
