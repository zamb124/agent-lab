"""Интеграция: ``build_job_context`` / ``pick_company_billing_user`` на живом frontend_container."""

from __future__ import annotations

import pytest

from core.context.job_context import build_job_context, pick_company_billing_user
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


@pytest.mark.asyncio
async def test_build_job_context_signs_jwt_for_member(frontend_container, unique_id) -> None:
    cid = f"co_jctx_{unique_id}"
    uid = f"u_jctx_{unique_id}"
    user = User(user_id=uid, name="Owner", companies={cid: ["owner"]})
    company = Company(
        company_id=cid,
        name="JobCtx",
        owner_user_id=uid,
        members={uid: ["owner"]},
        balance=5.0,
    )
    await frontend_container.user_repository.set(user)
    await frontend_container.company_repository.set(company)

    ctx = build_job_context(
        company=company,
        user=user,
        host="reembed_job",
        trace_id=f"trace:{unique_id}",
        session_id=f"sess:{unique_id}",
        channel="test_worker",
    )
    assert ctx.user.user_id == uid
    assert ctx.active_company is not None
    assert ctx.active_company.company_id == cid
    assert ctx.host == "reembed_job"
    assert ctx.channel == "test_worker"
    assert ctx.trace_id == f"trace:{unique_id}"
    assert ctx.session_id == f"sess:{unique_id}"
    token = get_token_service().validate_token(ctx.auth_token)
    assert token is not None
    assert token.user_id == uid
    assert token.company_id == cid


@pytest.mark.asyncio
async def test_build_job_context_raises_for_non_member(unique_id) -> None:
    cid = f"co_alien_{unique_id}"
    company = Company(
        company_id=cid,
        name="Alien",
        owner_user_id=f"u_alien_{unique_id}",
        members={f"u_alien_{unique_id}": ["owner"]},
    )
    outsider = User(user_id=f"u_alien_{unique_id}", name="Outsider", companies={})
    with pytest.raises(ValueError, match="не состоит в компании"):
        build_job_context(
            company=company,
            user=outsider,
            host="h",
            trace_id="t",
            session_id="s",
            channel="c",
        )


@pytest.mark.asyncio
async def test_pick_company_billing_user_returns_owner_user_id(
    frontend_container, unique_id
) -> None:
    cid = f"co_pick_owner_{unique_id}"
    uid = f"u_pick_owner_{unique_id}"
    await frontend_container.user_repository.set(
        User(user_id=uid, name="Owner", companies={cid: ["owner"]})
    )
    company = Company(
        company_id=cid,
        name="P",
        owner_user_id=uid,
        members={uid: ["owner"]},
    )
    await frontend_container.company_repository.set(company)

    picked = await pick_company_billing_user(
        company=company,
        user_repository=frontend_container.user_repository,
    )
    assert picked.user_id == uid


@pytest.mark.asyncio
async def test_pick_company_billing_user_falls_back_to_min_owner_member(
    frontend_container, unique_id
) -> None:
    cid = f"co_pick_min_{unique_id}"
    uid_a = f"u_a_{unique_id}"
    uid_z = f"u_z_{unique_id}"
    await frontend_container.user_repository.set(
        User(user_id=uid_z, name="Z", companies={cid: ["owner"]})
    )
    await frontend_container.user_repository.set(
        User(user_id=uid_a, name="A", companies={cid: ["owner"]})
    )
    company = Company(
        company_id=cid,
        name="P",
        owner_user_id=None,
        members={uid_z: ["owner"], uid_a: ["owner"]},
    )
    await frontend_container.company_repository.set(company)

    picked = await pick_company_billing_user(
        company=company,
        user_repository=frontend_container.user_repository,
    )
    assert picked.user_id == min(uid_a, uid_z)


@pytest.mark.asyncio
async def test_pick_company_billing_user_skips_users_without_membership(
    frontend_container, unique_id
) -> None:
    """``owner_user_id`` указывает на пользователя без актуального членства — fallback в members."""
    cid = f"co_pick_outdated_{unique_id}"
    uid_outdated = f"u_outdated_{unique_id}"
    uid_actual = f"u_actual_{unique_id}"
    await frontend_container.user_repository.set(
        User(user_id=uid_outdated, name="Outdated", companies={})
    )
    await frontend_container.user_repository.set(
        User(user_id=uid_actual, name="Actual", companies={cid: ["owner"]})
    )
    company = Company(
        company_id=cid,
        name="P",
        owner_user_id=uid_outdated,
        members={uid_outdated: ["owner"], uid_actual: ["owner"]},
    )
    await frontend_container.company_repository.set(company)

    picked = await pick_company_billing_user(
        company=company,
        user_repository=frontend_container.user_repository,
    )
    assert picked.user_id == uid_actual


@pytest.mark.asyncio
async def test_pick_company_billing_user_ignores_whitespace_owner_id(
    frontend_container, unique_id
) -> None:
    cid = f"co_pick_ws_{unique_id}"
    uid = f"u_ws_{unique_id}"
    await frontend_container.user_repository.set(
        User(user_id=uid, name="M", companies={cid: ["owner"]})
    )
    company = Company(
        company_id=cid,
        name="WS",
        owner_user_id="   ",
        members={uid: ["owner"]},
    )
    await frontend_container.company_repository.set(company)

    picked = await pick_company_billing_user(
        company=company,
        user_repository=frontend_container.user_repository,
    )
    assert picked.user_id == uid


@pytest.mark.asyncio
async def test_pick_company_billing_user_raises_when_no_owner(
    frontend_container, unique_id
) -> None:
    cid = f"co_pick_none_{unique_id}"
    company = Company(
        company_id=cid,
        name="NoOwner",
        owner_user_id=None,
        members={f"u_admin_{unique_id}": ["admin"]},
    )
    await frontend_container.company_repository.set(company)
    with pytest.raises(ValueError, match="нет валидного owner"):
        await pick_company_billing_user(
            company=company,
            user_repository=frontend_container.user_repository,
        )
