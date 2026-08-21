"""Платежи Т-Банка без живого Init: Token, webhook-контракт, валидация API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.tinkoff_provider import (
    TinkoffProvider,
    _check_order_terminal_operations,
    _platform_status,
)
from core.clients.payment.tinkoff_token import compute_tinkoff_token
from core.config.models import PaymentProviderConfigEntry
from core.models.identity_models import Company
from core.models.payment_models import (
    CreatePaymentRequest,
    PaymentProviderType,
    PaymentStatus,
    PaymentSyncOperation,
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

    def test_transaction_accepts_stored_yoomoney(self) -> None:
        txn = Transaction.model_validate(
            {
                "transaction_id": "system:txn_legacy",
                "company_id": "system",
                "user_id": "user_1",
                "amount": 100.0,
                "status": "success",
                "payment_provider": "yoomoney",
            }
        )
        assert txn.payment_provider == PaymentProviderType.YOOMONEY

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


class TestTinkoffCheckOrderStatus:
    def test_rejected_becomes_failed_operation(self) -> None:
        ops = _check_order_terminal_operations(
            transaction_id="co1:abc123def456",
            payments=[{"PaymentId": "91", "Status": "REJECTED", "Amount": 10000}],
        )
        assert len(ops) == 1
        assert ops[0].status == PaymentStatus.FAILED
        assert ops[0].operation_id == "91"
        assert ops[0].amount == 100.0

    def test_refunded_becomes_refunded_operation(self) -> None:
        ops = _check_order_terminal_operations(
            transaction_id="co1:abc123def456",
            payments=[{"PaymentId": "92", "Status": "REFUNDED", "Amount": 10000}],
        )
        assert len(ops) == 1
        assert ops[0].status == PaymentStatus.REFUNDED
        assert ops[0].operation_id == "92"

    def test_new_does_not_emit_operation(self) -> None:
        ops = _check_order_terminal_operations(
            transaction_id="co1:abc123def456",
            payments=[{"PaymentId": "93", "Status": "NEW", "Amount": 10000}],
        )
        assert ops == []

    def test_confirmed_becomes_success_operation(self) -> None:
        ops = _check_order_terminal_operations(
            transaction_id="co1:abc123def456",
            payments=[{"PaymentId": "94", "Status": "CONFIRMED", "Amount": 10000}],
        )
        assert len(ops) == 1
        assert ops[0].status == PaymentStatus.SUCCESS
        assert _platform_status("CONFIRMED") == PaymentStatus.SUCCESS.value

    def test_skips_pending_then_takes_confirmed(self) -> None:
        ops = _check_order_terminal_operations(
            transaction_id="co1:abc123def456",
            payments=[
                {"PaymentId": "1", "Status": "NEW", "Amount": 10000},
                {"PaymentId": "2", "Status": "CONFIRMED", "Amount": 10000},
            ],
        )
        assert len(ops) == 1
        assert ops[0].operation_id == "2"
        assert ops[0].status == PaymentStatus.SUCCESS

    def test_unknown_bank_status_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown Tinkoff payment status"):
            _check_order_terminal_operations(
                transaction_id="co1:abc123def456",
                payments=[{"PaymentId": "95", "Status": "WEIRD", "Amount": 10000}],
            )


@pytest.mark.asyncio
class TestPaymentSyncApply:
    async def test_rejected_sync_does_not_credit_balance(
        self,
        frontend_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        cid = f"co_psync_{unique_id}"
        company = Company(
            company_id=cid,
            name=f"Payment sync {unique_id}",
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=10.0,
        )
        await frontend_container.company_repository.set(company)
        payment_service = frontend_container.payment_service
        txn_id = new_payment_transaction_id(cid)
        txn = Transaction(
            transaction_id=txn_id,
            company_id=cid,
            user_id=system_user_id,
            amount=100.0,
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType.TINKOFF,
        )
        await payment_service._save_transaction(txn)
        try:
            applied = await payment_service.apply_sync_operation(
                txn,
                PaymentSyncOperation(
                    transaction_id=txn_id,
                    status=PaymentStatus.FAILED,
                    operation_id="pay_rej",
                    amount=100.0,
                ),
            )
            assert applied is True
            stored = await payment_service.get_transaction(txn_id)
            assert stored is not None
            assert stored.status == PaymentStatus.FAILED
            assert stored.external_payment_id == "pay_rej"
            co = await frontend_container.company_repository.get(cid)
            assert co is not None
            assert co.balance == 10.0
        finally:
            await frontend_container.company_repository.delete(cid)

    async def test_refunded_sync_does_not_credit_balance(
        self,
        frontend_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        cid = f"co_prefund_{unique_id}"
        company = Company(
            company_id=cid,
            name=f"Payment refund {unique_id}",
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=10.0,
        )
        await frontend_container.company_repository.set(company)
        payment_service = frontend_container.payment_service
        txn_id = new_payment_transaction_id(cid)
        txn = Transaction(
            transaction_id=txn_id,
            company_id=cid,
            user_id=system_user_id,
            amount=100.0,
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType.TINKOFF,
        )
        await payment_service._save_transaction(txn)
        try:
            applied = await payment_service.apply_sync_operation(
                txn,
                PaymentSyncOperation(
                    transaction_id=txn_id,
                    status=PaymentStatus.REFUNDED,
                    operation_id="pay_rf",
                    amount=100.0,
                ),
            )
            assert applied is True
            stored = await payment_service.get_transaction(txn_id)
            assert stored is not None
            assert stored.status == PaymentStatus.REFUNDED
            co = await frontend_container.company_repository.get(cid)
            assert co is not None
            assert co.balance == 10.0
        finally:
            await frontend_container.company_repository.delete(cid)
