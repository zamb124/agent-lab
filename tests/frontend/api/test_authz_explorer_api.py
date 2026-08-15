"""Access Explorer: gate, явные tuples, без roster через can_view."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.authz.group_sync import group_company_link, group_member_tuple
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles
from tests.fixtures.wiki import CreatePage


def _auth_company_user(auth_headers: dict[str, str]) -> tuple[str, str]:
    token_service = get_token_service()
    token_data = token_service.validate_token(
        auth_headers["Authorization"].replace("Bearer ", "")
    )
    company_id = token_data.company_id
    user_id = token_data.user_id
    if company_id is None or company_id == "":
        raise AssertionError("auth token must carry company_id")
    if user_id is None or user_id == "":
        raise AssertionError("auth token must carry user_id")
    return company_id, user_id


@pytest.mark.asyncio
class TestAuthzExplorerAPI:
    async def test_by_user_unauthorized(self, frontend_client: AsyncClient) -> None:
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-user",
            params={"user_id": "anyone"},
        )
        assert response.status_code == 401

    async def test_by_user_forbidden_without_fga_admin(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id = f"expl_co_{unique_id}"
        user_id = f"expl_admin_{unique_id}"
        company = Company(
            company_id=company_id,
            name="Explorer Roles",
            owner_user_id="other_owner",
        )
        user = User(
            user_id=user_id,
            name="Roster Admin",
            groups=["user"],
            companies={company_id: ["admin"]},
            active_company_id=company_id,
        )
        await frontend_container.company_repository.set(company)
        await frontend_container.user_repository.set(user)
        await set_test_company_member_roles(
            frontend_container.company_repository,
            frontend_container.authz_service,
            company_id=company_id,
            user_id="other_owner",
            roles=["owner"],
        )
        token = get_token_service().create_token(user_id, company_id=company_id)
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-user",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id": user_id},
        )
        assert response.status_code == 403

    async def test_by_user_lists_explicit_grant_not_title_as_id(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, _actor_id = _auth_company_user(auth_headers)
        target_user_id = f"expl_target_{unique_id}"
        page_id = f"expl_page_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(page_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.user(target_user_id),
                    relation=AuthzRelation.VIEWER,
                    obj=AuthzObject.wiki_page(page_id),
                ),
            ]
        )
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-user",
            headers=auth_headers,
            params={"user_id": target_user_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user_id"] == target_user_id
        assert body["company_visible"] is True
        matching = [
            item
            for item in body["items"]
            if item["object_key"] == page_id and item["object_type"] == "wiki_page"
        ]
        assert len(matching) == 1
        row = matching[0]
        assert row["relation"] == "viewer"
        assert row["grant_source"] == "direct"
        assert row["title"] is None
        assert row["title_status"] == "missing"
        assert row["title"] != page_id

    async def test_by_object_does_not_expand_company_visible_roster(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, actor_id = _auth_company_user(auth_headers)
        page_id = f"expl_vis_{unique_id}"
        extra_user = f"expl_extra_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(page_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.company_member(company_id),
                    relation=AuthzRelation.COMPANY_VIEWER,
                    obj=AuthzObject.wiki_page(page_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.user(extra_user),
                    relation=AuthzRelation.EDITOR,
                    obj=AuthzObject.wiki_page(page_id),
                ),
            ]
        )
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers,
            params={"object_type": "wiki_page", "object_key": page_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["company_visible"] is True
        subject_ids = {item["subject_id"] for item in body["items"]}
        assert extra_user in subject_ids
        assert actor_id not in subject_ids
        assert company_id not in subject_ids

    async def test_why_returns_product_reasons(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, _actor_id = _auth_company_user(auth_headers)
        target_user_id = f"expl_why_{unique_id}"
        page_id = f"expl_why_page_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(page_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.user(target_user_id),
                    relation=AuthzRelation.VIEWER,
                    obj=AuthzObject.wiki_page(page_id),
                ),
            ]
        )
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/why",
            headers=auth_headers,
            params={
                "user_id": target_user_id,
                "object_type": AuthzObjectType.WIKI_PAGE.value,
                "object_key": page_id,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["allowed"] is True
        assert "direct_grant" in body["reasons"]
        assert "#" not in "".join(body["reasons"])
        assert "union" not in "".join(body["reasons"])

    async def test_why_parent_inherit(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, _actor_id = _auth_company_user(auth_headers)
        target_user_id = f"expl_parent_user_{unique_id}"
        parent_id = f"expl_parent_{unique_id}"
        child_id = f"expl_child_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(parent_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(child_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.user(target_user_id),
                    relation=AuthzRelation.OWNER,
                    obj=AuthzObject.wiki_page(parent_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.wiki_page(parent_id)),
                    relation=AuthzRelation.PARENT,
                    obj=AuthzObject.wiki_page(child_id),
                ),
            ]
        )
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/why",
            headers=auth_headers,
            params={
                "user_id": target_user_id,
                "object_type": AuthzObjectType.WIKI_PAGE.value,
                "object_key": child_id,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["allowed"] is True
        assert "parent_inherit" in body["reasons"]
        assert "direct_grant" not in body["reasons"]

    async def test_why_company_visible_only_for_member(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, actor_id = _auth_company_user(auth_headers)
        outsider_id = f"expl_outsider_{unique_id}"
        page_id = f"expl_visible_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=AuthzObject.wiki_page(page_id),
                ),
                AuthzTuple(
                    subject=AuthzSubject.company_member(company_id),
                    relation=AuthzRelation.COMPANY_VIEWER,
                    obj=AuthzObject.wiki_page(page_id),
                ),
            ]
        )
        member_response = await frontend_client.get(
            "/frontend/api/authz/explorer/why",
            headers=auth_headers,
            params={
                "user_id": actor_id,
                "object_type": AuthzObjectType.WIKI_PAGE.value,
                "object_key": page_id,
            },
        )
        assert member_response.status_code == 200, member_response.text
        member_body = member_response.json()
        assert member_body["allowed"] is True
        assert "company_visible" in member_body["reasons"]

        outsider_response = await frontend_client.get(
            "/frontend/api/authz/explorer/why",
            headers=auth_headers,
            params={
                "user_id": outsider_id,
                "object_type": AuthzObjectType.WIKI_PAGE.value,
                "object_key": page_id,
            },
        )
        assert outsider_response.status_code == 200, outsider_response.text
        outsider_body = outsider_response.json()
        assert outsider_body["allowed"] is False
        assert "company_visible" not in outsider_body["reasons"]

    async def test_hydrate_wiki_title_and_manage_href(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        frontend_container,
        create_page: CreatePage,
        unique_id: str,
    ) -> None:
        _company_id, actor_id = _auth_company_user(auth_headers_system)
        title = f"ExplHydrate {unique_id}"
        page = await create_page(title, markdown="Explorer hydrate page.")
        page_id = page["wiki_page_id"]
        assert isinstance(page_id, str)
        target_user_id = f"expl_hyd_{unique_id}"
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.user(target_user_id),
                    relation=AuthzRelation.VIEWER,
                    obj=AuthzObject.wiki_page(page_id),
                )
            ]
        )
        by_user = await frontend_client.get(
            "/frontend/api/authz/explorer/by-user",
            headers=auth_headers_system,
            params={"user_id": target_user_id},
        )
        assert by_user.status_code == 200, by_user.text
        user_rows = [
            item
            for item in by_user.json()["items"]
            if item["object_key"] == page_id and item["object_type"] == "wiki_page"
        ]
        assert len(user_rows) == 1
        user_row = user_rows[0]
        assert user_row["title"] == title
        assert user_row["title_status"] == "loaded"
        assert user_row["href"] == f"/wiki/p/{page_id}"
        assert user_row["manage_href"] == f"/wiki/p/{page_id}?access=1"
        assert user_row["href"] != user_row["manage_href"]

        by_object = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers_system,
            params={"object_type": "wiki_page", "object_key": page_id},
        )
        assert by_object.status_code == 200, by_object.text
        object_body = by_object.json()
        assert object_body["title"] == title
        assert object_body["title_status"] == "loaded"
        assert object_body["href"] == f"/wiki/p/{page_id}"
        assert object_body["manage_href"] == f"/wiki/p/{page_id}?access=1"
        _ = actor_id

    async def test_search_finds_page_and_hides_other_company(
        self,
        frontend_client: AsyncClient,
        auth_headers_system: dict[str, str],
        auth_headers_company2: dict[str, str],
        create_page: CreatePage,
        unique_id: str,
    ) -> None:
        title = f"ExplSearchUnique {unique_id}"
        page = await create_page(title, markdown="Explorer search page.")
        page_id = page["wiki_page_id"]
        found = await frontend_client.get(
            "/frontend/api/authz/explorer/objects",
            headers=auth_headers_system,
            params={"q": title, "object_type": "wiki_page"},
        )
        assert found.status_code == 200, found.text
        keys = {item["object_key"] for item in found.json()["items"]}
        assert page_id in keys
        titles = {item["title"] for item in found.json()["items"]}
        assert title in titles

        other = await frontend_client.get(
            "/frontend/api/authz/explorer/objects",
            headers=auth_headers_company2,
            params={"q": title, "object_type": "wiki_page"},
        )
        assert other.status_code == 200, other.text
        other_keys = {item["object_key"] for item in other.json()["items"]}
        assert page_id not in other_keys

    async def test_revoke_removes_tuple_structural_rejected(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, _actor_id = _auth_company_user(auth_headers)
        target_user_id = f"expl_rev_{unique_id}"
        page_id = f"expl_rev_page_{unique_id}"
        obj = AuthzObject.wiki_page(page_id)
        await frontend_container.authz_service.write(
            [
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=obj,
                ),
                AuthzTuple(
                    subject=AuthzSubject.user(target_user_id),
                    relation=AuthzRelation.VIEWER,
                    obj=obj,
                ),
            ]
        )
        revoke = await frontend_client.post(
            "/frontend/api/authz/explorer/revoke",
            headers=auth_headers,
            json={
                "object_type": "wiki_page",
                "object_key": page_id,
                "relation": "viewer",
                "subject_kind": AuthzSubjectKind.USER.value,
                "subject_id": target_user_id,
            },
        )
        assert revoke.status_code == 200, revoke.text
        assert revoke.json()["revoked"] is True
        leftover = await frontend_container.authz_service.list_tuples(
            obj,
            relation=AuthzRelation.VIEWER,
            subject=AuthzSubject.user(target_user_id),
        )
        assert leftover == []
        after = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers,
            params={"object_type": "wiki_page", "object_key": page_id},
        )
        assert after.status_code == 200, after.text
        subject_ids = {item["subject_id"] for item in after.json()["items"]}
        assert target_user_id not in subject_ids

        structural = await frontend_client.post(
            "/frontend/api/authz/explorer/revoke",
            headers=auth_headers,
            json={
                "object_type": "wiki_page",
                "object_key": page_id,
                "relation": "parent",
                "subject_kind": AuthzSubjectKind.USER.value,
                "subject_id": target_user_id,
            },
        )
        assert structural.status_code == 400
        company_rel = await frontend_client.post(
            "/frontend/api/authz/explorer/revoke",
            headers=auth_headers,
            json={
                "object_type": "wiki_page",
                "object_key": page_id,
                "relation": "company",
                "subject_kind": AuthzSubjectKind.USER.value,
                "subject_id": target_user_id,
            },
        )
        assert company_rel.status_code == 400

    async def test_group_grant_and_why_membership(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
        unique_id: str,
    ) -> None:
        company_id, _actor_id = _auth_company_user(auth_headers)
        target_user_id = f"expl_grp_user_{unique_id}"
        flow_id = f"expl_grp_flow_{unique_id}"
        group_name = f"explg{unique_id[:8]}"
        obj = AuthzObject.flow(flow_id, company_id=company_id)
        await frontend_container.authz_service.write(
            [
                group_company_link(group_name, company_id),
                group_member_tuple(
                    group_name, target_user_id, company_id=company_id
                ),
                AuthzTuple(
                    subject=AuthzSubject.object_ref(AuthzObject.company(company_id)),
                    relation=AuthzRelation.COMPANY,
                    obj=obj,
                ),
                AuthzTuple(
                    subject=AuthzSubject.group_member(
                        group_name, company_id=company_id
                    ),
                    relation=AuthzRelation.VIEWER,
                    obj=obj,
                ),
            ]
        )
        by_object = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers,
            params={"object_type": "flow", "object_key": obj.object_key},
        )
        assert by_object.status_code == 200, by_object.text
        group_rows = [
            item
            for item in by_object.json()["items"]
            if item["grant_source"] == "group"
        ]
        assert len(group_rows) == 1
        assert group_rows[0]["subject_kind"] == "group"

        why = await frontend_client.get(
            "/frontend/api/authz/explorer/why",
            headers=auth_headers,
            params={
                "user_id": target_user_id,
                "object_type": "flow",
                "object_key": obj.object_key,
            },
        )
        assert why.status_code == 200, why.text
        assert "group_membership" in why.json()["reasons"]

    async def test_other_company_object_not_found(
        self,
        frontend_client: AsyncClient,
        auth_headers_company2: dict[str, str],
        create_page: CreatePage,
        unique_id: str,
    ) -> None:
        page = await create_page(
            f"ExplTenant {unique_id}", markdown="Explorer tenancy page."
        )
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers_company2,
            params={"object_type": "wiki_page", "object_key": page["wiki_page_id"]},
        )
        assert response.status_code == 404

    async def test_unsupported_object_type_company(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = await frontend_client.get(
            "/frontend/api/authz/explorer/by-object",
            headers=auth_headers,
            params={"object_type": "company", "object_key": "system"},
        )
        assert response.status_code == 400
