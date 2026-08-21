"""Платежи Т-Банка без живого Init: Token, webhook-контракт, валидация API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.tinkoff_provider import TinkoffProvider
from core.clients.payment.tinkoff_token import compute_tinkoff_token
from core.config.models import PaymentProviderConfigEntry
from core.models.payment_models import (
    CreatePaymentRequest,
    PaymentProviderType,
    PaymentStatus,
    Transaction,
)
from core.payments.service import new_payment_transaction_id, payment_browser_return_url


def _require_configured_provider() -> TinkoffProvider:
    if not PaymentProviderFactory.get_available_providers():
        PaymentProviderFactory.initialize()
    provider = PaymentProviderFactory.get_default_provider()
    if provider is None:
        pytest.skip("платёжный провайдер Tinkoff не сконфигурирован")
    return provider


@pytest.mark.asyncio
class TestTinkoffWebhookHttp:
    async def test_invalid_token_returns_ok(
        self,
        frontend_client: AsyncClient,
        frontend_container,
    ) -> None:
        _ = frontend_container
        provider = _require_configured_provider()
        payload = {
            "TerminalKey": provider.config.terminal_key,
            "OrderId": "unknownco:deadbeef12",
            "Success": True,
            "Status": "CONFIRMED",
            "PaymentId": "1",
            "ErrorCode": "0",
            "Amount": 10000,
            "Token": "0" * 64,
        }
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            json=payload,
        )
        assert response.status_code == 200
        assert response.text == "OK"

    async def test_missing_token_returns_ok(self, frontend_client: AsyncClient, frontend_container) -> None:
        _ = frontend_container
        _ = _require_configured_provider()
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            json={
                "TerminalKey": "x",
                "OrderId": "unknownco:deadbeef12",
                "Success": True,
                "Status": "CONFIRMED",
                "PaymentId": "1",
                "ErrorCode": "0",
                "Amount": 10000,
            },
        )
        assert response.status_code == 200
        assert response.text == "OK"

    async def test_unknown_order_id_returns_ok(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id: str,
    ) -> None:
        _ = frontend_container
        provider = _require_configured_provider()
        payload = {
            "TerminalKey": provider.config.terminal_key,
            "OrderId": f"tf{unique_id}:{unique_id}",
            "Success": True,
            "Status": "CONFIRMED",
            "PaymentId": "1",
            "ErrorCode": "0",
            "Amount": 10000,
        }
        payload["Token"] = compute_tinkoff_token(payload, provider.config.password)
        response = await frontend_client.post(
            "/api/v1/payments/webhook/tinkoff_main",
            json=payload,
        )
        assert response.status_code == 200
        assert response.text == "OK"

    async def test_non_json_not_ok_credit(self, frontend_client: AsyncClient) -> None:
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/tinkoff_main",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code != 200

    async def test_unknown_provider_404(self, frontend_client: AsyncClient, frontend_container) -> None:
        _ = frontend_container
        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/no_such_tinkoff_provider",
            json={"OrderId": "x:y"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestBillingTopupGuards:
    async def test_topup_too_small_422(
        self,
        frontend_client: AsyncClient,
        auth_headers,
    ) -> None:
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 50.0},
        )
        assert response.status_code == 422

    async def test_topup_unauthorized(self, frontend_client: AsyncClient) -> None:
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            json={"amount": 100.0},
        )
        assert response.status_code == 401


class TestPaymentModels:
    def test_create_payment_request_min_amount(self) -> None:
        with pytest.raises(ValidationError):
            CreatePaymentRequest(amount=99.99)

    def test_create_payment_request_max_amount(self) -> None:
        with pytest.raises(ValidationError):
            CreatePaymentRequest(amount=1_000_001.0)

    def test_create_payment_request_valid(self) -> None:
        req = CreatePaymentRequest(amount=500.0)
        assert req.amount == 500.0

    def test_transaction_default_status_pending(self) -> None:
        txn = Transaction(
            transaction_id="test:txn_1",
            company_id="test",
            user_id="user_1",
            amount=100.0,
            payment_provider=PaymentProviderType.TINKOFF,
        )
        assert txn.status == PaymentStatus.PENDING
        assert txn.completed_at is None

    def test_new_payment_transaction_id_fits_tinkoff(self, unique_id: str) -> None:
        transaction_id = new_payment_transaction_id(f"co{unique_id}")
        assert ":" in transaction_id
        assert len(transaction_id) <= 50

    def test_return_url_follows_linnex_host(self) -> None:
        url = payment_browser_return_url(
            host="acme.linnex.io",
            company_subdomain="acme",
            payment_result="success",
            transaction_id="co1:abc123def456",
        )
        assert url == (
            "https://acme.linnex.io/billing?payment=success&transaction_id=co1:abc123def456"
        )

    def test_return_url_follows_humanitec_host(self) -> None:
        url = payment_browser_return_url(
            host="acme.humanitec.ru",
            company_subdomain="acme",
            payment_result="fail",
            transaction_id="co1:abc123def456",
        )
        assert url == (
            "https://acme.humanitec.ru/billing?payment=fail&transaction_id=co1:abc123def456"
        )

    def test_return_url_localhost_keeps_port(self) -> None:
        url = payment_browser_return_url(
            host="acme.localhost:8002",
            company_subdomain="acme",
            payment_result="success",
            transaction_id="co1:abc123def456",
        )
        assert url == (
            "http://acme.localhost:8002/billing?payment=success&transaction_id=co1:abc123def456"
        )

    def test_return_url_empty_host_raises(self) -> None:
        with pytest.raises(ValueError, match="host is required"):
            payment_browser_return_url(
                host="  ",
                company_subdomain="acme",
                payment_result="success",
                transaction_id="co1:abc123def456",
            )


class TestPaymentProviderFactory:
    def test_create_config_tinkoff(self) -> None:
        config_entry = PaymentProviderConfigEntry(
            provider_type="tinkoff",
            terminal_key="1787223840074DEMO",
            password="secret",
            api_url="https://securepay.tinkoff.ru/v2",
            receipt_enabled=True,
            taxation="usn_income_outcome",
        )
        config = PaymentProviderFactory._create_config_object(config_entry)
        assert config.terminal_key == "1787223840074DEMO"
        assert config.receipt_enabled is True

    def test_create_config_unknown_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            PaymentProviderConfigEntry.model_validate({"provider_type": "stripe"})

    def test_get_provider_returns_none_for_missing(self) -> None:
        assert PaymentProviderFactory.get_provider("unknown_tinkoff_name") is None
