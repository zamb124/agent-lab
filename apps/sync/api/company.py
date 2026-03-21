"""Участники компании — для списка «Личные» в Sync UI."""

from fastapi import APIRouter, HTTPException

from apps.sync.container import get_sync_container
from apps.sync.models.company_members import CompanyMemberRead
from core.context import get_context

router = APIRouter()


@router.get("/members", response_model=list[CompanyMemberRead])
async def list_company_members() -> list[CompanyMemberRead]:
    """Участники активной компании (без текущего пользователя)."""
    context = get_context()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id

    container = get_sync_container()
    company = await container.company_repository.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена.")

    out: list[CompanyMemberRead] = []
    for uid, roles_raw in company.members.items():
        if uid == viewer_id:
            continue
        user = await container.user_repository.get(uid)
        if user is None:
            raise HTTPException(
                status_code=500,
                detail=f"Участник {uid} указан в компании, но пользователь не найден.",
            )
        roles = list(roles_raw) if isinstance(roles_raw, list) else [roles_raw]
        out.append(
            CompanyMemberRead(
                user_id=uid,
                name=user.name,
                roles=roles,
                avatar_url=user.avatar_url,
            )
        )
    out.sort(key=lambda m: m.name.casefold())
    return out
