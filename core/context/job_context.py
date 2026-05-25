"""Общий билдер ``Context`` + JWT для фоновых задач (reembed, scheduler-tick'и и т.п.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service

if TYPE_CHECKING:
    from core.db.repositories.user_repository import UserRepository


def build_job_context(
    *,
    company: Company,
    user: User,
    host: str,
    trace_id: str,
    session_id: str,
    channel: str,
) -> Context:
    """
    Собирает ``Context`` для фоновой задачи и подписывает JWT через ``get_token_service``.

    Проверяет членство ``user`` в ``company`` (Zero-Guess) — без него запрос от имени
    компании невалиден и контекст не должен молча создаваться.
    """
    cid = company.company_id
    if cid not in user.companies:
        raise ValueError(
            f"build_job_context: пользователь {user.user_id} не состоит в компании {cid}",
        )
    roles = user.companies[cid]
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=cid,
        roles=roles,
    )
    context_user = user.model_copy(update={"active_company_id": cid})
    return Context(
        user=context_user,
        host=host,
        session_id=session_id,
        channel=channel,
        language=Language.RU,
        active_company=company,
        user_companies=[company],
        trace_id=trace_id,
        auth_token=auth_token,
    )


async def pick_company_billing_user(
    *,
    company: Company,
    user_repository: UserRepository,
) -> User:
    """
    Детерминированный платёжный субъект для фоновой задачи в контексте ``company``.

    1. ``company.owner_user_id`` (если такой пользователь есть и состоит в компании).
    2. Иначе среди ``company.members`` с ролью ``owner`` — минимальный ``user_id``
       (лексикографически), пользователь существует и состоит в компании.
    3. Иначе — ``ValueError`` (нет валидного владельца — фоновая задача от имени
       компании невозможна, данные требуют ручной починки).
    """
    cid = company.company_id
    raw_owner = (company.owner_user_id or "").strip()
    if raw_owner:
        loaded = await user_repository.get(raw_owner)
        if loaded is not None and cid in loaded.companies:
            return loaded

    candidates = sorted(
        uid
        for uid, roles in company.members.items()
        if "owner" in roles
    )
    for uid in candidates:
        loaded = await user_repository.get(uid)
        if loaded is not None and cid in loaded.companies:
            return loaded

    raise ValueError(f"pick_company_billing_user: у компании {cid} нет валидного owner-пользователя")
