"""Живые тесты DEMO-терминала Т-Банка: Receipt, карты на форме банка, срывы.

Нет monkeypatch/mock HTTP. Банк на localhost webhook не доставит —
после CONFIRMED сверка через GetState/CheckOrder.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from httpx import AsyncClient, ConnectError, ConnectTimeout, HTTPError
from playwright.async_api import Page
from pydantic import ValidationError

from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.tinkoff_provider import (
    TINKOFF_CONFIRMED,
    TINKOFF_FAILED_STATUSES,
    TINKOFF_PENDING_STATUSES,
    TinkoffProvider,
)
from core.clients.payment.tinkoff_token import TINKOFF_ORDER_ID_MAX_LEN
from core.models.identity_models import Company, User
from core.models.payment_models import CreatePaymentRequest, PaymentStatus
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles
from tests.frontend.api.tinkoff_live import (
    DEMO_CARD_CANCEL,
    DEMO_CARD_RECEIPT,
    DEMO_CARD_REJECTED,
    DEMO_CARD_SUCCESS,
    DEMO_CVV,
    DEMO_EXPIRY,
    TINKOFF_LIVE_AMOUNT,
    TinkoffLiveCompany,
    create_billing_topup,
    current_status_after_wait,
    fill_tinkoff_card,
    make_tinkoff_payment_request,
    open_tinkoff_payment_form,
    pay_tinkoff_demo_card,
    poll_bank_status,
    require_external_payment_id,
    signed_tinkoff_notification,
    submit_tinkoff_payment_form,
    sync_company_payments,
    tinkoff_notification_url,
)

pytest_plugins = ("tests.frontend.api.tinkoff_live",)
pytestmark = [pytest.mark.network, pytest.mark.timeout(240)]

_CANCELLED_STATUSES = frozenset({"CANCELED", "CANCELLED", "REFUNDED", "REVERSED"})


async def _company_balance(frontend_di, company_id: str) -> float:
    company = await Company.get(company_id)
    assert company is not None
    return company.balance


class TestTinkoffLiveInit:
    async def test_init_with_receipt_returns_payment_url(
        self,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        unique_id: str,
    ) -> None:
        request = make_tinkoff_payment_request(
            transaction_id=f"{tinkoff_pay_company.company_id}:{unique_id}",
            amount=TINKOFF_LIVE_AMOUNT,
            customer_email=tinkoff_pay_company.email,
            provider=tinkoff_live_provider,
        )
        response = await tinkoff_live_provider.create_payment(request)
        assert response.payment_url.strip() != ""
        assert response.external_payment_id is not None
        assert response.external_payment_id.strip() != ""
        assert tinkoff_live_provider.config.taxation == "usn_income_outcome"
        assert tinkoff_live_provider.config.receipt_enabled is True

    async def test_init_without_email_raises_before_http(
        self,
        tinkoff_live_provider: TinkoffProvider,
        unique_id: str,
    ) -> None:
        request = make_tinkoff_payment_request(
            transaction_id=f"tf{unique_id}:{unique_id}",
            amount=TINKOFF_LIVE_AMOUNT,
            customer_email=None,
            provider=tinkoff_live_provider,
        )
        with pytest.raises(ValueError, match="customer_email"):
            await tinkoff_live_provider.create_payment(request)

    async def test_init_order_id_too_long_raises_before_http(
        self,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        request = make_tinkoff_payment_request(
            transaction_id="x" * (TINKOFF_ORDER_ID_MAX_LEN + 1),
            amount=TINKOFF_LIVE_AMOUNT,
            customer_email=tinkoff_pay_company.email,
            provider=tinkoff_live_provider,
        )
        with pytest.raises(ValueError, match="OrderId"):
            await tinkoff_live_provider.create_payment(request)

    async def test_init_wrong_password_raises_bank_error(
        self,
        tinkoff_wrong_password_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        unique_id: str,
    ) -> None:
        request = make_tinkoff_payment_request(
            transaction_id=f"{tinkoff_pay_company.company_id}:{unique_id}",
            amount=TINKOFF_LIVE_AMOUNT,
            customer_email=tinkoff_pay_company.email,
            provider=tinkoff_wrong_password_provider,
        )
        with pytest.raises(ValueError, match="ErrorCode"):
            await tinkoff_wrong_password_provider.create_payment(request)

    async def test_notification_url_is_public_webhook(
        self,
        tinkoff_live_provider: TinkoffProvider,
    ) -> None:
        notification_url = tinkoff_notification_url(tinkoff_live_provider)
        parsed = urlparse(notification_url)
        assert tinkoff_live_provider.registry_name == "tinkoff_main"
        assert parsed.scheme in ("http", "https")
        assert parsed.netloc != ""
        assert parsed.path == "/api/v1/payments/webhook/tinkoff_main"

    async def test_demo_terminal_key_contains_demo(
        self,
        tinkoff_live_provider: TinkoffProvider,
    ) -> None:
        assert "DEMO" in tinkoff_live_provider.config.terminal_key


class TestTinkoffLiveBillingGuards:
    async def test_topup_below_minimum_422(
        self,
        frontend_client: AsyncClient,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        with pytest.raises(ValidationError):
            CreatePaymentRequest(amount=50.0)
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers={"Authorization": f"Bearer {tinkoff_pay_company.token}"},
            json={"amount": 50.0},
        )
        assert response.status_code == 422

    async def test_topup_without_jwt_401(self, frontend_client: AsyncClient) -> None:
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            json={"amount": TINKOFF_LIVE_AMOUNT},
        )
        assert response.status_code == 401

    async def test_topup_viewer_403(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        unique_id: str,
    ) -> None:
        company_id = f"tfv{unique_id}"
        user_id = f"tfvu{unique_id}"
        company = Company(
            company_id=company_id,
            name=f"Tinkoff viewer {unique_id}",
            subdomain=company_id,
            owner_user_id=user_id,
            members={user_id: ["viewer"]},
            balance=0.0,
        )
        await Company.set(company)
        user = User(
            user_id=user_id,
            name=f"Tinkoff viewer {unique_id}",
            emails=[f"tfv{unique_id}@linnex.io"],
            companies={company_id: ["viewer"]},
            active_company_id=company_id,
        )
        await User.set(user)
        await set_test_company_member_roles(
            frontend_di.authz_service,
            company_id=company_id,
            user_id=user_id,
            roles=["viewer"],
        )
        token = get_token_service().create_token(user_id, company_id=company_id)
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": TINKOFF_LIVE_AMOUNT},
        )
        assert response.status_code == 403

    async def test_init_unreachable_api_url_raises(
        self,
        tinkoff_unreachable_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        unique_id: str,
        frontend_di,
    ) -> None:
        request = make_tinkoff_payment_request(
            transaction_id=f"{tinkoff_pay_company.company_id}:{unique_id}",
            amount=TINKOFF_LIVE_AMOUNT,
            customer_email=tinkoff_pay_company.email,
            provider=tinkoff_unreachable_provider,
        )
        with pytest.raises((ConnectError, ConnectTimeout, HTTPError, OSError)):
            await tinkoff_unreachable_provider.create_payment(request)
        missing = await frontend_di.payment_service.get_transaction(
            request.transaction_id
        )
        assert missing is None


class TestTinkoffLiveCards:
    async def test_card_4300_confirmed_checkorder_credits_once(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await pay_tinkoff_demo_card(
            tinkoff_payment_page,
            payment.payment_url,
            pan=DEMO_CARD_SUCCESS,
            provider=tinkoff_live_provider,
            payment_id=payment_id,
        )
        bank_status = await poll_bank_status(
            tinkoff_live_provider,
            payment_id,
            wanted=frozenset({TINKOFF_CONFIRMED}),
        )
        assert bank_status == TINKOFF_CONFIRMED
        stats = await sync_company_payments(
            frontend_di, tinkoff_pay_company.company_id
        )
        assert stats.updated == 1
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == TINKOFF_LIVE_AMOUNT
        second = await sync_company_payments(
            frontend_di, tinkoff_pay_company.company_id
        )
        assert second.updated == 0
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == TINKOFF_LIVE_AMOUNT
        txn = await frontend_di.payment_service.get_transaction(
            payment.transaction_id
        )
        assert txn is not None
        assert txn.status == PaymentStatus.SUCCESS
        assert txn.balance_applied is True

    async def test_card_test2_rejected_does_not_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await open_tinkoff_payment_form(tinkoff_payment_page, payment.payment_url)
        await fill_tinkoff_card(
            tinkoff_payment_page,
            pan=DEMO_CARD_REJECTED,
            expiry=DEMO_EXPIRY,
            cvv=DEMO_CVV,
        )
        await submit_tinkoff_payment_form(tinkoff_payment_page)
        status = await current_status_after_wait(
            tinkoff_live_provider, payment_id, timeout_sec=90.0
        )
        assert status != TINKOFF_CONFIRMED
        paid = tinkoff_payment_page.get_by_text("Оплачено")
        assert await paid.count() == 0
        assert "payment=success" not in tinkoff_payment_page.url
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_card_4000_test7_receipt_paid(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await pay_tinkoff_demo_card(
            tinkoff_payment_page,
            payment.payment_url,
            pan=DEMO_CARD_RECEIPT,
            provider=tinkoff_live_provider,
            payment_id=payment_id,
        )
        bank_status = await poll_bank_status(
            tinkoff_live_provider,
            payment_id,
            wanted=frozenset({TINKOFF_CONFIRMED}),
        )
        assert bank_status == TINKOFF_CONFIRMED
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == TINKOFF_LIVE_AMOUNT

    async def test_card_5000_cancel_after_confirm(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await pay_tinkoff_demo_card(
            tinkoff_payment_page,
            payment.payment_url,
            pan=DEMO_CARD_CANCEL,
            provider=tinkoff_live_provider,
            payment_id=payment_id,
        )
        await poll_bank_status(
            tinkoff_live_provider,
            payment_id,
            wanted=frozenset({TINKOFF_CONFIRMED}),
        )
        cancel_status = await tinkoff_live_provider.cancel_payment(
            payment_id,
            amount=payment.amount,
            customer_email=tinkoff_pay_company.email,
        )
        assert cancel_status in _CANCELLED_STATUSES
        after_cancel = await poll_bank_status(
            tinkoff_live_provider,
            payment_id,
            wanted=_CANCELLED_STATUSES,
        )
        assert after_cancel in _CANCELLED_STATUSES


class TestTinkoffLiveBreakage:
    async def test_close_after_payment_url_stays_pending(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await tinkoff_payment_page.goto(payment.payment_url, wait_until="load")
        await tinkoff_payment_page.close()
        status = await tinkoff_live_provider.check_payment_status(payment_id)
        assert status in TINKOFF_PENDING_STATUSES
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_open_form_without_card_does_not_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await open_tinkoff_payment_form(tinkoff_payment_page, payment.payment_url)
        await tinkoff_payment_page.close()
        status = await tinkoff_live_provider.check_payment_status(payment_id)
        assert status != TINKOFF_CONFIRMED
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_submit_then_close_does_not_guess(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await open_tinkoff_payment_form(tinkoff_payment_page, payment.payment_url)
        await fill_tinkoff_card(
            tinkoff_payment_page,
            pan=DEMO_CARD_SUCCESS,
            expiry=DEMO_EXPIRY,
            cvv=DEMO_CVV,
        )
        await submit_tinkoff_payment_form(tinkoff_payment_page)
        await tinkoff_payment_page.close()
        status = await current_status_after_wait(
            tinkoff_live_provider, payment_id, timeout_sec=90.0
        )
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        balance = await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        )
        if status == TINKOFF_CONFIRMED:
            assert balance == TINKOFF_LIVE_AMOUNT
        else:
            assert balance == 0.0

    async def test_fail_url_or_close_transaction_not_success(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        await tinkoff_payment_page.goto(payment.payment_url, wait_until="load")
        await tinkoff_payment_page.close()
        txn = await frontend_di.payment_service.get_transaction(
            payment.transaction_id
        )
        assert txn is not None
        assert txn.status != PaymentStatus.SUCCESS

    async def test_authorized_does_not_credit_until_confirmed(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        await pay_tinkoff_demo_card(
            tinkoff_payment_page,
            payment.payment_url,
            pan=DEMO_CARD_SUCCESS,
            provider=tinkoff_live_provider,
            payment_id=payment_id,
        )
        status = await tinkoff_live_provider.check_payment_status(payment_id)
        if status == "AUTHORIZED":
            await sync_company_payments(
                frontend_di, tinkoff_pay_company.company_id
            )
            assert await _company_balance(
                frontend_di, tinkoff_pay_company.company_id
            ) == 0.0
        await poll_bank_status(
            tinkoff_live_provider,
            payment_id,
            wanted=frozenset({TINKOFF_CONFIRMED}),
        )
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == TINKOFF_LIVE_AMOUNT

    async def test_two_topups_pay_only_one(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        tinkoff_payment_page: Page,
    ) -> None:
        first = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        second = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        first_payment_id = await require_external_payment_id(
            frontend_di, first.transaction_id
        )
        await pay_tinkoff_demo_card(
            tinkoff_payment_page,
            first.payment_url,
            pan=DEMO_CARD_SUCCESS,
            provider=tinkoff_live_provider,
            payment_id=first_payment_id,
        )
        await poll_bank_status(
            tinkoff_live_provider,
            first_payment_id,
            wanted=frozenset({TINKOFF_CONFIRMED}),
        )
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == TINKOFF_LIVE_AMOUNT
        unpaid = await frontend_di.payment_service.get_transaction(
            second.transaction_id
        )
        assert unpaid is not None
        assert unpaid.status == PaymentStatus.PENDING

    async def test_cancel_without_email_raises_before_http(
        self,
        tinkoff_live_provider: TinkoffProvider,
    ) -> None:
        with pytest.raises(ValueError, match="customer_email"):
            await tinkoff_live_provider.cancel_payment(
                "1",
                amount=TINKOFF_LIVE_AMOUNT,
                customer_email=None,
            )

    async def test_cancel_unknown_payment_id_raises(
        self,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        with pytest.raises((ValueError, HTTPError)):
            await tinkoff_live_provider.cancel_payment(
                "0",
                amount=TINKOFF_LIVE_AMOUNT,
                customer_email=tinkoff_pay_company.email,
            )

    async def test_cancel_new_payment_zero_balance(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        payment = await create_billing_topup(frontend_client, tinkoff_pay_company.token)
        payment_id = await require_external_payment_id(
            frontend_di, payment.transaction_id
        )
        cancel_status = await tinkoff_live_provider.cancel_payment(
            payment_id,
            amount=payment.amount,
            customer_email=tinkoff_pay_company.email,
        )
        assert cancel_status in (_CANCELLED_STATUSES | TINKOFF_FAILED_STATUSES)
        await sync_company_payments(frontend_di, tinkoff_pay_company.company_id)
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0


class TestTinkoffLiveWebhookContract:
    async def test_non_json_is_not_200_with_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code != 200
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_json_without_token_returns_ok_no_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        _ = tinkoff_live_provider
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            json={
                "TerminalKey": "x",
                "OrderId": f"{tinkoff_pay_company.company_id}:missing",
                "Success": True,
                "Status": "CONFIRMED",
                "PaymentId": "1",
                "ErrorCode": "0",
                "Amount": 10000,
            },
        )
        assert response.status_code == 200
        assert response.text == "OK"
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_wrong_token_returns_ok_no_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
    ) -> None:
        payload = signed_tinkoff_notification(
            tinkoff_live_provider,
            order_id=f"{tinkoff_pay_company.company_id}:wrongtok",
            payment_id="1",
            amount_kopecks=10000,
            status="CONFIRMED",
            token="0" * 64,
        )
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            json=payload,
        )
        assert response.status_code == 200
        assert response.text == "OK"
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_unknown_order_id_returns_ok_no_credit(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        tinkoff_live_provider: TinkoffProvider,
        tinkoff_pay_company: TinkoffLiveCompany,
        unique_id: str,
    ) -> None:
        payload = signed_tinkoff_notification(
            tinkoff_live_provider,
            order_id=f"{tinkoff_pay_company.company_id}:{unique_id}",
            payment_id="1",
            amount_kopecks=10000,
            status="CONFIRMED",
        )
        response = await frontend_client.post(
            "/api/v1/payments/webhook/tinkoff_main",
            json=payload,
        )
        assert response.status_code == 200
        assert response.text == "OK"
        assert await _company_balance(
            frontend_di, tinkoff_pay_company.company_id
        ) == 0.0

    async def test_unknown_provider_404(self, frontend_client: AsyncClient) -> None:
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/no_such_tinkoff_provider",
            json={"OrderId": "x:y"},
        )
        assert response.status_code == 404

    async def test_factory_default_is_live_provider(
        self,
        tinkoff_live_provider: TinkoffProvider,
    ) -> None:
        default_provider = PaymentProviderFactory.get_default_provider()
        assert default_provider is tinkoff_live_provider
