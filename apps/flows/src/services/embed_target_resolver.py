"""Резолвер embed-конфига для embed A2A маршрутов."""

from dataclasses import dataclass

from core.models.embed_models import EmbedConfig, EmbedInterfaceLook, EmbedStatus
from core.models.identity_models import Company
from core.ui_document.document import FlowUIConversationSettings, FlowUIPageId


@dataclass(frozen=True)
class EmbedTarget:
    embed_id: str
    company_id: str
    flow_id: str
    branch_id: str
    allowed_origins: list[str]
    active: bool
    guest_max_user_messages: int | None
    look: EmbedInterfaceLook
    conversation: FlowUIConversationSettings | None
    start_page_id: FlowUIPageId | None


async def resolve_embed_target(embed_id: str) -> EmbedTarget | None:
    """Возвращает embed target с flow/skill/origins по embed_id."""
    config = await EmbedConfig.get(embed_id)
    if config is None:
        return None

    company = await Company.get(config.company_id)
    if company is None:
        raise ValueError(f"Company for embed_id '{embed_id}' not found")

    guest_cap = config.guest_max_user_messages
    if guest_cap is not None and guest_cap < 1:
        raise ValueError(f"embed {embed_id} guest_max_user_messages must be >= 1")

    return EmbedTarget(
        embed_id=embed_id,
        company_id=company.company_id,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
        allowed_origins=list(config.allowed_origins),
        active=config.status == EmbedStatus.ACTIVE,
        guest_max_user_messages=guest_cap,
        look=EmbedInterfaceLook.from_embed_config(config),
        conversation=config.conversation,
        start_page_id=config.start_page_id,
    )
