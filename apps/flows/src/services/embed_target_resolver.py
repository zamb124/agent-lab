"""Резолвер embed-конфига для embed A2A маршрутов."""

from dataclasses import dataclass

from apps.flows.src.container import FlowContainer
from core.context import Context, clear_context, get_context, set_context
from core.models.context_models import Language
from core.models.embed_models import EmbedStatus
from core.models.identity_models import Company, User


@dataclass(frozen=True)
class EmbedTarget:
    embed_id: str
    company_id: str
    flow_id: str
    branch_id: str
    allowed_origins: list[str]
    active: bool
    guest_max_user_messages: int | None


async def resolve_embed_target(container: FlowContainer, embed_id: str) -> EmbedTarget | None:
    """Возвращает embed target с flow/skill/origins по embed_id."""
    mapping = await container.embed_mapping_repository.get(embed_id)
    if mapping is None:
        return None

    company = await container.company_repository.get(mapping.company_id)
    if company is None:
        raise ValueError(f"Company for embed_id '{embed_id}' not found")

    config = await _load_embed_config_in_company_scope(container, embed_id=embed_id, company=company)
    if config is None:
        return None

    guest_cap = config.guest_max_user_messages
    if guest_cap is not None and guest_cap < 1:
        guest_cap = None

    return EmbedTarget(
        embed_id=embed_id,
        company_id=company.company_id,
        flow_id=config.flow_id,
        branch_id=config.branch_id,
        allowed_origins=list(config.allowed_origins or []),
        active=config.status == EmbedStatus.ACTIVE,
        guest_max_user_messages=guest_cap,
    )


async def _load_embed_config_in_company_scope(
    container: FlowContainer,
    *,
    embed_id: str,
    company: Company,
):
    previous_context = get_context()
    user = previous_context.user if previous_context is not None else User(user_id="system", name="System")
    host = previous_context.host if previous_context is not None else ""
    session_id = previous_context.session_id if previous_context is not None else "embed-resolver"
    channel = previous_context.channel if previous_context is not None else "system"
    trace_id = previous_context.trace_id if previous_context is not None else None
    language = previous_context.language if previous_context is not None else Language.RU
    active_namespace = previous_context.active_namespace if previous_context is not None else "default"

    set_context(
        Context(
            user=user,
            host=host,
            session_id=session_id,
            channel=channel,
            active_company=company,
            trace_id=trace_id,
            language=language,
            active_namespace=active_namespace,
        )
    )
    try:
        return await container.embed_config_repository.get(embed_id)
    finally:
        if previous_context is not None:
            set_context(previous_context)
        else:
            clear_context()
