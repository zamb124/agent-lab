"""
Универсальные API эндпоинты компаний (доступны на всех сервисах).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from core.models.identity_models import User
from core.pagination import ListResponse

router = APIRouter(tags=["companies"])


async def build_my_companies_response(
    *,
    user: User,
    company_repository: Any,
) -> ListResponse[dict]:
    items: list[dict] = []
    for company_id, roles in user.companies.items():
        company = await company_repository.get(company_id)
        if company is None:
            raise HTTPException(status_code=404, detail=f"Company not found: {company_id}")
        if not company.subdomain:
            raise HTTPException(status_code=500, detail=f"Company subdomain is empty: {company_id}")
        items.append(
            {
                "company_id": company.company_id,
                "name": company.name,
                "subdomain": company.subdomain,
                "role": roles,
                "is_active": company.company_id == user.active_company_id,
            }
        )
    return ListResponse[dict](items=items)


@router.get("/me", response_model=ListResponse[dict])
async def get_my_companies(request: Request) -> ListResponse[dict]:
    """Возвращает компании текущего пользователя с subdomain и ролями."""
    token_data = getattr(request.state, "token_data", None)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    container = request.app.state.container
    user = await container.user_repository.get(token_data.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await build_my_companies_response(
        user=user,
        company_repository=container.company_repository,
    )
