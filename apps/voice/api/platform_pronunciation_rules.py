"""REST API платформенных правил произношения TTS (только system/superadmin).

Маршруты:
    GET    /api/platform/pronunciation-rules         — список
    POST   /api/platform/pronunciation-rules         — создать
    PUT    /api/platform/pronunciation-rules/{id}    — обновить
    DELETE /api/platform/pronunciation-rules/{id}    — удалить

После любого мутирующего вызова сбрасывается платформенный TTL-кэш.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from apps.voice.di import Di
from core.ai.runtime import invalidate_voice_platform_pronunciation_cache
from core.clients.tts_pronunciation.models import (
    PronunciationRule,
    PronunciationRulePatch,
    PronunciationRuleWrite,
)
from core.context import require_context
from core.logging import get_logger
from core.models.identity_models import User
from core.websocket import WsCommandError

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/platform/pronunciation-rules",
    tags=["frontend", "platform", "pronunciation"],
)


class PlatformPronunciationRulesListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[PronunciationRule]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _require_superadmin(di: Di) -> User:
    context = require_context()
    user = context.user
    company = context.active_company
    if company is None or company.company_id != "system":
        raise WsCommandError(
            "forbidden",
            "Platform rules can be managed only by system administrators",
            error_code="forbidden",
        )
    await di.authz_service.require_company_admin(
        company_id="system",
        user_id=user.user_id,
    )
    return user


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@router.get("", response_model=PlatformPronunciationRulesListResponse)
async def list_platform_pronunciation_rules(
    di: Di,
) -> PlatformPronunciationRulesListResponse:
    """Список платформенных правил произношения TTS."""
    _ = await _require_superadmin(di)
    rows = await PronunciationRule.list_for_company_scope(company_id=None)
    return PlatformPronunciationRulesListResponse(items=rows)


@router.post("", response_model=PronunciationRule, status_code=201)
async def create_platform_pronunciation_rule(
    payload: PronunciationRuleWrite,
    di: Di,
) -> PronunciationRule:
    """Создать платформенное правило произношения TTS."""
    user = await _require_superadmin(di)
    row = await PronunciationRule.create_for_company_scope(company_id=None, rule=payload)
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_created",
        rule_id=row.pronunciation_rule_id,
        kind=payload.kind,
        actor_user_id=user.user_id,
    )
    return row


@router.put("/{rule_id}", response_model=PronunciationRule)
async def update_platform_pronunciation_rule(
    rule_id: str,
    payload: PronunciationRulePatch,
    di: Di,
) -> PronunciationRule:
    """Обновить платформенное правило произношения TTS."""
    user = await _require_superadmin(di)
    row = await PronunciationRule.update_by_company_scope_and_rule_id(
        company_id=None,
        rule_id=rule_id,
        patch=payload,
    )
    if row is None:
        raise WsCommandError("not_found", "Rule not found", error_code="not_found")
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_updated",
        rule_id=rule_id,
        actor_user_id=user.user_id,
    )
    return row


@router.delete("/{rule_id}")
async def delete_platform_pronunciation_rule(
    rule_id: str,
    di: Di,
) -> dict[str, bool]:
    """Удалить платформенное правило произношения TTS."""
    user = await _require_superadmin(di)
    deleted = await PronunciationRule.delete_by_company_scope_and_rule_id(
        company_id=None,
        rule_id=rule_id,
    )
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_deleted",
        rule_id=rule_id,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}
