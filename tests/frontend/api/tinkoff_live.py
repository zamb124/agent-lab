"""Фикстуры и хелперы живой DEMO-сюиты Т-Банка (без моков HTTP)."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import AsyncClient
from playwright.async_api import Locator, Page, async_playwright

from apps.frontend.container import FrontendContainer
from core.clients.payment.base_provider import PaymentRequest
from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.tinkoff_provider import (
    TINKOFF_CONFIRMED,
    TINKOFF_FAILED_STATUSES,
    TINKOFF_REFUNDED_STATUSES,
    TinkoffProvider,
)
from core.clients.payment.tinkoff_token import TINKOFF_ORDER_ID_MAX_LEN, compute_tinkoff_token
from core.models.identity_models import Company, User
from core.models.payment_models import CreatePaymentResponse, PaymentSyncStats
from core.payments.sync_service import PaymentSyncService
from core.short_links.service import require_platform_public_base_url
from core.types import JsonObject
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles

TINKOFF_LIVE_AMOUNT = 100.0
DEMO_CARD_SUCCESS = "4300000000000777"
DEMO_CARD_REJECTED = "5000000000000009"
DEMO_CARD_RECEIPT = "4000000000000101"
DEMO_CARD_CANCEL = "5000000000000108"
DEMO_EXPIRY = "12/30"
DEMO_CVV = "111"
_PLACEHOLDER_PREFIX = "YOUR_"
_CARD_NUMBER_SELECTOR = (
    '[automation-id="tui-input-card-group__card"], '
    'input[autocomplete="cc-number"], input[name="cardNumber"], input[name="pan"], '
    'input[name="CardNumber"], input#pan, input#cardNumber'
)
_EXPIRY_SELECTOR = (
    '[automation-id="tui-input-card-group__expire"], input[name="ccexpiryyear"], '
    'input[autocomplete="cc-exp"], input[name="expDate"], input[name="expiry"], '
    'input[name="ExpDate"], input#expDate, input#expiry'
)
_CVV_SELECTOR = (
    '[automation-id="tui-input-card-group__cvc"], '
    'input[autocomplete="cc-csc"], input[name="cvv"], input[name="cvc"], '
    'input[name="CVV"], input#cvv, input#cvc'
)
_POLL_INTERVAL_SEC = 1.5
_GET_STATE_TIMEOUT_SEC = 90.0
_FORM_GOTO_TIMEOUT_MS = 60_000
_FORM_PAID_TIMEOUT_SEC = 90.0


@dataclass(frozen=True, slots=True)
class TinkoffLiveCompany:
    company_id: str
    user_id: str
    email: str
    token: str


def tinkoff_notification_url(provider: TinkoffProvider) -> str:
    public_base = require_platform_public_base_url()
    return f"{public_base}/api/v1/payments/webhook/{provider.registry_name}"


def require_tinkoff_live_provider() -> TinkoffProvider:
    if not PaymentProviderFactory.get_available_providers():
        PaymentProviderFactory.initialize()
    provider = PaymentProviderFactory.get_default_provider()
    if provider is None:
        pytest.skip("платёжный провайдер Tinkoff не сконфигурирован")
    terminal_key = provider.config.terminal_key.strip()
    password = provider.config.password.strip()
    if terminal_key.startswith(_PLACEHOLDER_PREFIX) or password.startswith(_PLACEHOLDER_PREFIX):
        pytest.skip("Tinkoff DEMO credentials are placeholders")
    if "DEMO" not in terminal_key:
        pytest.fail(f"Tinkoff live terminal_key must contain DEMO, got {terminal_key!r}")
    if not provider.config.receipt_enabled:
        pytest.fail("Tinkoff live suite requires receipt_enabled=true for Receipt / Test 7")
    return provider


def make_tinkoff_payment_request(
    *,
    transaction_id: str,
    amount: float,
    customer_email: str | None,
    provider: TinkoffProvider,
) -> PaymentRequest:
    if transaction_id.strip() == "":
        raise ValueError("transaction_id is required")
    company_id = transaction_id.split(":", 1)[0]
    return PaymentRequest(
        amount=amount,
        company_id=company_id,
        user_id="tinkoff-live",
        transaction_id=transaction_id,
        success_url="https://example.com/billing?payment=success",
        fail_url="https://example.com/billing?payment=fail",
        notification_url=tinkoff_notification_url(provider),
        customer_email=customer_email,
        language="ru",
    )


def signed_tinkoff_notification(
    provider: TinkoffProvider,
    *,
    order_id: str,
    payment_id: str,
    amount_kopecks: int,
    status: str,
    token: str | None = None,
) -> JsonObject:
    payload: JsonObject = {
        "TerminalKey": provider.config.terminal_key,
        "OrderId": order_id,
        "Success": True,
        "Status": status,
        "PaymentId": payment_id,
        "ErrorCode": "0",
        "Amount": amount_kopecks,
    }
    if token is None:
        payload["Token"] = compute_tinkoff_token(payload, provider.config.password)
    else:
        payload["Token"] = token
    return payload


async def poll_bank_status(
    provider: TinkoffProvider,
    payment_id: str,
    *,
    wanted: frozenset[str],
    timeout_sec: float = _GET_STATE_TIMEOUT_SEC,
) -> str:
    clean_payment_id = payment_id.strip()
    if clean_payment_id == "":
        raise ValueError("payment_id is required")
    if not wanted:
        raise ValueError("wanted statuses must not be empty")

    async def _loop() -> str:
        while True:
            status = await provider.check_payment_status(clean_payment_id)
            if status in wanted:
                return status
            await asyncio.sleep(_POLL_INTERVAL_SEC)

    return await asyncio.wait_for(_loop(), timeout=timeout_sec)


async def create_billing_topup(
    frontend_client: AsyncClient,
    token: str,
    amount: float = TINKOFF_LIVE_AMOUNT,
) -> CreatePaymentResponse:
    if token.strip() == "":
        raise ValueError("token is required")
    response = await frontend_client.post(
        "/frontend/api/billing/topup",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": amount},
    )
    if response.status_code != 200:
        raise AssertionError(
            f"topup failed: status={response.status_code} body={response.text}"
        )
    return CreatePaymentResponse.model_validate(response.json())


async def require_external_payment_id(
    frontend_container: FrontendContainer,
    transaction_id: str,
) -> str:
    transaction = await frontend_container.payment_service.get_transaction(transaction_id)
    if transaction is None:
        raise AssertionError(f"transaction not found: {transaction_id}")
    if transaction.external_payment_id is None or transaction.external_payment_id.strip() == "":
        raise AssertionError(f"transaction missing external_payment_id: {transaction_id}")
    return transaction.external_payment_id


async def sync_company_payments(
    frontend_container: FrontendContainer,
    company_id: str,
) -> PaymentSyncStats:
    sync_service = PaymentSyncService(
        payment_service=frontend_container.payment_service,
        storage=frontend_container.shared_storage,
    )
    return await sync_service.sync_pending_transactions(company_id)


async def resolve_tinkoff_form_locator(page: Page, selector: str) -> Locator:
    async def _find() -> Locator | None:
        page_locator = page.locator(selector)
        if await page_locator.count() > 0:
            return page_locator.first
        iframe_count = await page.locator("iframe").count()
        for index in range(iframe_count):
            frame_locator = page.frame_locator("iframe").nth(index).locator(selector)
            if await frame_locator.count() > 0:
                return frame_locator.first
        return None

    async def _loop() -> Locator:
        while True:
            found = await _find()
            if found is not None:
                return found
            await asyncio.sleep(0.3)

    try:
        return await asyncio.wait_for(_loop(), timeout=25)
    except TimeoutError as exc:
        body = await page.inner_text("body")
        raise AssertionError(
            "Tinkoff payment form field not found: "
            + f"selector={selector!r} url={page.url} text={body[:1500]}"
        ) from exc


async def current_status_after_wait(
    provider: TinkoffProvider,
    payment_id: str,
    *,
    timeout_sec: float,
) -> str:
    terminal = frozenset({TINKOFF_CONFIRMED}) | TINKOFF_FAILED_STATUSES | TINKOFF_REFUNDED_STATUSES

    async def _loop() -> str:
        while True:
            status = await provider.check_payment_status(payment_id)
            if status in terminal:
                return status
            await asyncio.sleep(_POLL_INTERVAL_SEC)

    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_sec)
    except TimeoutError:
        return await provider.check_payment_status(payment_id)


async def open_tinkoff_payment_form(page: Page, payment_url: str) -> None:
    if payment_url.strip() == "":
        raise ValueError("payment_url is required")
    await page.goto(payment_url, wait_until="load", timeout=_FORM_GOTO_TIMEOUT_MS)
    await page.wait_for_selector("input, button, iframe", timeout=30_000)


async def _type_tinkoff_field(field: Locator, value: str) -> None:
    # TUI card-group после PAN сдвигает CVC поверх expiry — click перехватывается.
    await field.focus()
    await field.fill("")
    await field.press_sequentially(value, delay=40)


async def fill_tinkoff_card(
    page: Page,
    *,
    pan: str,
    expiry: str,
    cvv: str,
) -> None:
    if pan.strip() == "" or expiry.strip() == "" or cvv.strip() == "":
        raise ValueError("pan, expiry and cvv are required")
    card_number = await resolve_tinkoff_form_locator(page, _CARD_NUMBER_SELECTOR)
    await _type_tinkoff_field(card_number, pan)
    expiry_field = await resolve_tinkoff_form_locator(page, _EXPIRY_SELECTOR)
    await _type_tinkoff_field(expiry_field, expiry)
    cvv_field = await resolve_tinkoff_form_locator(page, _CVV_SELECTOR)
    await _type_tinkoff_field(cvv_field, cvv)


async def submit_tinkoff_payment_form(page: Page) -> None:
    pay_button = page.get_by_role("button", name=re.compile(r"Оплатить|Pay"))
    if await pay_button.count() == 0:
        iframe_count = await page.locator("iframe").count()
        for index in range(iframe_count):
            frame_button = page.frame_locator("iframe").nth(index).get_by_role(
                "button", name=re.compile(r"Оплатить|Pay")
            )
            if await frame_button.count() > 0:
                await frame_button.first.click()
                return
        body = await page.inner_text("body")
        raise AssertionError(
            "Tinkoff pay button not found. "
            + f"url={page.url} text={body[:1500]}"
        )
    await pay_button.first.click()


async def wait_tinkoff_form_paid(
    page: Page,
    provider: TinkoffProvider,
    payment_id: str,
) -> None:
    clean_payment_id = payment_id.strip()
    if clean_payment_id == "":
        raise ValueError("payment_id is required")

    async def _loop() -> None:
        while True:
            if "payment=fail" in page.url:
                body = await page.inner_text("body")
                raise AssertionError(
                    "Tinkoff payment form redirected to FailURL. "
                    + f"url={page.url} text={body[:1500]}"
                )
            if "payment=success" in page.url:
                return
            paid = page.get_by_text("Оплачено")
            if await paid.count() > 0:
                return
            status = await provider.check_payment_status(clean_payment_id)
            if status == TINKOFF_CONFIRMED:
                return
            if status in TINKOFF_FAILED_STATUSES | TINKOFF_REFUNDED_STATUSES:
                body = await page.inner_text("body")
                raise AssertionError(
                    f"Tinkoff payment ended with {status}. "
                    + f"url={page.url} text={body[:1500]}"
                )
            await asyncio.sleep(_POLL_INTERVAL_SEC)

    try:
        await asyncio.wait_for(_loop(), timeout=_FORM_PAID_TIMEOUT_SEC)
    except TimeoutError as exc:
        status = await provider.check_payment_status(clean_payment_id)
        body = await page.inner_text("body")
        raise AssertionError(
            "Tinkoff payment was not CONFIRMED. "
            + f"status={status} url={page.url} text={body[:1500]}"
        ) from exc


async def pay_tinkoff_demo_card(
    page: Page,
    payment_url: str,
    *,
    pan: str,
    provider: TinkoffProvider,
    payment_id: str,
    expiry: str = DEMO_EXPIRY,
    cvv: str = DEMO_CVV,
) -> None:
    await open_tinkoff_payment_form(page, payment_url)
    await fill_tinkoff_card(page, pan=pan, expiry=expiry, cvv=cvv)
    await submit_tinkoff_payment_form(page)
    await wait_tinkoff_form_paid(page, provider, payment_id)


@pytest.fixture
def tinkoff_live_provider(frontend_container: FrontendContainer) -> TinkoffProvider:
    _ = frontend_container
    return require_tinkoff_live_provider()


@pytest.fixture
def tinkoff_wrong_password_provider(tinkoff_live_provider: TinkoffProvider) -> TinkoffProvider:
    config = tinkoff_live_provider.config.model_copy(
        update={"password": "definitely-wrong-tinkoff-password"}
    )
    return TinkoffProvider(config)


@pytest.fixture
def tinkoff_unreachable_provider(tinkoff_live_provider: TinkoffProvider) -> TinkoffProvider:
    config = tinkoff_live_provider.config.model_copy(
        update={"api_url": "https://tinkoff-live-test.invalid/v2"}
    )
    return TinkoffProvider(config)


@pytest_asyncio.fixture
async def tinkoff_pay_company(
    frontend_container: FrontendContainer,
    unique_id: str,
) -> TinkoffLiveCompany:
    company_id = f"tf{unique_id}"
    if len(company_id) + 1 + 8 > TINKOFF_ORDER_ID_MAX_LEN:
        raise ValueError(f"company_id too long for Tinkoff OrderId: {company_id}")
    user_id = f"tfu{unique_id}"
    email = f"tf{unique_id}@linnex.io"
    company = Company(
        company_id=company_id,
        name=f"Tinkoff live {unique_id}",
        subdomain=company_id,
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
        balance=0.0,
    )
    await frontend_container.company_repository.set(company)
    user = User(
        user_id=user_id,
        name=f"Tinkoff live {unique_id}",
        emails=[email],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    await set_test_company_member_roles(
        frontend_container.company_repository,
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["owner", "admin"],
    )
    token = get_token_service().create_token(user_id, company_id=company_id)
    return TinkoffLiveCompany(
        company_id=company_id,
        user_id=user_id,
        email=email,
        token=token,
    )


@pytest_asyncio.fixture
async def tinkoff_payment_page() -> Page:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        # Chromium не содержит НУЦ Минцифры; extra server-CA в Playwright нет
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        yield page
        await browser.close()
