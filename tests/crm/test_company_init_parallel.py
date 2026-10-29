"""Параллельный initialize_company не валит UniqueViolation на company_mapping."""

from __future__ import annotations

import asyncio

import pytest

from apps.crm.models.company_mapping import CompanyMapping
from apps.crm.models.crm_entity import CRMEntity
from core.authz.service import AuthzService
from core.context import clear_context, set_context
from core.identity.company_membership import set_company_member_roles
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.timeout(60, func_only=True),
]

_PARALLEL_WORKERS = 8


async def test_initialize_company_parallel_workers_share_one_mapping(
    authz_service: AuthzService,
    crm_di,
    unique_id: str,
) -> None:
    """N воркеров как CRM granian: один mapping, без IntegrityError в lifespan."""
    company_id = f"co-init-{unique_id}"
    owner_id = f"owner-{unique_id}"
    company = Company(
        company_id=company_id,
        name="CRM Init Parallel",
        subdomain=f"init-{unique_id}",
        owner_user_id=owner_id,
        members={},
    )
    owner = User(user_id=owner_id, name="Owner", companies={})
    _ = await Company.set(company)
    _ = await User.set(owner)
    _ = await set_company_member_roles(
        authz=authz_service,
        company=company,
        user=owner,
        roles=["owner"],
    )
    _ = set_context(
        Context(
            user=owner,
            active_company=company,
            channel="api",
        )
    )
    try:
        results: list[dict[str, int | bool]] = list(
            await asyncio.gather(
                *[
                    crm_di.company_init_service.initialize_company(company_id)
                    for _ in range(_PARALLEL_WORKERS)
                ]
            )
        )
    finally:
        clear_context()

    assert len(results) == _PARALLEL_WORKERS
    mapping: CompanyMapping | None = await CompanyMapping.get(company_id)
    assert mapping is not None
    organizations = (
        await CRMEntity.cursor_page_by_created_at_and_entity_id_desc(
            entity_type="organization",
            namespace="default",
            company_id=company_id,
            limit=10,
        )
    ).items
    assert len(organizations) == 1
    assert mapping.entity_id == organizations[0].entity_id
