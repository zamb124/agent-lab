"""Субдомены system.localhost / company2.localhost для UI с context_type=frontend (CRM, RAG)."""

from __future__ import annotations

from apps.frontend.container import FrontendContainer


async def ensure_ui_subdomain_mappings(container: FrontendContainer) -> None:
    """Прописывает subdomain на компаниях и маппинг в SubdomainRepository (shared storage)."""

    async def one(company_id: str, slug: str) -> None:
        company = await container.company_repository.get(company_id)
        if company is None:
            raise ValueError(f"Компания {company_id} не найдена — сначала фикстуры auth_token_*")
        if company.subdomain != slug:
            company.subdomain = slug
            await container.company_repository.set(company)
        await container.subdomain_repository.set_mapping(slug, company_id)

    await one("system", "system")
    await one("company2", "company2")
