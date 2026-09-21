"""REST API платформенных правил произношения TTS (только system/superadmin).

Маршруты:
    GET    /api/platform/pronunciation-rules         — список
    POST   /api/platform/pronunciation-rules         — создать
    PUT    /api/platform/pronunciation-rules/{id}    — обновить
    DELETE /api/platform/pronunciation-rules/{id}    — удалить

После любого мутирующего вызова сбрасывается платформенный TTL-кэш.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.voice.dependencies import ContainerDep
from core.ai.runtime import invalidate_voice_platform_pronunciation_cache
from core.clients.tts_pronunciation.models import PronunciationRule
from core.context import require_context
from core.db.repositories.pronunciation_rule_repository import pronunciation_rule
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/platform/pronunciation-rules",
    tags=["frontend", "platform", "pronunciation"],
)


class PlatformPronunciationRuleCreateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: Literal["alias", "regex", "stress"]
    pattern: str = Field(min_length=1)
    replacement: str
    language: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True
    providers: list[str] | None = None
    voices: list[str] | None = None
    enabled: bool = True
    note: str | None = None


class PlatformPronunciationRuleUpdateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: Literal["alias", "regex", "stress"] | None = None
    pattern: str | None = Field(default=None, min_length=1)
    replacement: str | None = None
    language: str | None = None
    case_sensitive: bool | None = None
    word_boundary: bool | None = None
    providers: list[str] | None = None
    voices: list[str] | None = None
    enabled: bool | None = None
    note: str | None = None


class PlatformPronunciationRulesListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[PronunciationRule]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _require_superadmin(container: ContainerDep) -> User:
    context = require_context()
    user = context.user
    company = context.active_company
    if company is None or company.company_id != "system":
        raise HTTPException(
            status_code=403, detail="Platform rules can be managed only by system administrators"
        )
    await container.authz_service.require_company_admin(
        company_id="system",
        user_id=user.user_id,
    )
    return user


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@router.get("", response_model=PlatformPronunciationRulesListResponse)
async def list_platform_pronunciation_rules(
    container: ContainerDep,
) -> PlatformPronunciationRulesListResponse:
    """Список платформенных правил произношения TTS."""
    _ = await _require_superadmin(container)
    rows = await container.platform_pronunciation_rule_repository.list_all()
    return PlatformPronunciationRulesListResponse(items=[pronunciation_rule(r) for r in rows])


@router.post("", response_model=PronunciationRule, status_code=201)
async def create_platform_pronunciation_rule(
    payload: PlatformPronunciationRuleCreateRequest,
    container: ContainerDep,
) -> PronunciationRule:
    """Создать платформенное правило произношения TTS."""
    user = await _require_superadmin(container)
    row = await container.platform_pronunciation_rule_repository.create(
        kind=payload.kind,
        pattern=payload.pattern,
        replacement=payload.replacement,
        language=payload.language,
        case_sensitive=payload.case_sensitive,
        word_boundary=payload.word_boundary,
        providers=payload.providers,
        voices=payload.voices,
        enabled=payload.enabled,
        note=payload.note,
    )
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_created",
        rule_id=row.id,
        kind=payload.kind,
        actor_user_id=user.user_id,
    )
    return pronunciation_rule(row)


@router.put("/{rule_id}", response_model=PronunciationRule)
async def update_platform_pronunciation_rule(
    rule_id: str,
    payload: PlatformPronunciationRuleUpdateRequest,
    container: ContainerDep,
) -> PronunciationRule:
    """Обновить платформенное правило произношения TTS."""
    user = await _require_superadmin(container)
    row = await container.platform_pronunciation_rule_repository.update(
        rule_id,
        kind=payload.kind,
        pattern=payload.pattern,
        replacement=payload.replacement,
        language=payload.language,
        case_sensitive=payload.case_sensitive,
        word_boundary=payload.word_boundary,
        providers=payload.providers,
        voices=payload.voices,
        enabled=payload.enabled,
        note=payload.note,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_updated",
        rule_id=rule_id,
        actor_user_id=user.user_id,
    )
    return pronunciation_rule(row)


@router.delete("/{rule_id}")
async def delete_platform_pronunciation_rule(
    rule_id: str,
    container: ContainerDep,
) -> dict[str, bool]:
    """Удалить платформенное правило произношения TTS."""
    user = await _require_superadmin(container)
    deleted = await container.platform_pronunciation_rule_repository.delete(rule_id)
    invalidate_voice_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_deleted",
        rule_id=rule_id,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}
