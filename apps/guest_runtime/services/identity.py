"""Context scope для внутреннего API фермы (без AuthMiddleware)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus


@asynccontextmanager
async def guest_identity_scope(
    *,
    user: User,
    company: Company,
) -> AsyncGenerator[None, None]:
    if user.status != UserStatus.ACTIVE:
        raise ValueError(f"user is not active: {user.user_id}")
    token = set_context(
        Context(
            user=user,
            host="guest-runtime",
            channel="guest_runtime",
            active_company=company,
            user_companies=[company],
            active_namespace="default",
            metadata={"token_purpose": "guest_runtime"},
        )
    )
    try:
        yield
    finally:
        reset_context(token)
