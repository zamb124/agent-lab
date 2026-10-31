"""Платежи Т-Банка без живого Init: Token, webhook-контракт, валидация API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx2 import AsyncClient
from pydantic import ValidationError

from core.clients.payment.base_provider import PaymentRequest, PaymentResponse
from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.tinkoff_provider import (
    TinkoffProvider,
    _check_order_terminal_operations,
    _platform_status,
)
from core.clients.payment.tinkoff_token import compute_tinkoff_token
from core.config import get_settings
from core.config.models import PaymentProviderConfigEntry, PaymentProvidersConfig, ServerConfig
from core.db.storage import Storage
from core.models.identity_models import Company
from core.models.payment_models import (
    CreatePaymentRequest,
    PaymentProviderType,
    PaymentStatus,
    PaymentSyncCandidate,
    PaymentSyncOperation,
    Transaction,
)
from core.payments.service import new_payment_transaction_id, payment_browser_return_url
from core.payments.sync_service import PaymentSyncService
from core.short_links.service import require_platform_public_base_url
from tests.fixtures.auth import set_test_company_member_roles


def _require_configured_provider() -> TinkoffProvider:
    if not PaymentProviderFactory.get_available_providers():
        PaymentProviderFactory.initialize()
    provider = PaymentProviderFactory.get_default_provider()
    if provider is None:
        pytest.skip("платёжный провайдер Tinkoff не сконфигурирован")
    return provider


async def _seed_billing_company(
    frontend_di,
    *,
    company_id: str,
    name: str,
    owner_user_id: str,
    balance: float,
) -> None:
    company = Company(
        company_id=company_id,
        name=name,
        owner_user_id=owner_user_id,
        balance=balance,
    )
    await Company.set(company)
    await set_test_company_member_roles(
        frontend_di.authz_service,
        company_id=company_id,
        user_id=owner_user_id,
        roles=["owner"],
    )


async def _delete_company_payments(storage: Storage, company_id: str) -> None:
    keys = await storage.list_by_prefix(f"payment:{company_id}:", limit=500, force_global=True)
    for key in keys:
        deleted = await storage.delete(key, force_global=True)
        if not deleted:
            raise AssertionError(f"failed to delete payment key {key}")


@pytest.mark.asyncio
class TestTinkoffWebhookHttp:
    async def test_invalid_token_returns_ok(
        self,
        frontend_client: AsyncClient,
        frontend_di,
    ) -> None:
        _ = frontend_di
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

    async def test_missing_token_returns_ok(
        self, frontend_client: AsyncClient, frontend_di
    ) -> None:
        _ = frontend_di
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
        frontend_di,
        unique_id: str,
    ) -> None:
        _ = frontend_di
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

    async def test_unknown_provider_404(
        self, frontend_client: AsyncClient, frontend_di
    ) -> None:
        _ = frontend_di
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

    def test_return_url_follows_linnex_host_fail(self) -> None:
        url = payment_browser_return_url(
            host="acme.linnex.io",
            company_subdomain="acme",
            payment_result="fail",
            transaction_id="co1:abc123def456",
        )
        assert url == (
            "https://acme.linnex.io/billing?payment=fail&transaction_id=co1:abc123def456"
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
        frontend_di,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        cid = f"co_psync_{unique_id}"
        await _seed_billing_company(
            frontend_di,
            company_id=cid,
            name=f"Payment sync {unique_id}",
            owner_user_id=system_user_id,
            balance=10.0,
        )
        payment_service = frontend_di.payment_service
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
            co = await Company.get(cid)
            assert co is not None
            assert co.balance == 10.0
        finally:
            await Company.delete_by_id(cid)

    async def test_refunded_sync_does_not_credit_balance(
        self,
        frontend_di,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        cid = f"co_prefund_{unique_id}"
        await _seed_billing_company(
            frontend_di,
            company_id=cid,
            name=f"Payment refund {unique_id}",
            owner_user_id=system_user_id,
            balance=10.0,
        )
        payment_service = frontend_di.payment_service
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
            co = await Company.get(cid)
            assert co is not None
            assert co.balance == 10.0
        finally:
            await Company.delete_by_id(cid)


class TestPlatformPublicBaseUrl:
    def test_pydantic_default_is_linnex(self) -> None:
        default = ServerConfig.model_fields["platform_public_base_url"].default
        assert default == "https://linnex.io"

    def test_sync_window_defaults(self) -> None:
        cfg = PaymentProvidersConfig()
        assert cfg.sync_pending_max_age_hours == 24
        assert cfg.sync_check_order_limit == 50


@pytest.mark.asyncio
class TestTinkoffInitNotificationUrl:
    async def test_topup_uses_platform_public_base(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _ = frontend_di
        provider = _require_configured_provider()
        captured: list[PaymentRequest] = []

        async def fake_create_payment(
            self: TinkoffProvider,
            request: PaymentRequest,
        ) -> PaymentResponse:
            _ = self
            captured.append(request)
            return PaymentResponse(
                payment_url="https://pay.tbank.ru/test-init",
                external_payment_id="init-test-1",
            )

        monkeypatch.setattr(TinkoffProvider, "create_payment", fake_create_payment)
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 100.0},
        )
        assert response.status_code == 200, response.text
        assert len(captured) == 1
        public_base = require_platform_public_base_url()
        assert captured[0].notification_url == (
            f"{public_base}/api/v1/payments/webhook/{provider.registry_name}"
        )
        payload = response.json()
        transaction_id = payload["transaction_id"]
        stored = await frontend_di.payment_service.get_transaction(transaction_id)
        assert stored is not None
        deleted = await frontend_di.shared_storage.delete(
            f"payment:{stored.company_id}:{stored.payment_provider.value}:{stored.transaction_id}",
            force_global=True,
        )
        if not deleted:
            raise AssertionError("failed to delete topup test transaction")


@pytest.mark.asyncio
class TestTinkoffWebhookCredits:
    async def test_confirmed_credits_without_sync(
        self,
        frontend_client: AsyncClient,
        frontend_di,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        provider = _require_configured_provider()
        cid = f"co_wh_{unique_id}"
        await _seed_billing_company(
            frontend_di,
            company_id=cid,
            name=f"Webhook credit {unique_id}",
            owner_user_id=system_user_id,
            balance=10.0,
        )
        payment_service = frontend_di.payment_service
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
        payment_id = f"pay{unique_id[:12]}"
        payload = {
            "TerminalKey": provider.config.terminal_key,
            "OrderId": txn_id,
            "Success": True,
            "Status": "CONFIRMED",
            "PaymentId": payment_id,
            "ErrorCode": "0",
            "Amount": 10000,
        }
        payload["Token"] = compute_tinkoff_token(payload, provider.config.password)
        try:
            response = await frontend_client.post(
                "/frontend/api/v1/payments/webhook/tinkoff_main",
                json=payload,
            )
            assert response.status_code == 200
            assert response.text == "OK"
            stored = await payment_service.get_transaction(txn_id)
            assert stored is not None
            assert stored.status == PaymentStatus.SUCCESS
            assert stored.balance_applied is True
            co = await Company.get(cid)
            assert co is not None
            assert co.balance == 110.0
        finally:
            _ = await frontend_di.shared_storage.delete(
                f"payment_external:{PaymentProviderType.TINKOFF.value}:{payment_id}",
                force_global=True,
            )
            await _delete_company_payments(frontend_di.shared_storage, cid)
            await Company.delete_by_id(cid)


@pytest.mark.asyncio
class TestPaymentSyncPendingOnly:
    async def test_success_rows_do_not_call_check_order(
        self,
        frontend_di,
        unique_id: str,
        system_user_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _ = _require_configured_provider()
        cid = f"co_ok_{unique_id}"
        await _seed_billing_company(
            frontend_di,
            company_id=cid,
            name=f"Payment success flood {unique_id}",
            owner_user_id=system_user_id,
            balance=0.0,
        )
        payment_service = frontend_di.payment_service
        now = datetime.now(timezone.utc)
        for index in range(120):
            txn = Transaction(
                transaction_id=f"{cid}:ok{index:03d}{unique_id[:8]}",
                company_id=cid,
                user_id=system_user_id,
                amount=100.0,
                status=PaymentStatus.SUCCESS,
                payment_provider=PaymentProviderType.TINKOFF,
                created_at=now,
                completed_at=now,
                balance_applied=True,
            )
            await payment_service._save_transaction(txn)
        check_calls: list[list[str]] = []

        async def fake_sync(
            self: TinkoffProvider,
            pending: list[PaymentSyncCandidate],
            storage: Storage | None = None,
        ) -> list[PaymentSyncOperation]:
            _ = self, storage
            check_calls.append([item.transaction_id for item in pending])
            return []

        monkeypatch.setattr(TinkoffProvider, "sync_pending_transactions", fake_sync)
        sync_service = PaymentSyncService(
            payment_service=payment_service,
            storage=frontend_di.shared_storage,
        )
        try:
            stats = await sync_service.sync_pending_transactions(cid)
            assert stats.total_pending == 0
            assert stats.checked == 0
            assert check_calls == []
        finally:
            await _delete_company_payments(frontend_di.shared_storage, cid)
            await Company.delete_by_id(cid)

    async def test_stale_pending_expires_after_check_order(
        self,
        frontend_di,
        unique_id: str,
        system_user_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _ = _require_configured_provider()
        monkeypatch.setattr(get_settings().payment_providers, "sync_pending_max_age_hours", 24)
        monkeypatch.setattr(get_settings().payment_providers, "sync_check_order_limit", 50)
        cid = f"co_exp_{unique_id}"
        await _seed_billing_company(
            frontend_di,
            company_id=cid,
            name=f"Payment expire {unique_id}",
            owner_user_id=system_user_id,
            balance=10.0,
        )
        payment_service = frontend_di.payment_service
        stale_id = new_payment_transaction_id(cid)
        fresh_id = new_payment_transaction_id(cid)
        stale = Transaction(
            transaction_id=stale_id,
            company_id=cid,
            user_id=system_user_id,
            amount=100.0,
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType.TINKOFF,
            created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        fresh = Transaction(
            transaction_id=fresh_id,
            company_id=cid,
            user_id=system_user_id,
            amount=100.0,
            status=PaymentStatus.PENDING,
            payment_provider=PaymentProviderType.TINKOFF,
        )
        await payment_service._save_transaction(stale)
        await payment_service._save_transaction(fresh)
        check_ids: list[str] = []

        async def fake_sync(
            self: TinkoffProvider,
            pending: list[PaymentSyncCandidate],
            storage: Storage | None = None,
        ) -> list[PaymentSyncOperation]:
            _ = self, storage
            check_ids.extend(item.transaction_id for item in pending)
            return []

        monkeypatch.setattr(TinkoffProvider, "sync_pending_transactions", fake_sync)
        sync_service = PaymentSyncService(
            payment_service=payment_service,
            storage=frontend_di.shared_storage,
        )
        try:
            stats = await sync_service.sync_pending_transactions(cid)
            assert stale_id in check_ids
            assert fresh_id in check_ids
            stored_stale = await payment_service.get_transaction(stale_id)
            stored_fresh = await payment_service.get_transaction(fresh_id)
            assert stored_stale is not None
            assert stored_fresh is not None
            assert stored_stale.status == PaymentStatus.FAILED
            assert stored_fresh.status == PaymentStatus.PENDING
            assert stats.updated == 1
            co = await Company.get(cid)
            assert co is not None
            assert co.balance == 10.0
        finally:
            await _delete_company_payments(frontend_di.shared_storage, cid)
            await Company.delete_by_id(cid)

    async def test_global_sync_does_not_scan_subdomain_keys(
        self,
        frontend_di,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _ = _require_configured_provider()
        original = Storage.list_by_prefix

        async def wrapped(
            self: Storage,
            prefix: str,
            limit: int = 100,
            force_global: bool = False,
        ) -> list[str]:
            if prefix.startswith("subdomain:"):
                raise AssertionError("payment sync must not scan subdomain keys")
            return await original(self, prefix, limit=limit, force_global=force_global)

        async def no_pending(*_args: object, **_kwargs: object) -> list[Transaction]:
            return []

        monkeypatch.setattr(Storage, "list_by_prefix", wrapped)
        monkeypatch.setattr(
            frontend_di.payment_service,
            "list_pending_transactions",
            no_pending,
        )
        sync_service = PaymentSyncService(
            payment_service=frontend_di.payment_service,
            storage=frontend_di.shared_storage,
        )
        stats = await sync_service.sync_all_companies()
        assert stats.total_pending == 0
        assert stats.companies_checked == 0
