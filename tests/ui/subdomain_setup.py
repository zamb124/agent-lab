"""Субдомены worker-компаний для UI с context_type=frontend (CRM, RAG, Office)."""

from __future__ import annotations

from core.models.identity_models import Company
from tests.ui.e2e_worker import (
    ui_e2e_company2_id,
    ui_e2e_company_id,
    ui_e2e_subdomain,
    ui_e2e_subdomain_company2,
)


async def ensure_ui_subdomain_mappings(frontend_di) -> None:
    """Прописывает subdomain на worker-компаниях."""

    async def one(company_id: str, slug: str) -> None:
        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"Компания {company_id} не найдена — сначала фикстуры auth_token_*")
        if company.subdomain != slug:
            company.subdomain = slug
            await Company.set(company)

    await one(ui_e2e_company_id(), ui_e2e_subdomain())
    await one(ui_e2e_company2_id(), ui_e2e_subdomain_company2())
