"""Общие helpers для HTTP-тестов sync.

Тесты создают namespace через `NamespaceService` (таблица `namespaces` в shared).
Менеджер фильтрует активную компанию, поэтому seed поднимает `Context` и потом
сбрасывает его.
"""


from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from core.context import clear_context, get_context, set_context
from core.di.platform import PlatformDi
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.namespace.authz.tuples import (
    platform_namespace_company_editor_tuple,
    platform_namespace_company_link,
    platform_namespace_company_viewer_tuple,
)
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


@contextmanager
def _temporary_company_context(
    company_id: str,
    *,
    subdomain: str | None = None,
) -> Iterator[None]:
    """Поднимает минимальный Context с `active_company` для записи в KV.

    Префикс storage: ``company:{subdomain or company_id}:`` (см. `BaseRepository`).
    Если у компании в БД задан subdomain (UI E2E ``ui-gwN``), его нужно передать —
    иначе seed уйдёт в ключ ``company:{company_id}:``, а runtime читает
    ``company:{subdomain}:``.
    """
    previous = get_context()
    company = Company(
        company_id=company_id,
        name=f"sync test {company_id}",
        owner_user_id="seed_owner",
        members={},
        subdomain=subdomain,
    )
    user = User(
        user_id="seed_owner",
        name="seed",
        active_company_id=company_id,
        companies={company_id: ["owner"]},
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def seed_namespace_via_repo(
    di: PlatformDi,
    company_id: str,
    name: str,
    *,
    subdomain: str | None = None,
) -> str:
    """Создаёт namespace через NamespaceService (SQL + OpenFGA dual-write) DI вызывающего теста."""
    resolved_subdomain = subdomain
    if resolved_subdomain is None:
        company = await Company.get(company_id)
        if company is not None and company.subdomain is not None and company.subdomain.strip() != "":
            resolved_subdomain = company.subdomain

    with _temporary_company_context(company_id, subdomain=resolved_subdomain):
        existing = await di.namespace_service.get(name)
        if existing is None:
            _ = await di.namespace_service.create(
                name=name,
                description="sync test namespace",
            )
        else:
            await di.authz_service.write(
                [
                    platform_namespace_company_link(company_id, name),
                    platform_namespace_company_viewer_tuple(company_id, name),
                    platform_namespace_company_editor_tuple(company_id, name),
                ]
            )
    return name


async def create_topic_channel_via_http(
    sync_client,
    sync_auth_headers: dict[str, str],
    *,
    company_id: str,
    unique_id: str,
    suffix: str = "",
    channel_name: str = "TopicChannel",
) -> str:
    """Создаёт topic-канал через REST sync, предварительно засеяв namespace."""
    from tests.sync.conftest import require_sync_di

    namespace = f"ns_{unique_id}_{suffix}" if suffix else f"ns_{unique_id}"
    await seed_namespace_via_repo(require_sync_di(), company_id, namespace)
    cr = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=sync_auth_headers,
        json={
            "namespace": namespace,
            "type": "topic",
            "name": channel_name,
            "is_private": False,
        },
    )
    assert cr.status_code == 201, cr.text
    return cr.json()["channel_id"]


def platform_auxiliary_file_spec_json(*, is_public: bool = True) -> str:
    import json

    return json.dumps(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


async def upload_platform_file(
    frontend_client,
    auth_headers,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    is_public: bool = True,
):
    from tests.files.chunked_upload_helpers import chunked_upload_file

    return await chunked_upload_file(
        frontend_client,
        auth_headers,
        content=content,
        original_name=filename,
        content_type=content_type,
        spec_json=platform_auxiliary_file_spec_json(is_public=is_public),
    )


_FRONTEND_HTTP_BASE_URL = "http://127.0.0.1:9004"


async def upload_platform_file_http(
    auth_token: str,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    is_public: bool = True,
):
    """Upload через реальный frontend_service — нужен sync_worker и transcribe/STT."""
    from httpx import AsyncClient

    from tests.files.chunked_upload_helpers import chunked_upload_file

    headers = {"Authorization": f"Bearer {auth_token}"}
    async with AsyncClient(base_url=_FRONTEND_HTTP_BASE_URL, timeout=60.0) as client:
        return await chunked_upload_file(
            client,
            headers,
            content=content,
            original_name=filename,
            content_type=content_type,
            spec_json=platform_auxiliary_file_spec_json(is_public=is_public),
        )
