"""Контекст компании для execute_command (is_member через get_context)."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.websocket.manager import notification_manager


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _realtime_notification_manager() -> None:
    """Инициализирует notification_manager с реальным Redis для тестов call_handlers."""
    redis_url = os.environ.get("DATABASE__REDIS_URL", "redis://localhost:63792/0")
    await notification_manager.start_redis_listener(redis_url)
    yield
    await notification_manager.stop_redis_listener()


@pytest.fixture(autouse=True)
def _handler_company_context(company_id: str) -> None:
    company = Company(
        company_id=company_id,
        name="Test company",
        members={"u1": ["owner"], "member1": ["member"], "u_other": ["member"]},
    )
    user = User(
        user_id="u1",
        name="U1",
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    yield
    clear_context()
