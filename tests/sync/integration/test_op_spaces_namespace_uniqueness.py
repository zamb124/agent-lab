"""op_spaces_create — namespace 1:1 с SyncSpace.

Реальная БД + shared NamespaceRepository. Без моков.
"""

from __future__ import annotations

import pytest

from apps.sync.container import SyncContainer
from apps.sync.models.spaces import SpaceCreate
from apps.sync.realtime.operations import (
    SpacesCreatePayload,
    op_spaces_create,
)
from core.context import clear_context
from core.models.identity_models import User
from core.websocket import WsCommandError


@pytest.mark.asyncio
async def test_op_spaces_create_creates_namespace_1to1(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
    company_id: str,
) -> None:
    payload = SpacesCreatePayload(
        body=SpaceCreate(
            name=f"NS Test {unique_id}",
            description=None,
            namespace=f"ns_{unique_id}",
        )
    )
    space = await op_spaces_create(payload, user=op_user, container=op_container)

    assert space.namespace == f"ns_{unique_id}"
    # Namespace зарегистрирован в shared KV для company.
    ns = await op_container.namespace_repository.get(f"ns_{unique_id}")
    assert ns is not None
    assert ns.company_id == company_id


@pytest.mark.asyncio
async def test_op_spaces_create_rejects_duplicate_namespace_in_same_company(
    op_user: User,
    op_container: SyncContainer,
    op_context: None,
    unique_id: str,
) -> None:
    namespace = f"dup_{unique_id}"
    payload1 = SpacesCreatePayload(
        body=SpaceCreate(name=f"First {unique_id}", description=None, namespace=namespace)
    )
    await op_spaces_create(payload1, user=op_user, container=op_container)

    payload2 = SpacesCreatePayload(
        body=SpaceCreate(name=f"Second {unique_id}", description=None, namespace=namespace)
    )
    with pytest.raises(ValueError, match="уже привязан"):
        await op_spaces_create(payload2, user=op_user, container=op_container)


@pytest.mark.asyncio
async def test_op_spaces_create_no_company_context_raises(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
) -> None:
    """Без get_context() с active_company → WsCommandError('ws_no_company')."""
    clear_context()
    user_no_company = User(user_id=op_user.user_id, name=op_user.name, active_company_id="")
    payload = SpacesCreatePayload(
        body=SpaceCreate(
            name=f"NoCtx {unique_id}", description=None, namespace=f"noctx_{unique_id}"
        )
    )
    with pytest.raises(WsCommandError) as exc_info:
        await op_spaces_create(payload, user=user_no_company, container=op_container)
    assert exc_info.value.code == "ws_no_company"
