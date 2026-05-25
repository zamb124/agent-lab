"""
API для управления API ключами компании
"""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ApiKey, ApiKeyCreate, ApiKeyCreated, ApiKeyUpdate
from core.context import require_context
from core.db.models.platform import ApiKeyRecord
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.pagination import OffsetPage
from core.types import JsonObject

logger = get_logger(__name__)
router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])

VALID_SCOPES = {
    "agents:read",
    "agents:write",
    "crm:read",
    "crm:write",
    "rag:read",
    "rag:write",
    "billing:read",
}


def _generate_api_key() -> tuple[str, str]:
    """Возвращает (secret, sha256_hex)."""
    secret = f"hum_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()
    return secret, key_hash


def _record_to_model(record: ApiKeyRecord) -> ApiKey:
    return ApiKey(
        key_id=record.key_id,
        name=record.name,
        key_prefix=record.key_prefix,
        scopes=record.scopes,
        created_at=record.created_at,
        last_used=record.last_used,
        company_id=record.company_id,
        created_by=record.created_by,
    )


def _require_api_key_principal() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return context.user, company


def _require_api_key_admin() -> tuple[User, Company]:
    user, company = _require_api_key_principal()
    roles = company.members.get(user.user_id, [])
    if "owner" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user, company


@router.get("", response_model=OffsetPage[ApiKey])
async def list_api_keys(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ApiKey]:
    _, company = _require_api_key_principal()
    records = await container.api_key_repository.list_by_company(
        company.company_id,
        limit=limit,
        offset=offset,
    )
    items = [_record_to_model(r) for r in records]
    return OffsetPage[ApiKey](items=items, total=len(items), limit=limit, offset=offset)

@router.post("", response_model=ApiKeyCreated)
async def create_api_key(
    key_data: ApiKeyCreate,
    container: ContainerDep,
) -> ApiKeyCreated:
    user, company = _require_api_key_admin()

    for scope in key_data.scopes:
        if scope not in VALID_SCOPES:
            raise HTTPException(
                status_code=400,
                detail=f"Недопустимый scope: {scope}. Допустимые: {', '.join(sorted(VALID_SCOPES))}",
            )

    secret, key_hash = _generate_api_key()
    key_id = f"key_{secrets.token_urlsafe(16)}"

    record = ApiKeyRecord(
        key_id=key_id,
        company_id=company.company_id,
        name=key_data.name,
        key_hash=key_hash,
        key_prefix=secret[:12],
        scopes=key_data.scopes,
        created_by=user.user_id,
        revoked=False,
        created_at=datetime.now(timezone.utc),
    )
    await container.api_key_repository.create(record)

    logger.info("Создан API ключ %s для компании %s", key_id, company.company_id)

    return ApiKeyCreated(
        key_id=key_id,
        name=key_data.name,
        secret=secret,
        scopes=key_data.scopes,
    )

@router.patch("/{key_id}")
async def update_api_key(
    key_id: str,
    body: ApiKeyUpdate,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_api_key_admin()

    updated = await container.api_key_repository.update_name(key_id, company.company_id, body.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Ключ не найден")

    return {"success": True, "key_id": key_id, "name": body.name}

@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    container: ContainerDep,
) -> JsonObject:
    _, company = _require_api_key_admin()

    revoked = await container.api_key_repository.revoke(key_id, company.company_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Ключ не найден или уже отозван")

    return {"success": True, "message": "API ключ отозван"}
