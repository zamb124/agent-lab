"""
Идемпотентное создание демо-embed для лендинга «Цифровые сотрудники» (компания system).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.frontend.models import LandingDemoSpec
from core.context import clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.models.context_models import Context
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.identity_models import User

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer

logger = get_logger(__name__)

LANDING_DEMO_SPECS: tuple[LandingDemoSpec, ...] = (
    LandingDemoSpec(
        embed_id="landing_demo_lawyer",
        flow_id="lawyer",
        name="Юридический аналитик (РФ)",
        assistant_title="Юридический аналитик (РФ)",
        greeting_message="Структурированный разбор по праву РФ и ориентиры, где свериться с НПА и реестрами. ИИ не заменяет юриста — перед решениями проверьте актуальные источники.",
        sort=10,
        image="lawyer.jpg",
    ),
    LandingDemoSpec(
        embed_id="landing_demo_doctor",
        flow_id="support_demo",
        name="Поддержка: демо",
        assistant_title="Демо сотрудника поддержки",
        greeting_message="Учебный сценарий первой линии: номер заказа, мок-данные в базе, уточнение проблемы и подсказки по следующим шагам. Реальных изменений в заказах нет.",
        sort=20,
        image="support_demo.jpg",
        show_tool_calls=True,
        guest_max_user_messages=10,
    ),
    LandingDemoSpec(
        embed_id="landing_demo_psy",
        flow_id="psy",
        name="Психологический ориентир",
        assistant_title="Психодемо-ассистент",
        greeting_message="Поддержка и ориентиры. Демо, не терапия. При кризисе обращайтесь к специалистам и службам 112/103.",
        sort=30,
        image="psy.jpg",
    ),
    LandingDemoSpec(
        embed_id="landing_demo_coach",
        flow_id="coach",
        name="Фитнес-тренер",
        assistant_title="Демо фитнес-тренер",
        greeting_message="План тренировки, техника, нагрузка без медицинских диагнозов. Демо.",
        sort=40,
        image="coach.jpg",
    ),
    LandingDemoSpec(
        embed_id="landing_demo_tutor",
        flow_id="tutor",
        name="Репетитор",
        assistant_title="Демо-репетитор",
        greeting_message="Объясню тему простыми словами. Демо, не ответ на ваше контрольное.",
        sort=50,
        image="tutor.jpg",
    ),
)


def landing_demo_embed_ids() -> tuple[str, ...]:
    return tuple(spec.embed_id for spec in LANDING_DEMO_SPECS)


LANDING_DEMO_IMAGE_BY_EMBED_ID: dict[str, str] = {
    spec.embed_id: spec.image for spec in LANDING_DEMO_SPECS
}


def _landing_demo_card_url(image: str) -> str:
    return f"/flows/demo_cards/{image}"


def public_landing_demo_card_url(embed_id: str) -> str | None:
    """
    Относительный URL превью для встроенных демо-embed лендинга.
    Сервис flows отдаёт файлы с mount /flows/demo_cards (тот же префикс, что у dev-proxy).
    """
    image = LANDING_DEMO_IMAGE_BY_EMBED_ID.get(embed_id)
    if image is None:
        return None
    return _landing_demo_card_url(image)


async def ensure_system_landing_demo_embeds(container: FrontendContainer) -> None:
    """
    Создаёт или обновляет пять публичных embed (company system) для каталога лендинга.
    Картинка карточки: статика /flows/demo_cards (без S3), чтобы каталог не зависел от бакета и file_id.
    """
    company = await container.company_repository.get(SYSTEM_COMPANY_ID)
    if company is None:
        logger.warning("landing_demo_bootstrap_skip_no_system_company")
        return

    admin = await container.user_repository.get("user_zambas124_yandex_ru_001")
    user_ctx = (
        admin
        if admin is not None
        else User(
            user_id="bootstrap_landing_demos",
            name="Bootstrap landing demos",
            emails=["bootstrap-landing@humanitec.local"],
            companies={SYSTEM_COMPANY_ID: ["admin"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    ctx = Context(
        user=user_ctx,
        active_company=company,
        session_id="ensure_system_landing_demo_embeds",
        channel="http",
    )
    set_context(ctx)
    try:
        cfg_repo = container.embed_config_repository
        map_repo = container.embed_mapping_repository
        now = datetime.now(timezone.utc)

        for spec in LANDING_DEMO_SPECS:
            embed_id = spec.embed_id
            flow_id = spec.flow_id
            card_url = _landing_demo_card_url(spec.image)

            prev = await cfg_repo.get(embed_id)
            created_at = prev.created_at if prev is not None else now
            created_by = (
                prev.created_by
                if prev is not None
                else "apps.frontend.services.landing_demo_seed"
            )

            config = EmbedConfig(
                embed_id=embed_id,
                name=spec.name,
                flow_id=flow_id,
                branch_id="default",
                allowed_origins=[],
                status=EmbedStatus.ACTIVE,
                theme="dark",
                show_launcher=True,
                show_reasoning=False,
                show_tool_calls=spec.show_tool_calls,
                primary_color="#6366f1",
                greeting_message=spec.greeting_message,
                assistant_title=spec.assistant_title,
                interface_locale="auto",
                placeholder="Введите сообщение...",
                branding=True,
                landing_visible=True,
                landing_card_image_url=card_url,
                landing_sort_order=spec.sort,
                guest_max_user_messages=spec.guest_max_user_messages,
                usage_count=prev.usage_count if prev is not None else 0,
                last_used_at=prev.last_used_at if prev is not None else None,
                created_at=created_at,
                created_by=created_by,
                updated_at=now,
            )
            _ = await cfg_repo.set(config)
            _ = await map_repo.set(EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID))
            logger.info(
                "landing_demo_embed_upserted",
                embed_id=embed_id,
                flow_id=config.flow_id,
                landing_card_image_url=card_url,
            )
    finally:
        clear_context()
