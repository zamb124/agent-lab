"""Публичные endpoint'ы customer-auth — платформенный роутер.

Любой сервис монтирует одной строкой::

    router.include_router(customer_auth_router, prefix="/public")

и получает `/…/public/customer-auth/*`: start/method/verify/status/me/logout,
webhook'и ботов контактов и OAuth callbacks. Это протокольные хендлеры
(Set-Cookie, внешние webhooks, OAuth redirect) — не зеркала `op_*`, и
они анонимны: выдача customer-сессии — сам вход.

UI — общий web-компонент ``<platform-customer-auth>``
(`core/frontend/static/lib/components/platform-customer-auth.ts`), продукт
встраивает его
с ``api-base`` + ``company-id``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from core.customers.contracts import (
    AuthStartPayload,
    AuthStartView,
    AuthStatusView,
    AuthVerifyPayload,
    AuthVerifyView,
    CustomerMe,
    CustomerRef,
    MethodChallengedView,
    MethodChosenPayload,
)
from core.customers.enums import PhoneVerificationErrorCode, PhoneVerificationMethod
from core.customers.errors import CustomerAuthError
from core.di.platform import Di
from core.platform_brand.resolver import resolve_brand_domain
from core.request_scope import require_customer
from core.types import parse_json_object

customer_auth_router = APIRouter(prefix="/customer-auth", tags=["customer-auth"])

_HTTP_STATUS: dict[PhoneVerificationErrorCode, int] = {
    PhoneVerificationErrorCode.INVALID_PHONE: 400,
    PhoneVerificationErrorCode.CODE_INVALID: 400,
    PhoneVerificationErrorCode.NOT_DELIVERABLE: 422,
    PhoneVerificationErrorCode.PROVIDER_MISMATCH: 409,
    PhoneVerificationErrorCode.CHALLENGE_EXPIRED: 410,
    PhoneVerificationErrorCode.CODE_EXPIRED: 410,
    PhoneVerificationErrorCode.RATE_LIMITED: 429,
    PhoneVerificationErrorCode.ATTEMPTS_EXCEEDED: 429,
    PhoneVerificationErrorCode.SESSION_REQUIRED: 401,
    PhoneVerificationErrorCode.SESSION_INVALID: 401,
    PhoneVerificationErrorCode.FORBIDDEN_SCOPE: 403,
    PhoneVerificationErrorCode.PROVIDER_UNAVAILABLE: 503,
    PhoneVerificationErrorCode.PROVIDER_NOT_CONFIGURED: 503,
    PhoneVerificationErrorCode.INTERNAL_ERROR: 500,
}


def _http(exc: CustomerAuthError) -> HTTPException:
    status = _HTTP_STATUS.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.code.value)


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _apex(request: Request) -> str:
    try:
        return resolve_brand_domain(request.headers.get("host", ""))
    except ValueError:
        return "localhost"


@customer_auth_router.post("/start", response_model=AuthStartView)
async def customer_auth_start(
    payload: AuthStartPayload, request: Request, di: Di
) -> AuthStartView:
    """Старт попытки: компания — из payload (владелец витрины)."""
    try:
        return await di.customer_auth_service.start(
            company_id=payload.company_id,
            phone=payload.phone,
            client=payload.client,
            ip=_ip(request),
            apex=_apex(request),
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc


@customer_auth_router.post("/method", response_model=MethodChallengedView)
async def customer_auth_choose(
    payload: MethodChosenPayload, request: Request, di: Di
) -> MethodChallengedView:
    """Выбор способа: код отправляется каскадой, contact/OAuth — deep link."""
    try:
        return await di.customer_auth_service.choose(
            challenge_id=payload.challenge_id,
            method=payload.method,
            company_id=payload.company_id,
            ip=_ip(request),
            apex=_apex(request),
            return_url=payload.return_url,
            callback_base=str(request.url.path).rsplit("/", 1)[0],
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc


@customer_auth_router.post("/verify", response_model=AuthVerifyView)
async def customer_auth_verify(
    payload: AuthVerifyPayload, request: Request, response: Response, di: Di
) -> AuthVerifyView:
    """Код или direct-доказательство → customer + `customer_token` cookie."""
    try:
        if payload.code is not None:
            customer, token = await di.customer_auth_service.verify_code(
                challenge_id=payload.challenge_id,
                code=payload.code,
                company_id=payload.company_id,
            )
        elif payload.direct is not None:
            customer, token = await di.customer_auth_service.verify_direct(
                challenge_id=payload.challenge_id,
                proof=payload.direct,
                company_id=payload.company_id,
            )
        else:
            raise HTTPException(status_code=400, detail="code_or_direct_required")
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    di.customer_session_service.attach_cookie(
        response, request, token, ttl_seconds=di.customer_session_service.token_ttl()
    )
    return AuthVerifyView(
        status="confirmed",
        customer=CustomerMe(
            customer_id=customer.customer_id,
            phone_e164=customer.phone_e164,
            scope_company_id=payload.company_id,
            name=customer.name,
        ),
    )


@customer_auth_router.get("/status", response_model=AuthStatusView)
async def customer_auth_status(
    challenge_id: str,
    company_id: str,
    request: Request,
    response: Response,
    di: Di,
) -> AuthStatusView:
    """Polling direct/OAuth потоков: при confirmed дополнительно Set-Cookie."""
    try:
        view, token = await di.customer_auth_service.status(
            challenge_id, company_id=company_id
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    if token is not None:
        di.customer_session_service.attach_cookie(
            response, request, token, ttl_seconds=di.customer_session_service.token_ttl()
        )
    return view


@customer_auth_router.get("/me", response_model=CustomerMe)
async def customer_me(di: Di) -> CustomerMe:
    """Текущий покупатель по `customer_token` cookie; 401 без сессии."""
    scope = require_customer()
    me = await di.customer_service.to_me(
        CustomerRef(
            customer_id=scope.customer_id,
            phone_e164=scope.phone_e164,
            scope_company_id=scope.company_id,
        )
    )
    if me is None:
        raise HTTPException(status_code=401, detail="session_invalid")
    return me


@customer_auth_router.post("/logout", response_model=None)
async def customer_logout(request: Request, di: Di) -> Response:
    resp = Response(status_code=200)
    di.customer_session_service.clear_cookie(resp, request)
    return resp


@customer_auth_router.post("/webhooks/{provider}", response_model=None)
async def customer_auth_webhook(provider: str, request: Request, di: Di) -> Response:
    """Webhook ботов контактов (Telegram/MAX): /start → кнопка, contact → confirm."""
    apex = _apex(request)
    registry = di.customer_auth_service.registry_for(apex)
    verifier = None
    for candidate in registry.contact_share.values():
        if candidate.provider.value == provider:
            verifier = candidate
            break
    if verifier is None:
        raise HTTPException(status_code=404, detail="provider_not_configured")
    secret_header = request.headers.get("x-telegram-bot-api-secret-token") or (
        request.headers.get("x-max-bot-api-secret")
    )
    try:
        verifier.verify_secret(secret_header)
        payload = parse_json_object(await request.body(), "customer_auth.webhook")
        await di.customer_auth_service.handle_contact_update(
            provider=verifier, payload=payload
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return Response(status_code=200)


def _oauth_method(provider_slug: str) -> PhoneVerificationMethod | None:
    """Slug из callback URL → метод: `yandex_id` ↔ `yandex`."""
    for method in PhoneVerificationMethod:
        if method.value.endswith("_id") and method.value.removesuffix("_id") == provider_slug:
            return method
    return None


@customer_auth_router.get("/oauth/{provider}/callback", response_model=None)
async def customer_auth_oauth_callback(
    provider: str,
    request: Request,
    di: Di,
    code: str = "",
    state: str = "",
    device_id: str = "",
) -> Response:
    """OAuth-redirect: `code`+`state` → подтверждение → Set-Cookie → return_url."""
    method = _oauth_method(provider)
    if method is None or not code or not state:
        raise HTTPException(status_code=400, detail="oauth_params_required")
    apex = _apex(request)
    try:
        _customer, token, return_url = await di.customer_auth_service.complete_oauth(
            method=method,
            code=code,
            state=state,
            apex=apex,
            device_id=device_id,
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    redirect = RedirectResponse(url=return_url or f"https://{apex}/", status_code=302)
    di.customer_session_service.attach_cookie(
        redirect, request, token, ttl_seconds=di.customer_session_service.token_ttl()
    )
    return redirect


__all__ = ["customer_auth_router"]
