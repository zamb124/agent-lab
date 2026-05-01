#!/usr/bin/env python3
"""
Создаёт или обновляет пять публичных embed (company system) для каталога /demo/digital-workers.

Предусловия:
  - Подняты сервисы и flows подгрузили bundles (lawyer, doctor, psy, coach, tutor).
  - Картинки доступны по HTTP на сервисе flows: ``/static/demo_cards/*.jpg``.

Переменные окружения:
  FLOWS_PUBLIC_BASE_URL — базовый URL сервиса flows (без слэша), по умолчанию http://127.0.0.1:8001

Запуск из корня репозитория:
  uv run python scripts/seed_system_landing_demo_embeds.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from apps.frontend.container import get_frontend_container
from core.context import clear_context, set_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.models.context_models import Context
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.models.identity_models import User

logger = get_logger(__name__)

_DEMOS: tuple[dict[str, str | int], ...] = (
    {
        "embed_id": "landing_demo_lawyer",
        "flow_id": "lawyer",
        "name": "Юридический ориентир",
        "assistant_title": "Юридический ориентир",
        "greeting_message": "Общие ориентиры и что уточнить у юриста. Демо, не консультация.",
        "sort": 10,
        "image": "lawyer.jpg",
    },
    {
        "embed_id": "landing_demo_doctor",
        "flow_id": "doctor",
        "name": "Здоровье: просветительский",
        "assistant_title": "Ориентир по здоровью",
        "greeting_message": "Просветительские ориентиры и когда очень важно обратиться к врачу. Не диагноз.",
        "sort": 20,
        "image": "doctor.jpg",
    },
    {
        "embed_id": "landing_demo_psy",
        "flow_id": "psy",
        "name": "Психологический ориентир",
        "assistant_title": "Психодемо-ассистент",
        "greeting_message": "Поддержка и ориентиры. Демо, не терапия. При кризисе обращайтесь к специалистам и службам 112/103.",
        "sort": 30,
        "image": "psy.jpg",
    },
    {
        "embed_id": "landing_demo_coach",
        "flow_id": "coach",
        "name": "Карьерный коуч",
        "assistant_title": "Карьерный демо-коуч",
        "greeting_message": "Структура целей и черновик резюме. Демо, без гарантий трудоустройства.",
        "sort": 40,
        "image": "coach.jpg",
    },
    {
        "embed_id": "landing_demo_tutor",
        "flow_id": "tutor",
        "name": "Репетитор",
        "assistant_title": "Демо-репетитор",
        "greeting_message": "Объясню тему простыми словами. Демо, не ответ на ваше контрольное.",
        "sort": 50,
        "image": "tutor.jpg",
    },
)


def _flows_base_url() -> str:
    raw = os.environ.get("FLOWS_PUBLIC_BASE_URL", "http://127.0.0.1:8001")
    return raw.strip().rstrip("/")


async def _run() -> None:
    base = _flows_base_url()
    container = get_frontend_container()
    company = await container.company_repository.get(SYSTEM_COMPANY_ID)
    if company is None:
        raise RuntimeError("Компания system не найдена. Проверьте bootstrap и shared storage.")

    admin = await container.user_repository.get("user_zambas124_yandex_ru_001")
    user_ctx = (
        admin
        if admin is not None
        else User(
            user_id="seed_landing_embeds",
            name="Seed landing embeds",
            email="seed@humanitec.local",
            companies={SYSTEM_COMPANY_ID: ["admin"]},
            active_company_id=SYSTEM_COMPANY_ID,
        )
    )
    ctx = Context(
        user=user_ctx,
        active_company=company,
        session_id="seed_system_landing_demo_embeds",
        channel="http",
    )
    set_context(ctx)
    try:
        cfg_repo = container.embed_config_repository
        map_repo = container.embed_mapping_repository
        now = datetime.now(timezone.utc)

        for d in _DEMOS:
            embed_id = str(d["embed_id"])
            image_name = str(d["image"])
            card_url = f"{base}/static/demo_cards/{image_name}"

            prev = await cfg_repo.get(embed_id)
            created_at = prev.created_at if prev is not None else now
            created_by = prev.created_by if prev is not None else "scripts.seed_system_landing_demo_embeds"

            config = EmbedConfig(
                embed_id=embed_id,
                name=str(d["name"]),
                flow_id=str(d["flow_id"]),
                branch_id="default",
                allowed_origins=[],
                status=EmbedStatus.ACTIVE,
                theme="dark",
                show_launcher=True,
                show_reasoning=False,
                show_tool_calls=False,
                primary_color="#6366f1",
                greeting_message=str(d["greeting_message"]),
                assistant_title=str(d["assistant_title"]),
                interface_locale="auto",
                placeholder="Введите сообщение...",
                branding=True,
                landing_visible=True,
                landing_card_image_url=card_url,
                landing_sort_order=int(d["sort"]),
                usage_count=prev.usage_count if prev is not None else 0,
                last_used_at=prev.last_used_at if prev is not None else None,
                created_at=created_at,
                created_by=created_by,
                updated_at=now,
            )
            await cfg_repo.set(config)
            await map_repo.set(EmbedMapping(embed_id=embed_id, company_id=SYSTEM_COMPANY_ID))
            logger.info(
                "landing_demo_embed_upserted",
                embed_id=embed_id,
                flow_id=config.flow_id,
                landing_card_image_url=card_url,
            )
            print(f"OK {embed_id} -> {config.flow_id} card={card_url}")
    finally:
        clear_context()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
