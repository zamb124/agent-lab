"""Общие helpers для HTTP-тестов sync.

После удаления SyncSpace тесты создают namespace через shared
`NamespaceRepository` (CRM-сервиса в тестовом контейнере sync нет, поэтому
вместо REST `/crm/api/v1/namespaces` идём напрямую в репозиторий).

`NamespaceRepository.is_global = False`, поэтому `set` требует активный
`Context` с `active_company`. В pytest-процессе он не выставлен — поднимаем
на короткое время для seed'а, потом сбрасываем.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, Namespace, User


@contextmanager
def _temporary_company_context(company_id: str) -> Iterator[None]:
    """Поднимает минимальный Context с `active_company.company_id` для записи в KV.

    `subdomain` намеренно None — ключ строится через
    `company_identifier = subdomain or company_id` (см. `BaseRepository`).
    """
    previous = get_context()
    company = Company(
        company_id=company_id,
        name=f"sync test {company_id}",
        owner_user_id="seed_owner",
        members={},
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


async def seed_namespace_via_repo(company_id: str, name: str) -> str:
    """Создаёт namespace в shared `NamespaceRepository` для тестовой компании."""
    from apps.sync.container import get_sync_container

    container = get_sync_container()
    with _temporary_company_context(company_id):
        await container.namespace_repository.set(
            Namespace(
                name=name,
                company_id=company_id,
                description="sync test namespace",
                is_default=False,
            )
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
    namespace = f"ns_{unique_id}_{suffix}" if suffix else f"ns_{unique_id}"
    await seed_namespace_via_repo(company_id, namespace)
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
    import io

    return await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers,
        data={"spec": platform_auxiliary_file_spec_json(is_public=is_public)},
        files={"file": (filename, io.BytesIO(content), content_type)},
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
    import io

    from httpx import AsyncClient

    headers = {"Authorization": f"Bearer {auth_token}"}
    async with AsyncClient(base_url=_FRONTEND_HTTP_BASE_URL, timeout=60.0) as client:
        return await client.post(
            "/frontend/api/v1/files/",
            headers=headers,
            data={"spec": platform_auxiliary_file_spec_json(is_public=is_public)},
            files={"file": (filename, io.BytesIO(content), content_type)},
        )
