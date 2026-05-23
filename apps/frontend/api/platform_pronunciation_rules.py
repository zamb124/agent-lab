"""REST API платформенных правил произношения TTS (только system/superadmin).

Маршруты:
    GET    /api/platform/pronunciation-rules         — список
    POST   /api/platform/pronunciation-rules         — создать
    PUT    /api/platform/pronunciation-rules/{id}    — обновить
    DELETE /api/platform/pronunciation-rules/{id}    — удалить

После любого мутирующего вызова сбрасывается платформенный TTL-кэш.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.dependencies import ContainerDep
from core.clients.tts_pronunciation.models import PronunciationRuleKind
from core.clients.voice_resolver import invalidate_platform_pronunciation_cache
from core.db.models.platform import PlatformPronunciationRule
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/platform/pronunciation-rules",
    tags=["frontend", "platform", "pronunciation"],
)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------

class PlatformPronunciationRuleDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["alias", "regex", "stress"]
    pattern: str
    replacement: str
    language: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True
    providers: list[str] | None = None
    voices: list[str] | None = None
    enabled: bool = True
    note: str | None = None


class PlatformPronunciationRuleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    items: list[PlatformPronunciationRuleDTO]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _require_superadmin(request: Request) -> User:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    user: User = request.state.user
    company_id = getattr(request.state, "company", None)
    company_id_str = company_id.company_id if company_id else None
    if company_id_str != "system":
        raise HTTPException(
            status_code=403, detail="Управление платформенными правилами доступно только системным администраторам"
        )
    roles = user.companies.get("system", [])
    if "admin" not in roles and "owner" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Требуются права admin/owner в компании system",
        )
    return user


def _rule_kind(value: str) -> PronunciationRuleKind:
    if value not in ("alias", "regex", "stress"):
        raise ValueError(f"Неизвестный kind правила произношения: {value!r}")
    return value


def _row_to_dto(row: PlatformPronunciationRule) -> PlatformPronunciationRuleDTO:
    return PlatformPronunciationRuleDTO(
        id=row.id,
        kind=_rule_kind(row.kind),
        pattern=row.pattern,
        replacement=row.replacement,
        language=row.language,
        case_sensitive=row.case_sensitive,
        word_boundary=row.word_boundary,
        providers=list(row.providers) if row.providers else None,
        voices=list(row.voices) if row.voices else None,
        enabled=row.enabled,
        note=row.note,
    )


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------

@router.get("", response_model=PlatformPronunciationRulesListResponse)
async def list_platform_pronunciation_rules(
    request: Request,
    container: ContainerDep,
) -> PlatformPronunciationRulesListResponse:
    """Список платформенных правил произношения TTS."""
    _require_superadmin(request)
    rows = await container.platform_pronunciation_rule_repository.list_all()
    return PlatformPronunciationRulesListResponse(items=[_row_to_dto(r) for r in rows])


@router.post("", response_model=PlatformPronunciationRuleDTO, status_code=201)
async def create_platform_pronunciation_rule(
    payload: PlatformPronunciationRuleCreateRequest,
    request: Request,
    container: ContainerDep,
) -> PlatformPronunciationRuleDTO:
    """Создать платформенное правило произношения TTS."""
    user = _require_superadmin(request)
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
    invalidate_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_created",
        rule_id=row.id,
        kind=payload.kind,
        actor_user_id=user.user_id,
    )
    return _row_to_dto(row)


@router.put("/{rule_id}", response_model=PlatformPronunciationRuleDTO)
async def update_platform_pronunciation_rule(
    rule_id: str,
    payload: PlatformPronunciationRuleUpdateRequest,
    request: Request,
    container: ContainerDep,
) -> PlatformPronunciationRuleDTO:
    """Обновить платформенное правило произношения TTS."""
    user = _require_superadmin(request)
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
        raise HTTPException(status_code=404, detail="Правило не найдено")
    invalidate_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_updated",
        rule_id=rule_id,
        actor_user_id=user.user_id,
    )
    return _row_to_dto(row)


@router.delete("/{rule_id}")
async def delete_platform_pronunciation_rule(
    rule_id: str,
    request: Request,
    container: ContainerDep,
) -> dict[str, bool]:
    """Удалить платформенное правило произношения TTS."""
    user = _require_superadmin(request)
    deleted = await container.platform_pronunciation_rule_repository.delete(rule_id)
    invalidate_platform_pronunciation_cache()
    logger.info(
        "frontend.platform_pronunciation_rule_deleted",
        rule_id=rule_id,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return {"deleted": deleted}
