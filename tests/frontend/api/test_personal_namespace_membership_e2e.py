"""E2E: personal namespace создаётся при membership (invite accept / company create).

Реальная shared Postgres + ASGI frontend. Без monkeypatch / mock.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from httpx import AsyncClient

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import NamespaceKind, User
from core.namespace import personal_namespace_name
from core.utils.tokens import get_token_service


def _short_code_from_invite_url(invite_url: str) -> str:
    parsed = urlparse(invite_url)
    path = parsed.path or ""
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2 or segments[0] != "l":
        raise ValueError(f"Ожидался путь /l/{{code}}: {path}")
    return segments[1]


async def _jwt_from_invite_url(frontend_container, invite_url: str) -> str:
    code = _short_code_from_invite_url(invite_url)
    raw = await frontend_container.short_link_service.get_invite_jwt_by_code(code)
    if raw is None:
        raise ValueError("JWT не найден по короткому коду")
    return raw


async def _create_invitee_no_company(
    frontend_container, *, name: str, unique_id: str
) -> tuple[str, dict[str, str]]:
    uid = f"pns_inv_{unique_id}"
    user = User(
        user_id=uid,
        name=name,
        emails=[f"{uid}@test.local"],
        companies={},
        active_company_id="",
    )
    await frontend_container.user_repository.set(user)
    token = get_token_service().create_token(uid, company_id="", roles=[])
    return uid, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_accept_invite_creates_personal_namespace(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    frontend_container,
    unique_id: str,
) -> None:
    token_service = get_token_service()
    owner_data = token_service.validate_token(auth_token)
    assert owner_data is not None
    target_company_id = owner_data.company_id

    gen = await frontend_client.post(
        "/frontend/api/invites/generate",
        headers=auth_headers,
        json={"role": "developer"},
    )
    assert gen.status_code == 200, gen.text
    invite_url = gen.json()["invite_url"]
    short_code = _short_code_from_invite_url(invite_url)
    _ = await _jwt_from_invite_url(frontend_container, invite_url)

    invitee_name = f"Invitee Personal {unique_id}"
    invitee_id, invitee_headers = await _create_invitee_no_company(
        frontend_container, name=invitee_name, unique_id=unique_id
    )

    accept = await frontend_client.post(
        "/frontend/api/invites/accept",
        headers=invitee_headers,
        json={"short_code": short_code},
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["company_id"] == target_company_id

    company = await frontend_container.company_repository.get(target_company_id)
    assert company is not None
    invitee = await frontend_container.user_repository.get(invitee_id)
    assert invitee is not None
    assert target_company_id in invitee.companies

    set_context(
        Context(
            user=invitee,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        expected_name = personal_namespace_name(invitee_id)
        personal = await frontend_container.namespace_service.get(expected_name)
        assert personal is not None
        assert personal.kind == NamespaceKind.PERSONAL
        assert personal.owner_user_id == invitee_id
        assert personal.description == invitee_name
        again = await frontend_container.namespace_service.ensure_personal_namespace(
            invitee_id, display_name=invitee_name
        )
        assert again.name == expected_name
        product = await frontend_container.namespace_service.list(limit=500)
        personal_for_user = [
            ns
            for ns in product
            if ns.kind == NamespaceKind.PERSONAL and ns.owner_user_id == invitee_id
        ]
        assert len(personal_for_user) == 1
    finally:
        clear_context()


@pytest.mark.asyncio
@pytest.mark.timeout(120, func_only=True)
async def test_create_company_creates_personal_namespace_for_owner(
    frontend_client: AsyncClient,
    auth_token: str,
    frontend_container,
    unique_id: str,
) -> None:
    token_service = get_token_service()
    owner_data = token_service.validate_token(auth_token)
    assert owner_data is not None
    owner_id = owner_data.user_id
    owner = await frontend_container.user_repository.get(owner_id)
    assert owner is not None

    company_name = f"PNS Co {unique_id}"
    company_slug = f"pns-co-{unique_id}"[:48]
    response = await frontend_client.post(
        "/frontend/api/companies",
        json={"name": company_name, "slug": company_slug},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200, response.text
    company_id = response.json()["company_id"]

    company = await frontend_container.company_repository.get(company_id)
    assert company is not None
    owner_after = await frontend_container.user_repository.get(owner_id)
    assert owner_after is not None
    assert company_id in owner_after.companies

    set_context(
        Context(
            user=owner_after,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        expected_name = personal_namespace_name(owner_id)
        personal = await frontend_container.namespace_service.get(expected_name)
        assert personal is not None
        assert personal.kind == NamespaceKind.PERSONAL
        assert personal.owner_user_id == owner_id
        assert personal.description == owner_after.name
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_console_me_personal_endpoint_ensures_namespace(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    unique_id: str,
) -> None:
    _ = unique_id
    token_service = get_token_service()
    owner_data = token_service.validate_token(auth_token)
    assert owner_data is not None

    response = await frontend_client.get(
        "/frontend/api/namespaces/me/personal",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == NamespaceKind.PERSONAL.value
    assert body["name"] == personal_namespace_name(owner_data.user_id)
    assert body["owner_user_id"] == owner_data.user_id
