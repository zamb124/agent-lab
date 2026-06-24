"""Общие helper'ы API worktracker: текущий actor и company."""

from __future__ import annotations

from core.context import require_active_company, require_context
from core.worktracker.models import UserActor


def current_company_id() -> str:
    return require_active_company().company_id


def current_user_actor() -> UserActor:
    return UserActor(user_id=require_context().user.user_id)


def current_user_id() -> str:
    return require_context().user.user_id
