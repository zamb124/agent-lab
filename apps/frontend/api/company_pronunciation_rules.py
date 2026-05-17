"""REST API per-company правил произношения TTS.

Маршруты:
    GET    /api/companies/{company_id}/pronunciation-rules         — список (member)
    POST   /api/companies/{company_id}/pronunciation-rules         — создать (owner/admin)
    PUT    /api/companies/{company_id}/pronunciation-rules/{id}    — обновить (owner/admin)
    DELETE /api/companies/{company_id}/pronunciation-rules/{id}    — удалить (owner/admin)
    POST   /api/companies/{company_id}/pronunciation-rules/test    — dry-run preview (member)

После любого мутирующего вызова сбрасываются TTL-кэши voice_resolver.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.dependencies import ContainerDep
from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRuleKind,
    PronunciationRuleSet,
)
from core.clients.tts_pronunciation.pipeline import get_tts_text_pipeline
from core.clients.voice_resolver import invalidate_company_overrides_cache
from core.db.models.platform import CompanyPronunciationRule
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/companies/{company_id}/pronunciation-rules",
    tags=["frontend", "pronunciation"],
)

_MAX_RULES_PER_COMPANY = 1000


# ---------------------------------------------------------------------------
# Pydantic DTO
# ---------------------------------------------------------------------------

class PronunciationRuleDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["alias", "regex", "stress"]
    pattern: str
    replacement: str
    language: Optional[str] = None
    case_sensitive: bool = False
    word_boundary: bool = True
    providers: Optional[list[str]] = None
    voices: Optional[list[str]] = None
    enabled: bool = True
    note: Optional[str] = None


class PronunciationRuleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["alias", "regex", "stress"] = Field(description="Тип правила.")
    pattern: str = Field(min_length=1, description="Искомое слово / regex.")
    replacement: str = Field(description="Замена.")
    language: Optional[str] = Field(default=None, description="BCP-47 (только ISO 639-1, например 'ru').")
    case_sensitive: bool = Field(default=False)
    word_boundary: bool = Field(default=True)
    providers: Optional[list[str]] = Field(default=None)
    voices: Optional[list[str]] = Field(default=None)
    enabled: bool = Field(default=True)
    note: Optional[str] = Field(default=None)


class PronunciationRuleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Optional[Literal["alias", "regex", "stress"]] = None
    pattern: Optional[str] = Field(default=None, min_length=1)
    replacement: Optional[str] = None
    language: Optional[str] = None
    case_sensitive: Optional[bool] = None
    word_boundary: Optional[bool] = None
    providers: Optional[list[str]] = None
    voices: Optional[list[str]] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class PronunciationRuleTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="Текст для dry-run.")
    provider: str = Field(default="litserve", description="Имя TTS-провайдера.")
    voice: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)


class PronunciationRuleTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    transformed: str
    changed: bool


class PronunciationRulesListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: str
    items: list[PronunciationRuleDTO]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _require_user(request: Request) -> User:
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return request.state.user


def _ensure_member(user: User, company_id: str) -> None:
    if company_id not in user.companies:
        raise HTTPException(status_code=403, detail="Доступ только участникам компании")


def _ensure_admin(user: User, company_id: str) -> None:
    roles = user.companies.get(company_id, [])
    if not any(r in ("owner", "admin") for r in roles):
        raise HTTPException(
            status_code=403,
            detail="Изменять правила произношения могут только owner/admin компании",
        )


def _rule_kind(value: str) -> PronunciationRuleKind:
    if value not in ("alias", "regex", "stress"):
        raise ValueError(f"Неизвестный kind правила произношения: {value!r}")
    return value


def _row_to_dto(row: CompanyPronunciationRule) -> PronunciationRuleDTO:
    return PronunciationRuleDTO(
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

@router.get("", response_model=PronunciationRulesListResponse)
async def list_company_pronunciation_rules(
    company_id: str,
    request: Request,
    container: ContainerDep,
) -> PronunciationRulesListResponse:
    """Список правил произношения TTS компании."""
    user = _require_user(request)
    _ensure_member(user, company_id)
    rows = await container.company_pronunciation_rule_repository.list_all(
        company_id=company_id
    )
    return PronunciationRulesListResponse(
        company_id=company_id,
        items=[_row_to_dto(r) for r in rows],
    )


@router.post("", response_model=PronunciationRuleDTO, status_code=201)
async def create_company_pronunciation_rule(
    company_id: str,
    payload: PronunciationRuleCreateRequest,
    request: Request,
    container: ContainerDep,
) -> PronunciationRuleDTO:
    """Создать правило произношения TTS для компании."""
    user = _require_user(request)
    _ensure_admin(user, company_id)

    try:
        row = await container.company_pronunciation_rule_repository.create(
            company_id=company_id,
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
            max_rules=_MAX_RULES_PER_COMPANY,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_pronunciation_rule_created",
        company_id=company_id,
        rule_id=row.id,
        kind=payload.kind,
        actor_user_id=user.user_id,
    )
    return _row_to_dto(row)


@router.put("/{rule_id}", response_model=PronunciationRuleDTO)
async def update_company_pronunciation_rule(
    company_id: str,
    rule_id: str,
    payload: PronunciationRuleUpdateRequest,
    request: Request,
    container: ContainerDep,
) -> PronunciationRuleDTO:
    """Обновить правило произношения TTS компании."""
    user = _require_user(request)
    _ensure_admin(user, company_id)

    row = await container.company_pronunciation_rule_repository.update(
        company_id=company_id,
        rule_id=rule_id,
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

    invalidate_company_overrides_cache(company_id=company_id)
    logger.info(
        "frontend.company_pronunciation_rule_updated",
        company_id=company_id,
        rule_id=rule_id,
        actor_user_id=user.user_id,
    )
    return _row_to_dto(row)


@router.delete("/{rule_id}")
async def delete_company_pronunciation_rule(
    company_id: str,
    rule_id: str,
    request: Request,
    container: ContainerDep,
) -> dict[str, bool]:
    """Удалить правило произношения TTS компании."""
    user = _require_user(request)
    _ensure_admin(user, company_id)

    deleted = await container.company_pronunciation_rule_repository.delete(
        company_id=company_id,
        rule_id=rule_id,
    )
    invalidate_company_overrides_cache(company_id=company_id)
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
    request: Request,
    container: ContainerDep,
) -> PronunciationRuleTestResponse:
    """Dry-run: применить текущие правила произношения к тексту и вернуть результат.

    Включает только per-company правила (без платформенных).
    """
    user = _require_user(request)
    _ensure_member(user, company_id)

    rows = await container.company_pronunciation_rule_repository.list_enabled(
        company_id=company_id
    )
    rules = [
        PronunciationRule(
            id=r.id,
            kind=_rule_kind(r.kind),
            pattern=r.pattern,
            replacement=r.replacement,
            language=r.language,
            case_sensitive=r.case_sensitive,
            word_boundary=r.word_boundary,
            providers=list(r.providers) if r.providers else None,
            voices=list(r.voices) if r.voices else None,
            enabled=r.enabled,
            note=r.note,
        )
        for r in rows
    ]
    rule_set = PronunciationRuleSet(rules=rules, normalization=NormalizationConfig())
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
