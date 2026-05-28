"""Типизированные контракты состояния FastAPI-приложения и запроса."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from fastapi import FastAPI, Request

from core.models.identity_models import Company
from core.utils.tokens import TokenData

if TYPE_CHECKING:
    from core.config import BaseSettings
    from core.container import BaseContainer
    from core.models.context_models import Context
    from core.models.identity_models import User


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
class CorrelationRequestState(TraceRequestState, Protocol):
    request_id: str


@runtime_checkable
class AuthRequestState(TraceRequestState, Protocol):
    context: Context
    user: User
    company: Company | None
    language: str
    user_companies: list[Company]
    token_data: TokenData | None


@runtime_checkable
class CompanyRequestState(Protocol):
    company: Company | None


@dataclass(frozen=True)
class RequestCorrelationIds:
    request_id: str
    trace_id: str


def get_request_correlation_ids(request: Request) -> RequestCorrelationIds | None:
    request_id = getattr(request.state, "request_id", None)
    trace_id = getattr(request.state, "trace_id", None)
    if not isinstance(request_id, str) or not request_id.strip():
        return None
    if not isinstance(trace_id, str) or not trace_id.strip():
        return None
    return RequestCorrelationIds(request_id=request_id, trace_id=trace_id)


def get_request_company_id(request: Request) -> str | None:
    company = getattr(request.state, "company", None)
    if company is None:
        return None
    if not isinstance(company, Company):
        raise RuntimeError("AuthMiddleware did not populate request.state.company")
    return company.company_id


def get_request_token_data(request: Request) -> TokenData | None:
    token_data = getattr(request.state, "token_data", None)
    if token_data is None:
        return None
    if not isinstance(token_data, TokenData):
        raise RuntimeError("AuthMiddleware did not populate request.state.token_data")
    return token_data


@runtime_checkable
class SessionTokenRequestState(Protocol):
    session_token_data: TokenData


@runtime_checkable
class SessionReissueRequestState(Protocol):
    reissue_auth_token: str
