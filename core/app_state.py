"""Typed contracts for FastAPI application and request state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from fastapi import FastAPI, Request

if TYPE_CHECKING:
    from core.config import BaseSettings
    from core.container import BaseContainer
    from core.models.context_models import Context
    from core.models.identity_models import Company, User
    from core.utils.tokens import TokenData


@runtime_checkable
class PlatformAppState(Protocol):
    container: BaseContainer
    settings: BaseSettings


def require_platform_app_state(request: Request) -> PlatformAppState:
    app = cast(FastAPI, request.app)
    if not hasattr(app.state, "container") or not hasattr(app.state, "settings"):
        raise RuntimeError("Platform app state is not configured")
    return cast(PlatformAppState, cast(object, app.state))


@runtime_checkable
class TraceRequestState(Protocol):
    trace_id: str


@runtime_checkable
class AuthRequestState(TraceRequestState, Protocol):
    context: Context
    user: User
    company: Company | None
    language: str
    user_companies: list[Company]
    token_data: TokenData | None


@runtime_checkable
class SessionTokenRequestState(Protocol):
    session_token_data: TokenData


@runtime_checkable
class SessionReissueRequestState(Protocol):
    reissue_auth_token: str
