"""DocumentsClient against ASGI office service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from core.clients.documents_client import DocumentsClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("office_app")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="documents-client-test",
        session_id="documents-client",
        channel="test",
    )
    set_context(ctx.model_copy(update={"active_namespace": namespace}))
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_documents_client_create_catalog_and_empty(
    frontend_di,
    unique_id: str,
) -> None:
    company = await Company.get("system")
    assert company is not None
    user = await User.get("system")
    assert user is not None
    namespace = f"docs-client-{unique_id}"
    await seed_namespace_via_repo(frontend_di, "system", namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        client = DocumentsClient()
        catalog = await client.create_catalog(title=f"Folder {unique_id}")
        catalog_id = catalog.get("catalog_id")
        assert isinstance(catalog_id, str) and catalog_id.strip()

        created = await client.create_empty(
            title=f"Doc {unique_id}",
            catalog_id=catalog_id,
            document_type="word",
        )
        file_id = created.get("file_id")
        assert isinstance(file_id, str) and file_id.strip()
        assert created.get("catalog_id") == catalog_id

        listed = await client.list_catalog(catalog_id)
        assert listed.get("catalog_id") == catalog_id
        documents = listed.get("documents")
        assert isinstance(documents, list)
        assert any(item.get("file_id") == file_id for item in documents if isinstance(item, dict))

        renamed = await client.rename(file_id=file_id, title=f"Renamed {unique_id}")
        assert renamed.get("title") == f"Renamed {unique_id}"

        link = await client.get_link(file_id=file_id, kind="editor")
        assert link.get("kind") == "editor"
        assert f"/documents/edit/{file_id}" in str(link.get("url"))
