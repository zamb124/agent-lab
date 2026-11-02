"""CustomerSessionService — сессия покупателя витрины.

JWT `TokenType.CUSTOMER` + httpOnly cookie `customer_token` на apex-домене
бренда. Сессия не даёт никаких прав платформенного пользователя: scope
покупателя — `scope_company_id` витрины, проверяется в `require_customer`.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request, Response

from core.config import get_settings
from core.customers.ref import CustomerRef
from core.utils.domain import get_cookie_domain
from core.utils.tokens import TokenService, TokenType, get_token_service

CUSTOMER_COOKIE = "customer_token"


class CustomerSessionService:
    """Выпуск и чтение customer-сессий (JWT + cookie)."""

    def issue(
        self,
        *,
        customer_id: str,
        phone_e164: str,
        scope_company_id: str,
        ttl_seconds: int,
    ) -> str:
        session_id = f"csess_{uuid4().hex}"
        return get_token_service().create_customer_token(
            customer_id=customer_id,
            phone_e164=phone_e164,
            scope_company_id=scope_company_id,
            session_id=session_id,
            expires_in=ttl_seconds,
        )

    def resolve_cookie(self, request: Request) -> CustomerRef | None:
        """`customer_token` cookie → CustomerRef; невалидный/чужой тип — None."""
        token = request.cookies.get(CUSTOMER_COOKIE)
        if not token:
            return None
        data = get_token_service().validate_token(token)
        if data is None or data.token_type != TokenType.CUSTOMER:
            return None
        customer_id = data.metadata.get("customer_id")
        phone = data.metadata.get("phone_e164")
        scope = data.metadata.get("scope_company_id")
        if not all(isinstance(v, str) and v for v in (customer_id, phone, scope)):
            return None
        return CustomerRef(
            customer_id=str(customer_id),
            phone_e164=str(phone),
            scope_company_id=str(scope),
        )

    def attach_cookie(
        self, response: Response, request: Request, token: str, *, ttl_seconds: int
    ) -> None:
        if not token or not str(token).strip():
            raise ValueError("attach_cookie: token required")
        settings = get_settings()
        response.set_cookie(
            key=CUSTOMER_COOKIE,
            value=token,
            domain=get_cookie_domain(request.headers.get("host", "")),
            httponly=True,
            secure=settings.server.env == "production",
            samesite="lax",
            max_age=ttl_seconds,
            path="/",
        )

    def clear_cookie(self, response: Response, request: Request) -> None:
        response.delete_cookie(
            key=CUSTOMER_COOKIE,
            domain=get_cookie_domain(request.headers.get("host", "")),
            path="/",
        )

    def token_ttl(self) -> int:
        return get_settings().customer_auth.session_ttl_seconds or TokenService.CUSTOMER_EXPIRES
