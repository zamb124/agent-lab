"""
Субдомен Host = тенант: 403 при несовпадении membership; HTML для document/json для API;
anonymous-страницы без 403.
"""

import pytest
from core.models.identity_models import Company
from core.utils.tokens import get_token_service


@pytest.mark.asyncio
async def test_tenant_mismatch_403_json(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """Чужой субдомен + Accept: application/json — JSON с detail."""
    other_slug = f"other-{unique_id}"
    other_cid = f"co_other_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Other tenant",
        owner_user_id="u_foreign",
        members={"u_foreign": ["owner"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={
                "Host": f"{other_slug}.localhost:8002",
                "Accept": "application/json",
            },
        )
        assert response.status_code == 403
        body = response.json()
        assert "detail" in body
    finally:
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_tenant_mismatch_403_html(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """Тот же сценарий, браузерный Accept — HTML-страница ошибки."""
    other_slug = f"ohtml-{unique_id}"
    other_cid = f"co_oh_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Other tenant h",
        owner_user_id="u_foreign2",
        members={"u_foreign2": ["owner"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={
                "Host": f"{other_slug}.localhost:8002",
                "Accept": "text/html,application/json;q=0.8",
            },
        )
        assert response.status_code == 403
        text = response.text
        assert "<!DOCTYPE html>" in text
        assert "HTTP 403" in text
        assert "localStorage" in text and "platform_theme" in text
    finally:
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_x_company_id_conflicts_with_subdomain_403(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """X-Company-Id не равен компании субдомена — 403 при поддомене в Host."""
    token_service = get_token_service()
    td = token_service.validate_token(auth_token)
    if td is None or not td.company_id:
        raise AssertionError("ожидается company_id в токене")
    company = await frontend_container.company_repository.get(td.company_id)
    if company is None or not company.subdomain:
        raise AssertionError("компания с subdomain")
    other_slug = f"oxc-{unique_id}"
    other_cid = f"co_oxc_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="XCo",
        owner_user_id="u_oxc",
        members={"u_oxc": ["owner"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        frontend_client.cookies.set("auth_token", auth_token)
        r = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={
                "Host": f"{company.subdomain}.localhost:8002",
                "X-Company-Id": other_cid,
                "Accept": "application/json",
            },
        )
        assert r.status_code == 403
        assert r.json()["detail"]
    finally:
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_policy_anonymous_200_on_foreign_tenant_subdomain(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """Anonymous /policy: не 403, даже если сессия с другой компанией, Host — чужой тенант."""
    other_slug = f"pol-{unique_id}"
    other_cid = f"co_pol_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Policy tenant",
        owner_user_id="u_pol",
        members={"u_pol": ["owner"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/policy",
            headers={"Host": f"{other_slug}.localhost:8002"},
        )
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text
    finally:
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_flows_path_wrong_tenant_403(
    flows_client, auth_token, frontend_container, unique_id: str
) -> None:
    """GET /flows/... (a2a) с Host чужого субдомена — 403 в middleware, не 200."""
    other_slug = f"flw-{unique_id}"
    other_cid = f"co_flw_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Flows foreign",
        owner_user_id="u_flw",
        members={"u_flw": ["owner"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        flows_client.cookies.set("auth_token", auth_token)
        response = await flows_client.get(
            f"/flows/flow_mw_{unique_id}",
            headers={
                "Host": f"{other_slug}.localhost:8001",
                "Accept": "application/json",
            },
        )
        assert response.status_code == 403
        assert "detail" in response.json()
    finally:
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_session_active_company_mismatch_redirect_307(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """Сессия с активной компанией A, Host — субдомен B; пользователь в обеих — редирект на A."""
    token_service = get_token_service()
    td = token_service.validate_token(auth_token)
    if td is None:
        raise AssertionError("token")
    home = await frontend_container.company_repository.get(td.company_id)
    if home is None or not home.subdomain:
        raise AssertionError("home company subdomain")

    other_slug = f"dual-{unique_id}"
    other_cid = f"co_dual_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Dual tenant",
        owner_user_id=td.user_id,
        members={td.user_id: ["member"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        user = await frontend_container.user_repository.get(td.user_id)
        if user is None:
            raise AssertionError("user")
        user.companies[other_cid] = ["member"]
        await frontend_container.user_repository.set(user)

        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={
                "Host": f"{other_slug}.localhost:8002",
                "Accept": "application/json",
            },
            follow_redirects=False,
        )
        assert response.status_code == 307
        loc = response.headers.get("location")
        assert loc is not None
        assert home.subdomain in loc
        assert "localhost:8002" in loc
        assert "/frontend/api/auth/me" in loc
    finally:
        restored = await frontend_container.user_repository.get(td.user_id)
        if restored is not None and other_cid in restored.companies:
            del restored.companies[other_cid]
            await frontend_container.user_repository.set(restored)
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)


@pytest.mark.asyncio
async def test_session_active_company_mismatch_redirect_307(
    frontend_client, auth_token, frontend_container, unique_id: str
) -> None:
    """Сессия с активной компанией A, Host — субдомен B; пользователь в обеих — редирект на A."""
    token_service = get_token_service()
    td = token_service.validate_token(auth_token)
    if td is None:
        raise AssertionError("token")
    home = await frontend_container.company_repository.get(td.company_id)
    if home is None or not home.subdomain:
        raise AssertionError("home company subdomain")

    other_slug = f"dual-{unique_id}"
    other_cid = f"co_dual_{unique_id}"
    other = Company(
        company_id=other_cid,
        name="Dual tenant",
        owner_user_id=td.user_id,
        members={td.user_id: ["member"]},
        subdomain=other_slug,
    )
    await frontend_container.company_repository.set(other)
    await frontend_container.subdomain_repository.set_mapping(other_slug, other_cid)
    try:
        user = await frontend_container.user_repository.get(td.user_id)
        if user is None:
            raise AssertionError("user")
        user.companies[other_cid] = ["member"]
        await frontend_container.user_repository.set(user)

        frontend_client.cookies.set("auth_token", auth_token)
        response = await frontend_client.get(
            "/frontend/api/auth/me",
            headers={
                "Host": f"{other_slug}.localhost:8002",
                "Accept": "application/json",
            },
            follow_redirects=False,
        )
        assert response.status_code == 307
        loc = response.headers.get("location")
        assert loc is not None
        assert home.subdomain in loc
        assert "localhost:8002" in loc
        assert "/frontend/api/auth/me" in loc
    finally:
        restored = await frontend_container.user_repository.get(td.user_id)
        if restored is not None and other_cid in restored.companies:
            del restored.companies[other_cid]
            await frontend_container.user_repository.set(restored)
        await frontend_container.subdomain_repository.delete(other_slug)
        await frontend_container.company_repository.delete(other_cid)
