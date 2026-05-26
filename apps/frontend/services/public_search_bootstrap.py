"""Bootstrap fixed public search embeds in company system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.context import Context, clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID, ensure_system_company_exists
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.search import (
    PUBLIC_SEARCH_FLOW_ID,
    PublicSearchMode,
    public_search_branch_id,
    public_search_embed_id,
)

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer

logger = get_logger(__name__)


@dataclass(frozen=True)
class PublicSearchEmbedSpec:
    mode: PublicSearchMode
    name: str
    placeholder: str
    guest_max_user_messages: int

    @property
    def embed_id(self) -> str:
        return public_search_embed_id(self.mode)

    @property
    def branch_id(self) -> str:
        return public_search_branch_id(self.mode)


PUBLIC_SEARCH_EMBED_SPECS: tuple[PublicSearchEmbedSpec, ...] = (
    PublicSearchEmbedSpec(
        mode="quick",
        name="Humanitec Search",
        placeholder="Спросите Humanitec Search...",
        guest_max_user_messages=40,
    ),
    PublicSearchEmbedSpec(
        mode="deep",
        name="Humanitec Deep Search",
        placeholder="Запустить глубокий поиск...",
        guest_max_user_messages=24,
    ),
    PublicSearchEmbedSpec(
        mode="research",
        name="Humanitec Research",
        placeholder="Сформулируйте исследовательский запрос...",
        guest_max_user_messages=12,
    ),
    PublicSearchEmbedSpec(
        mode="source",
        name="Humanitec Source AI",
        placeholder="Заглянуть внутрь источника...",
        guest_max_user_messages=30,
    ),
)

PUBLIC_SEARCH_SPEC_BY_MODE: dict[PublicSearchMode, PublicSearchEmbedSpec] = {
    spec.mode: spec for spec in PUBLIC_SEARCH_EMBED_SPECS
}


def _system_user() -> User:
    return User(
        user_id="system",
        name="System",
        groups=["admin"],
        companies={SYSTEM_COMPANY_ID: ["admin"]},
        active_company_id=SYSTEM_COMPANY_ID,
        emails=["system@humanitec.local"],
    )


async def _set_system_context(container: "FrontendContainer", *, session_id: str) -> Company:
    company = await ensure_system_company_exists(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
    )
    set_context(
        Context(
            user=_system_user(),
            active_company=company,
            session_id=session_id,
            channel="system",
            language=Language.RU,
            trace_id=f"system:{session_id}",
        )
    )
    return company


async def ensure_public_search_embed_configs(
    container: "FrontendContainer",
) -> dict[PublicSearchMode, EmbedConfig]:
    """Create or update the fixed public search embed configs."""
    _ = await _set_system_context(container, session_id="public_search_embed_bootstrap")
    try:
        cfg_repo = container.embed_config_repository
        map_repo = container.embed_mapping_repository
        now = datetime.now(timezone.utc)
        configs: dict[PublicSearchMode, EmbedConfig] = {}

        for spec in PUBLIC_SEARCH_EMBED_SPECS:
            previous = await cfg_repo.get(spec.embed_id)
            config = EmbedConfig(
                embed_id=spec.embed_id,
                name=spec.name,
                flow_id=PUBLIC_SEARCH_FLOW_ID,
                branch_id=spec.branch_id,
                allowed_origins=[],
                status=EmbedStatus.ACTIVE,
                theme="dark",
                position="bottom-right",
                show_launcher=False,
                show_reasoning=False,
                show_tool_calls=False,
                primary_color="#8BA3FF",
                greeting_message="",
                assistant_title=spec.name,
                interface_locale="auto",
                placeholder=spec.placeholder,
                branding=True,
                landing_visible=False,
                guest_max_user_messages=spec.guest_max_user_messages,
                usage_count=previous.usage_count if previous is not None else 0,
                last_used_at=previous.last_used_at if previous is not None else None,
                created_at=previous.created_at if previous is not None else now,
                created_by=(
                    previous.created_by
                    if previous is not None
                    else "apps.frontend.services.public_search_bootstrap"
                ),
                updated_at=now,
            )
            _ = await cfg_repo.set(config)
            _ = await map_repo.set(
                EmbedMapping(embed_id=spec.embed_id, company_id=SYSTEM_COMPANY_ID)
            )
            configs[spec.mode] = config
            logger.info(
                "public_search_embed_upserted",
                embed_id=config.embed_id,
                flow_id=config.flow_id,
                branch_id=config.branch_id,
            )
        return configs
    finally:
        clear_context()
