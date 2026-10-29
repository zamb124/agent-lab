"""Backfill personal namespaces для всех members всех компаний."""

from __future__ import annotations

from apps.idle.di import Di
from apps.idle.tasks.task_names import TASK_NAMESPACE_PERSONAL_BACKFILL
from core.context import clear_context, get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.namespace import ensure_personal_namespace_for_user
from core.tasks import platform_task

logger = get_logger(__name__)


@platform_task(TASK_NAMESPACE_PERSONAL_BACKFILL)
async def namespace_personal_backfill(company_id: str | None = None, *, di: Di) -> dict[str, int]:
    """Создаёт missing personal ns для members компании (все компании, если company_id нет)."""
    if company_id is not None:
        cleaned_company_id = company_id.strip()
        if cleaned_company_id == "":
            raise ValueError("company_id is required when provided")
        company = await Company.get(cleaned_company_id)
        if company is None:
            raise ValueError(f"Company not found: {cleaned_company_id}")
        companies = [company]
    else:
        companies = await Company.list(limit=10000)
    ensured = 0
    skipped = 0
    previous = get_context()
    try:
        for company in companies:
            for user_id in company.members:
                user = await User.get(user_id)
                if user is None:
                    skipped += 1
                    continue
                _ = set_context(
                    Context(
                        user=user.model_copy(
                            update={"active_company_id": company.company_id}
                        ),
                        host="backfill.local",
                        session_id="namespace-personal-backfill",
                        channel="taskiq",
                        language=Language.RU,
                        active_company=company,
                        user_companies=[company],
                        trace_id="namespace-personal-backfill",
                    )
                )
                await ensure_personal_namespace_for_user(
                    di.namespace_service,
                    user,
                    company=company,
                )
                ensured += 1
    finally:
        if previous is not None:
            _ = set_context(previous)
        else:
            clear_context()

    logger.info(
        "namespace.personal_backfill.done",
        ensured=ensured,
        skipped=skipped,
        companies=len(companies),
    )
    return {"ensured": ensured, "skipped": skipped, "companies": len(companies)}
