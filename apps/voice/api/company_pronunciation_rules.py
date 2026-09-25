"""REST API per-company правил произношения TTS.

Маршруты:
    GET    /api/companies/{company_id}/pronunciation-rules         — список (member)
    POST   /api/companies/{company_id}/pronunciation-rules         — создать (owner/admin)
    PUT    /api/companies/{company_id}/pronunciation-rules/{id}    — обновить (owner/admin)
    DELETE /api/companies/{company_id}/pronunciation-rules/{id}    — удалить (owner/admin)
    POST   /api/companies/{company_id}/pronunciation-rules/test    — dry-run preview (member)

После любого мутирующего вызова сбрасываются TTL-кэши voice runtime.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.voice.di import Di
from core.ai.runtime import invalidate_voice_company_overrides_cache
from core.authz.models import AuthzObject
from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRulePatch,
    PronunciationRuleSet,
    PronunciationRuleWrite,
)
from core.clients.tts_pronunciation.pipeline import get_tts_text_pipeline
from core.context import require_context
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/companies/{company_id}/pronunciation-rules",
    tags=["frontend", "pronunciation"],
)

_MAX_RULES_PER_COMPANY = 1000


class PronunciationRuleTestRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="Текст для dry-run.")
    provider: str = Field(default="litserve", description="Имя TTS-провайдера.")
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)


class PronunciationRuleTestResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    original: str
    transformed: str
    changed: bool


class PronunciationRulesListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    company_id: str
    items: list[PronunciationRule]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
async def _ensure_member(di: Di, user: User, company_id: str) -> None:
    await di.authz_service.require_can_view(
        AuthzObject.company(company_id),
        user_id=user.user_id,
    )


async def _ensure_admin(di: Di, user: User, company_id: str) -> None:
    await di.authz_service.require_company_admin(
        company_id=company_id,
        user_id=user.user_id,
    )


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@router.get("", response_model=PronunciationRulesListResponse)
async def list_company_pronunciation_rules(
    company_id: str,
    di: Di,
) -> PronunciationRulesListResponse:
    """Список правил произношения TTS компании."""
    user = require_context().user
    await _ensure_member(di, user, company_id)
    rows = await PronunciationRule.all_for_company_scope(company_id=company_id)
    return PronunciationRulesListResponse(company_id=company_id, items=rows)


@router.post("", response_model=PronunciationRule, status_code=201)
async def create_company_pronunciation_rule(
    company_id: str,
    payload: PronunciationRuleWrite,
    di: Di,
) -> PronunciationRule:
    """Создать правило произношения TTS для компании."""
    user = require_context().user
    await _ensure_admin(di, user, company_id)

    try:
        row = await PronunciationRule.create_for_company_scope(
            company_id=company_id,
            rule=payload,
            max_rules=_MAX_RULES_PER_COMPANY,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_voice_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_pronunciation_rule_created",
        company_id=company_id,
        rule_id=row.pronunciation_rule_id,
        kind=payload.kind,
        actor_user_id=user.user_id,
    )
    return row


@router.put("/{rule_id}", response_model=PronunciationRule)
async def update_company_pronunciation_rule(
    company_id: str,
    rule_id: str,
    payload: PronunciationRulePatch,
    di: Di,
) -> PronunciationRule:
    """Обновить правило произношения TTS компании."""
    user = require_context().user
    await _ensure_admin(di, user, company_id)

    row = await PronunciationRule.update_by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=rule_id,
        patch=payload,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    invalidate_voice_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_pronunciation_rule_updated",
        company_id=company_id,
        rule_id=rule_id,
        actor_user_id=user.user_id,
    )
    return row


@router.delete("/{rule_id}")
async def delete_company_pronunciation_rule(
    company_id: str,
    rule_id: str,
    di: Di,
) -> dict[str, bool]:
    """Удалить правило произношения TTS компании."""
    user = require_context().user
    await _ensure_admin(di, user, company_id)

    deleted = await PronunciationRule.delete_by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=rule_id,
    )
    invalidate_voice_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_pronunciation_rule_deleted",
        company_id=company_id,
        rule_id=rule_id,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}


@router.post("/test", response_model=PronunciationRuleTestResponse)
async def test_company_pronunciation_rules(
    company_id: str,
    payload: PronunciationRuleTestRequest,
    di: Di,
) -> PronunciationRuleTestResponse:
    """Dry-run: применить текущие правила произношения к тексту и вернуть результат.

    Включает только per-company правила (без платформенных).
    """
    user = require_context().user
    await _ensure_member(di, user, company_id)

    rows = await PronunciationRule.all_enabled_for_company_scope(company_id=company_id)
    rule_set = PronunciationRuleSet(rules=rows, normalization=NormalizationConfig())
    compiled = CompiledPronunciation.from_rule_set(rule_set)

    pipeline = get_tts_text_pipeline()
    transformed = pipeline.transform(
        payload.text,
        pronunciation=compiled,
        provider=payload.provider,
        voice=payload.voice,
        language=payload.language,
    )
    return PronunciationRuleTestResponse(
        original=payload.text,
        transformed=transformed,
        changed=(transformed != payload.text),
    )
