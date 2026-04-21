"""Общие helpers для интеграционных тестов sync.

После удаления SyncSpace тесты создают канал через `op_channels_create`,
предварительно засевая платформенный namespace в shared
`NamespaceRepository`.
"""

from __future__ import annotations

from apps.sync.container import SyncContainer
from apps.sync.models.channels import ChannelCreate, ChannelType
from apps.sync.realtime.operations import op_channels_create
from core.models.identity_models import Namespace, User


async def seed_test_namespace(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
    *,
    suffix: str = "",
) -> str:
    """Создаёт namespace в shared `NamespaceRepository` и возвращает имя."""
    company_id = op_user.active_company_id
    if not isinstance(company_id, str) or company_id == "":
        raise ValueError("op_user.active_company_id обязателен для seed_test_namespace.")
    name = f"ns_{unique_id}_{suffix}" if suffix else f"ns_{unique_id}"
    await op_container.namespace_repository.set(
        Namespace(
            name=name,
            company_id=company_id,
            description=f"sync test namespace {unique_id}",
            is_default=False,
        )
    )
    return name


async def create_test_topic_channel(
    op_user: User,
    op_container: SyncContainer,
    unique_id: str,
    *,
    name_suffix: str = "",
) -> str:
    """Создаёт topic-канал в новом namespace и возвращает channel_id."""
    namespace = await seed_test_namespace(op_user, op_container, unique_id, suffix=name_suffix or "ch")
    ch = await op_channels_create(
        ChannelCreate(
            type=ChannelType.TOPIC,
            name=f"Ch {unique_id}{name_suffix}",
            namespace=namespace,
            is_private=False,
        ),
        user=op_user,
        container=op_container,
    )
    return ch.id
