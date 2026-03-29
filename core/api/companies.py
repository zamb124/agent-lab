"""
Универсальные API эндпоинты компаний (доступны на всех сервисах).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["companies"])


@router.get("/me")
async def get_my_companies(request: Request) -> list[dict]:
    """Возвращает компании текущего пользователя с subdomain и ролями."""
    token_data = getattr(request.state, "token_data", None)
    if not token_data:
        raise HTTPException(status_code=401, detail="Not authenticated")

    container = request.app.state.container
    user = await container.user_repository.get(token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    companies: list[dict] = []
    for company_id, roles in user.companies.items():
        company = await container.company_repository.get(company_id)
        if not company:
            raise HTTPException(status_code=404, detail=f"Company not found: {company_id}")
        if not company.subdomain:
            raise HTTPException(status_code=500, detail=f"Company subdomain is empty: {company_id}")

        companies.append(
            {
                "company_id": company.company_id,
                "name": company.name,
                "subdomain": company.subdomain,
                "role": roles,
                "is_active": company.company_id == user.active_company_id,
            }
        )

    return companies
