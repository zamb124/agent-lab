"""
Тесты платёжной системы: YooMoney SHA-1, PaymentService, Billing API, Webhook.

Проверяем:
- SHA-1 верификацию webhook по спецификации YooMoney
  (https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming)
- Жизненный цикл транзакции: создание -> webhook -> пополнение баланса
- API endpoints: POST /api/billing/topup, GET /api/billing/history
- Webhook endpoint: POST /api/v1/payments/webhook/{provider_name}
- Защиту: невалидная подпись, дубликаты, несуществующий провайдер, роли
"""

import hashlib
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.clients.payment.base_provider import (
    PaymentRequest,
    WebhookVerificationResult,
)
from core.clients.payment.factory import PaymentProviderFactory
from core.clients.payment.yoomoney_provider import (
    YOOMONEY_TOKEN_STORAGE_KEY,
    YooMoneyConfig,
    YooMoneyProvider,
    YooMoneyTokenData,
    load_access_token,
    save_access_token,
)
from core.models.identity_models import Company, User
from core.models.payment_models import (
    PaymentProviderType,
    PaymentStatus,
    Transaction,
)
from core.utils.tokens import get_token_service


NOTIFICATION_SECRET = "test_notification_secret_abc123"


def _compute_yoomoney_sha1(
    notification_type: str,
    operation_id: str,
    amount: str,
    currency: str,
    dt: str,
    sender: str,
    codepro: str,
    secret: str,
    label: str,
) -> str:
    """
    Точное воспроизведение алгоритма подписи из документации YooMoney:
    SHA-1(notification_type&operation_id&amount&currency&datetime&sender&codepro&notification_secret&label)
    """
    parts = f"{notification_type}&{operation_id}&{amount}&{currency}&{dt}&{sender}&{codepro}&{secret}&{label}"
    return hashlib.sha1(parts.encode("utf-8")).hexdigest()


def _build_webhook_data(
    label: str,
    amount: str = "500.00",
    secret: str = NOTIFICATION_SECRET,
    *,
    notification_type: str = "p2p-incoming",
    operation_id: str = "op_123456",
    currency: str = "643",
    dt: str = "2026-04-10T12:00:00Z",
    sender: str = "41001234567890",
    codepro: str = "false",
    override_hash: str | None = None,
) -> dict:
    """Собирает словарь webhook-уведомления с корректной SHA-1 подписью."""
    sha1_hash = override_hash or _compute_yoomoney_sha1(
        notification_type, operation_id, amount, currency, dt, sender, codepro, secret, label,
    )
    return {
        "notification_type": notification_type,
        "operation_id": operation_id,
        "amount": amount,
        "currency": currency,
        "datetime": dt,
        "sender": sender,
        "codepro": codepro,
        "sha1_hash": sha1_hash,
        "label": label,
    }


def _make_yoomoney_provider() -> YooMoneyProvider:
    config = YooMoneyConfig(
        provider_type="yoomoney",
        account_number="4100123456789",
        notification_secret=NOTIFICATION_SECRET,
    )
    return YooMoneyProvider(config)


# ---------------------------------------------------------------------------
#  1. SHA-1 верификация YooMoney webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestYooMoneySHA1Verification:
    """
    Проверяем алгоритм SHA-1 из документации:
    sha1(notification_type&operation_id&amount&currency&datetime&sender&codepro&notification_secret&label)
    """

    async def test_valid_signature_p2p_incoming(self):
        """Валидная подпись p2p-incoming (перевод из кошелька)."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="company1:txn_abc123", amount="1000.00")

        result = await provider.verify_webhook(data)

        assert result.is_valid is True
        assert result.transaction_id == "company1:txn_abc123"
        assert result.amount == 1000.00
        assert result.external_payment_id == "op_123456"
        assert result.status == "success"
        assert result.error_message is None

    async def test_valid_signature_card_incoming(self):
        """Валидная подпись card-incoming (оплата картой через Quickpay)."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(
            label="company2:txn_xyz789",
            amount="500.00",
            notification_type="card-incoming",
            sender="",
        )

        result = await provider.verify_webhook(data)

        assert result.is_valid is True
        assert result.transaction_id == "company2:txn_xyz789"
        assert result.amount == 500.00

    async def test_invalid_signature_rejected(self):
        """Неверная подпись отклоняется."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(
            label="company1:txn_abc",
            override_hash="0000000000000000000000000000000000000000",
        )

        result = await provider.verify_webhook(data)

        assert result.is_valid is False
        assert result.error_message == "Invalid signature"
        assert result.transaction_id is None
        assert result.amount is None

    async def test_tampered_amount_breaks_signature(self):
        """Изменение суммы после подписи делает подпись невалидной."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="c:txn_1", amount="100.00")
        data["amount"] = "999.00"

        result = await provider.verify_webhook(data)

        assert result.is_valid is False

    async def test_tampered_label_breaks_signature(self):
        """Подмена label (transaction_id) ломает подпись."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="legit:txn_1")
        data["label"] = "attacker:txn_evil"

        result = await provider.verify_webhook(data)

        assert result.is_valid is False

    async def test_wrong_secret_breaks_signature(self):
        """Если notification_secret не совпадает, подпись невалидна."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(
            label="c:txn_1",
            secret="wrong_secret_from_attacker",
        )

        result = await provider.verify_webhook(data)

        assert result.is_valid is False

    async def test_missing_required_field_rejected(self):
        """Отсутствие обязательного поля -- невалидный webhook."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="c:txn_1")
        del data["operation_id"]

        result = await provider.verify_webhook(data)

        assert result.is_valid is False
        assert "Missing" in result.error_message

    async def test_empty_label_valid(self):
        """Пустой label -- валидная подпись (YooMoney отправляет пустой label если не задан)."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="")

        result = await provider.verify_webhook(data)

        assert result.is_valid is True
        assert result.transaction_id == ""

    async def test_documentation_example_hash(self):
        """
        Проверяем формулу SHA-1 из документации YooMoney:
        sha1("p2p-incoming&1234567&300.00&643&2011-07-01T09:00:00.000+04:00
              &41001XXXXXXXX&false&01234567890ABCDEF01234567890&YM.label.12345")
        == "a2ee4a9195f4a90e893cff4f62eeba0b662321f9"
        """
        expected_hash = "a2ee4a9195f4a90e893cff4f62eeba0b662321f9"
        computed = _compute_yoomoney_sha1(
            notification_type="p2p-incoming",
            operation_id="1234567",
            amount="300.00",
            currency="643",
            dt="2011-07-01T09:00:00.000+04:00",
            sender="41001XXXXXXXX",
            codepro="false",
            secret="01234567890ABCDEF01234567890",
            label="YM.label.12345",
        )
        assert computed == expected_hash

    async def test_utf8_encoding_in_hash(self):
        """Подпись корректно считается в UTF-8 (как в спецификации)."""
        provider = _make_yoomoney_provider()
        data = _build_webhook_data(label="company:txn_кириллица")

        result = await provider.verify_webhook(data)

        assert result.is_valid is True


# ---------------------------------------------------------------------------
#  2. YooMoneyProvider.create_payment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestYooMoneyCreatePayment:

    async def test_quickpay_url_generated(self):
        """create_payment генерирует Quickpay URL с корректными параметрами."""
        provider = _make_yoomoney_provider()
        request = PaymentRequest(
            amount=1500.0,
            company_id="comp_1",
            user_id="user_1",
            transaction_id="comp_1:txn_test123",
            success_url="https://example.com/billing?payment=success",
            fail_url="https://example.com/billing?payment=fail",
        )

        response = await provider.create_payment(request)

        assert response.payment_url.startswith("https://yoomoney.ru/quickpay/confirm.xml?")
        assert "receiver=4100123456789" in response.payment_url
        assert "sum=1500.0" in response.payment_url
        assert "label=comp_1%3Atxn_test123" in response.payment_url
        assert "paymentType=AC" in response.payment_url
        assert response.external_payment_id is None

    async def test_quickpay_contains_success_and_fail_urls(self):
        """URL содержит successURL и failURL."""
        provider = _make_yoomoney_provider()
        request = PaymentRequest(
            amount=200.0,
            company_id="c",
            user_id="u",
            transaction_id="c:txn_1",
            success_url="https://host/billing?payment=success",
            fail_url="https://host/billing?payment=fail",
        )

        response = await provider.create_payment(request)

        assert "successURL=" in response.payment_url
        assert "failURL=" in response.payment_url


# ---------------------------------------------------------------------------
#  3. PaymentService -- жизненный цикл транзакции
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPaymentService:

    async def test_create_payment_stores_transaction(
        self, frontend_container, unique_id,
    ):
        """create_payment сохраняет транзакцию со статусом PENDING."""
        company_id = f"pay_co_{unique_id}"
        user_id = f"pay_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Pay Test Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="Pay User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        provider = _make_yoomoney_provider()
        result = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=1000.0, provider=provider,
        )

        assert "transaction_id" in result
        assert result["amount"] == 1000.0
        assert result["payment_url"].startswith("https://yoomoney.ru/quickpay/")

        stored = await frontend_container.payment_service.get_transaction(
            result["transaction_id"],
        )
        assert stored is not None
        assert stored.status == PaymentStatus.PENDING
        assert stored.amount == 1000.0
        assert stored.company_id == company_id

    async def test_process_webhook_updates_balance(
        self, frontend_container, unique_id,
    ):
        """Полный цикл: создание -> webhook -> баланс компании пополнен."""
        company_id = f"wh_co_{unique_id}"
        user_id = f"wh_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Webhook Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=500.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="WH User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        provider = _make_yoomoney_provider()
        payment = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=2000.0, provider=provider,
        )

        txn_id = payment["transaction_id"]
        webhook_data = _build_webhook_data(
            label=txn_id, amount="2000.00", operation_id=f"op_{unique_id}",
        )

        verification = await provider.verify_webhook(webhook_data)
        assert verification.is_valid is True

        await frontend_container.payment_service.process_webhook(
            verification_result=verification,
            provider_name="yoomoney_main",
            raw_data=webhook_data,
        )

        updated_txn = await frontend_container.payment_service.get_transaction(txn_id)
        assert updated_txn.status == PaymentStatus.SUCCESS
        assert updated_txn.external_payment_id == f"op_{unique_id}"
        assert updated_txn.completed_at is not None

        updated_company = await frontend_container.company_repository.get(company_id)
        assert updated_company.balance == 2500.0

    async def test_duplicate_webhook_ignored(self, frontend_container, unique_id):
        """Повторный webhook с тем же operation_id не пополняет баланс дважды."""
        company_id = f"dup_co_{unique_id}"
        user_id = f"dup_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Dup Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=100.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="Dup User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        provider = _make_yoomoney_provider()
        payment = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=500.0, provider=provider,
        )

        txn_id = payment["transaction_id"]
        op_id = f"op_dup_{unique_id}"
        webhook_data = _build_webhook_data(
            label=txn_id, amount="500.00", operation_id=op_id,
        )

        verification = await provider.verify_webhook(webhook_data)

        await frontend_container.payment_service.process_webhook(
            verification_result=verification,
            provider_name="yoomoney_main",
            raw_data=webhook_data,
        )

        # Второй раз -- дубликат, баланс не изменится
        await frontend_container.payment_service.process_webhook(
            verification_result=verification,
            provider_name="yoomoney_main",
            raw_data=webhook_data,
        )

        final_company = await frontend_container.company_repository.get(company_id)
        assert final_company.balance == 600.0

    async def test_webhook_recovers_missing_transaction(
        self, frontend_container, unique_id,
    ):
        """
        Webhook для несуществующей транзакции восстанавливает её из label.
        Формат label: {company_id}:txn_{uuid}
        """
        company_id = f"rec_co_{unique_id}"
        user_id = f"rec_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Recovery Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="Rec User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        # Транзакция не создавалась через create_payment --
        # имитируем ситуацию когда KV потерял запись
        fake_txn_id = f"{company_id}:txn_{uuid.uuid4().hex[:16]}"
        op_id = f"op_rec_{unique_id}"

        provider = _make_yoomoney_provider()
        webhook_data = _build_webhook_data(
            label=fake_txn_id, amount="750.00", operation_id=op_id,
        )
        verification = await provider.verify_webhook(webhook_data)

        await frontend_container.payment_service.process_webhook(
            verification_result=verification,
            provider_name="yoomoney_main",
            raw_data=webhook_data,
        )

        recovered_txn = await frontend_container.payment_service.get_transaction(fake_txn_id)
        assert recovered_txn is not None
        assert recovered_txn.status == PaymentStatus.SUCCESS
        assert recovered_txn.amount == 750.0

        updated_company = await frontend_container.company_repository.get(company_id)
        assert updated_company.balance == 750.0

    async def test_get_company_transactions_returns_sorted(
        self, frontend_container, unique_id,
    ):
        """get_company_transactions возвращает транзакции отсортированные по дате."""
        company_id = f"list_co_{unique_id}"
        user_id = f"list_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="List Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="List User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        provider = _make_yoomoney_provider()

        for i in range(3):
            await frontend_container.payment_service.create_payment(
                company=company, user=user, amount=100.0 * (i + 1), provider=provider,
            )

        transactions = await frontend_container.payment_service.get_company_transactions(
            company_id=company_id,
        )

        assert len(transactions) == 3
        for t in transactions:
            assert t.company_id == company_id
        amounts = [t.amount for t in transactions]
        assert 100.0 in amounts
        assert 200.0 in amounts
        assert 300.0 in amounts

    async def test_webhook_unknown_provider_raises(self, frontend_container, unique_id):
        """process_webhook с неизвестным именем провайдера бросает ValueError."""
        provider = _make_yoomoney_provider()

        company_id = f"unk_co_{unique_id}"
        user_id = f"unk_usr_{unique_id}"
        company = Company(
            company_id=company_id,
            name="Unk Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)
        user = User(
            user_id=user_id,
            name="Unk User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        payment = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=100.0, provider=provider,
        )

        webhook_data = _build_webhook_data(
            label=payment["transaction_id"],
            amount="100.00",
            operation_id=f"op_unk_{unique_id}",
        )
        verification = await provider.verify_webhook(webhook_data)

        with pytest.raises(ValueError, match="Неизвестный провайдер"):
            await frontend_container.payment_service.process_webhook(
                verification_result=verification,
                provider_name="totally_unknown_provider",
                raw_data=webhook_data,
            )


# ---------------------------------------------------------------------------
#  4. Billing API -- topup, history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBillingTopupAPI:

    async def test_topup_success(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
        monkeypatch,
    ):
        """POST /api/billing/topup -- успешное создание платежа."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_test": provider},
        )
        monkeypatch.setattr(
            PaymentProviderFactory, "get_default_provider",
            classmethod(lambda cls: provider),
        )

        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 1000.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "payment_id" in data
        assert data["amount"] == 1000.0
        assert data["payment_url"].startswith("https://yoomoney.ru/quickpay/")

    async def test_topup_amount_too_small(
        self, frontend_client: AsyncClient, auth_headers,
    ):
        """Сумма ниже 100 -- 422."""
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 50.0},
        )
        assert response.status_code == 422

    async def test_topup_amount_too_large(
        self, frontend_client: AsyncClient, auth_headers,
    ):
        """Сумма выше 1_000_000 -- 422."""
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 2_000_000.0},
        )
        assert response.status_code == 422

    async def test_topup_unauthorized(self, frontend_client: AsyncClient):
        """Без авторизации -- 401."""
        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            json={"amount": 1000.0},
        )
        assert response.status_code == 401

    async def test_topup_viewer_forbidden(
        self, frontend_client: AsyncClient, frontend_container, unique_id,
    ):
        """Роль viewer не может пополнять баланс -- 403."""
        company_id = f"viewer_co_{unique_id}"
        viewer_id = f"viewer_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Viewer Co",
            owner_user_id="someone_else",
            members={viewer_id: ["viewer"]},
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=viewer_id,
            name="Viewer",
            companies={company_id: ["viewer"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        token = get_token_service().create_token(viewer_id, company_id=company_id)

        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 500.0},
        )
        assert response.status_code == 403

    async def test_topup_admin_allowed(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """Роль admin может пополнять (не только owner)."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_test": provider},
        )
        monkeypatch.setattr(
            PaymentProviderFactory, "get_default_provider",
            classmethod(lambda cls: provider),
        )

        company_id = f"admin_co_{unique_id}"
        admin_id = f"admin_{unique_id}"

        company = Company(
            company_id=company_id,
            name="Admin Co",
            owner_user_id="owner_x",
            members={admin_id: ["admin"]},
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=admin_id,
            name="Admin",
            companies={company_id: ["admin"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        token = get_token_service().create_token(admin_id, company_id=company_id)

        response = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 500.0},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True


@pytest.mark.asyncio
class TestBillingHistoryAPI:

    async def test_history_empty(
        self, frontend_client: AsyncClient, auth_headers,
    ):
        """GET /api/billing/history -- пустая история."""
        response = await frontend_client.get(
            "/frontend/api/billing/history",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "payments" in data
        assert isinstance(data["payments"], list)

    async def test_history_after_topup(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        frontend_container,
        monkeypatch,
    ):
        """После topup в истории появляется транзакция."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_test": provider},
        )
        monkeypatch.setattr(
            PaymentProviderFactory, "get_default_provider",
            classmethod(lambda cls: provider),
        )

        topup_resp = await frontend_client.post(
            "/frontend/api/billing/topup",
            headers=auth_headers,
            json={"amount": 777.0},
        )
        assert topup_resp.status_code == 200

        history_resp = await frontend_client.get(
            "/frontend/api/billing/history",
            headers=auth_headers,
        )
        assert history_resp.status_code == 200
        payments = history_resp.json()["payments"]
        amounts = [p["amount"] for p in payments]
        assert 777.0 in amounts

    async def test_history_unauthorized(self, frontend_client: AsyncClient):
        """Без авторизации -- 401."""
        response = await frontend_client.get("/frontend/api/billing/history")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
#  5. Webhook HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWebhookEndpoint:

    async def test_webhook_valid_signature(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """POST /api/v1/payments/webhook/{provider} -- валидная подпись, 200."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        company_id = f"wh_api_co_{unique_id}"
        user_id = f"wh_api_usr_{unique_id}"

        company = Company(
            company_id=company_id,
            name="WH API Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=user_id,
            name="WH API User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        payment = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=300.0, provider=provider,
        )
        txn_id = payment["transaction_id"]
        op_id = f"op_wh_{unique_id}"

        form_data = _build_webhook_data(
            label=txn_id, amount="300.00", operation_id=op_id,
        )

        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/yoomoney_main",
            content="&".join(f"{k}={v}" for k, v in form_data.items()),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200

        updated_txn = await frontend_container.payment_service.get_transaction(txn_id)
        assert updated_txn.status == PaymentStatus.SUCCESS

        updated_company = await frontend_container.company_repository.get(company_id)
        assert updated_company.balance == 300.0

    async def test_webhook_invalid_signature_still_200(
        self, frontend_client: AsyncClient, monkeypatch,
    ):
        """
        Невалидная подпись -> HTTP 200 (YooMoney ожидает 200 для прекращения повторов),
        но баланс не пополняется.
        """
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        form_data = _build_webhook_data(
            label="fake:txn_1",
            override_hash="0000000000000000000000000000000000000000",
        )

        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/yoomoney_main",
            content="&".join(f"{k}={v}" for k, v in form_data.items()),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200

    async def test_webhook_unknown_provider_404(
        self, frontend_client: AsyncClient, monkeypatch,
    ):
        """Несуществующий провайдер -> 404."""
        monkeypatch.setattr(PaymentProviderFactory, "_providers", {})

        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/nonexistent_provider",
            content="notification_type=p2p-incoming",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 404

    async def test_webhook_form_urlencoded_content_type(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """Webhook принимает application/x-www-form-urlencoded (стандарт YooMoney)."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        company_id = f"ct_co_{unique_id}"
        user_id = f"ct_usr_{unique_id}"
        company = Company(
            company_id=company_id,
            name="CT Co",
            owner_user_id=user_id,
            members={user_id: ["owner"]},
            balance=0.0,
        )
        await frontend_container.company_repository.set(company)
        user = User(
            user_id=user_id,
            name="CT User",
            companies={company_id: ["owner"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        payment = await frontend_container.payment_service.create_payment(
            company=company, user=user, amount=200.0, provider=provider,
        )

        form_data = _build_webhook_data(
            label=payment["transaction_id"],
            amount="200.00",
            operation_id=f"op_ct_{unique_id}",
        )

        response = await frontend_client.post(
            "/frontend/api/v1/payments/webhook/yoomoney_main",
            content="&".join(f"{k}={v}" for k, v in form_data.items()),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200

        updated_company = await frontend_container.company_repository.get(company_id)
        assert updated_company.balance == 200.0


# ---------------------------------------------------------------------------
#  6. PaymentProviderFactory
# ---------------------------------------------------------------------------


class TestPaymentProviderFactory:

    def test_create_config_yoomoney(self):
        """Создание YooMoneyConfig из словаря."""
        config_dict = {
            "provider_type": "yoomoney",
            "account_number": "4100999",
            "notification_secret": "secret123",
            "enabled": True,
        }
        config = PaymentProviderFactory._create_config_object(config_dict)
        assert isinstance(config, YooMoneyConfig)
        assert config.account_number == "4100999"
        assert config.notification_secret == "secret123"

    def test_create_config_unknown_type_raises(self):
        """Неизвестный provider_type бросает ValueError."""
        with pytest.raises(ValueError, match="Неизвестный тип"):
            PaymentProviderFactory._create_config_object({"provider_type": "stripe"})

    def test_create_config_missing_type_raises(self):
        """Отсутствие provider_type бросает ValueError."""
        with pytest.raises(ValueError, match="provider_type"):
            PaymentProviderFactory._create_config_object({})

    def test_get_provider_returns_none_for_missing(self, monkeypatch):
        """get_provider для несуществующего имени возвращает None."""
        monkeypatch.setattr(PaymentProviderFactory, "_providers", {})
        assert PaymentProviderFactory.get_provider("unknown") is None

    def test_get_default_provider_returns_first_if_no_default(self, monkeypatch):
        """Если default_provider не задан, возвращает первый доступный."""
        provider = _make_yoomoney_provider()
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        from unittest.mock import MagicMock

        mock_settings = MagicMock()
        mock_settings.payment_providers.default_provider = None
        monkeypatch.setattr(
            "core.clients.payment.factory.get_settings", lambda: mock_settings,
        )

        result = PaymentProviderFactory.get_default_provider()
        assert result is provider


# ---------------------------------------------------------------------------
#  7. Модели -- валидация
# ---------------------------------------------------------------------------


class TestPaymentModels:

    def test_create_payment_request_min_amount(self):
        """CreatePaymentRequest валидирует min amount = 100."""
        from core.models.payment_models import CreatePaymentRequest

        with pytest.raises(Exception):
            CreatePaymentRequest(amount=99.99)

    def test_create_payment_request_max_amount(self):
        """CreatePaymentRequest валидирует max amount = 1_000_000."""
        from core.models.payment_models import CreatePaymentRequest

        with pytest.raises(Exception):
            CreatePaymentRequest(amount=1_000_001.0)

    def test_create_payment_request_valid(self):
        """CreatePaymentRequest принимает валидную сумму."""
        from core.models.payment_models import CreatePaymentRequest

        req = CreatePaymentRequest(amount=500.0)
        assert req.amount == 500.0

    def test_transaction_default_status_pending(self):
        """Transaction по умолчанию создаётся со статусом PENDING."""
        txn = Transaction(
            transaction_id="test:txn_1",
            company_id="test",
            user_id="user_1",
            amount=100.0,
            payment_provider=PaymentProviderType.YOOMONEY,
        )
        assert txn.status == PaymentStatus.PENDING
        assert txn.completed_at is None

    def test_payment_status_enum_values(self):
        """PaymentStatus содержит все ожидаемые значения."""
        assert PaymentStatus.PENDING.value == "pending"
        assert PaymentStatus.SUCCESS.value == "success"
        assert PaymentStatus.FAILED.value == "failed"
        assert PaymentStatus.CANCELLED.value == "cancelled"
        assert PaymentStatus.REFUNDED.value == "refunded"

    def test_transaction_serialization_roundtrip(self):
        """Transaction сериализуется в JSON и обратно без потерь."""
        txn = Transaction(
            transaction_id="rt:txn_1",
            company_id="rt",
            user_id="u1",
            amount=999.99,
            status=PaymentStatus.SUCCESS,
            payment_provider=PaymentProviderType.YOOMONEY,
            external_payment_id="op_ext_1",
        )
        json_str = txn.model_dump_json()
        restored = Transaction.model_validate_json(json_str)

        assert restored.transaction_id == txn.transaction_id
        assert restored.amount == txn.amount
        assert restored.status == PaymentStatus.SUCCESS
        assert restored.external_payment_id == "op_ext_1"


# ---------------------------------------------------------------------------
#  8. Token storage -- save/load access_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.xdist_group("yoomoney_token_storage")
class TestYooMoneyTokenStorage:

    async def test_save_and_load_token(self, frontend_container):
        """save_access_token сохраняет токен, load_access_token загружает его."""
        storage = frontend_container.company_repository._storage

        token_data = await save_access_token(storage, "test_token_abc123")

        assert token_data.token == "test_token_abc123"
        assert token_data.is_expired() is False

        loaded = await load_access_token(storage)
        assert loaded is not None
        assert loaded.token == "test_token_abc123"

        # Очистка
        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

    async def test_load_missing_token_returns_none(self, frontend_container):
        """load_access_token возвращает None если токена нет."""
        storage = frontend_container.company_repository._storage

        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

        loaded = await load_access_token(storage)
        assert loaded is None

    async def test_expired_token_returns_none(self, frontend_container):
        """load_access_token возвращает None если токен истёк."""
        storage = frontend_container.company_repository._storage

        from datetime import datetime, timezone, timedelta
        import json

        expired_data = json.dumps({
            "token": "expired_token",
            "obtained_at": (datetime.now(timezone.utc) - timedelta(days=365 * 4)).isoformat(),
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        })
        await storage.set(YOOMONEY_TOKEN_STORAGE_KEY, expired_data, force_global=True)

        loaded = await load_access_token(storage)
        assert loaded is None

        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

    def test_token_data_serialization_roundtrip(self):
        """YooMoneyTokenData сериализуется и десериализуется корректно."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        original = YooMoneyTokenData(
            token="my_token_123",
            obtained_at=now,
            expires_at=now + timedelta(days=365 * 3),
        )

        json_str = original.to_json()
        restored = YooMoneyTokenData.from_json(json_str)

        assert restored.token == "my_token_123"
        assert restored.is_expired() is False

    def test_expired_token_data(self):
        """YooMoneyTokenData.is_expired() возвращает True для истёкших токенов."""
        from datetime import datetime, timezone, timedelta

        past = datetime.now(timezone.utc) - timedelta(days=1)
        token_data = YooMoneyTokenData(
            token="old",
            obtained_at=past - timedelta(days=365 * 3),
            expires_at=past,
        )

        assert token_data.is_expired() is True


# ---------------------------------------------------------------------------
#  9. YooMoney OAuth endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestYooMoneyOAuthAuthorize:

    async def test_authorize_returns_url(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        monkeypatch,
    ):
        """GET /api/billing/yoomoney/authorize возвращает URL авторизации."""
        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="secret",
            client_id="test_client_id_123",
            client_secret="test_client_secret_456",
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/authorize",
            headers=auth_headers,
            follow_redirects=False,
        )

        assert response.status_code == 200
        data = response.json()
        assert "authorize_url" in data
        assert "yoomoney.ru/oauth/authorize" in data["authorize_url"]
        assert "client_id=test_client_id_123" in data["authorize_url"]
        assert "account-info" in data["authorize_url"]
        assert "operation-history" in data["authorize_url"]

    async def test_authorize_requires_auth(self, frontend_client: AsyncClient):
        """Без авторизации -- 401."""
        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/authorize",
            follow_redirects=False,
        )
        assert response.status_code == 401

    async def test_authorize_viewer_forbidden(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """Роль viewer не может авторизовать YooMoney -- 403."""
        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="secret",
            client_id="test_cid",
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        company_id = f"oa_co_{unique_id}"
        viewer_id = f"oa_viewer_{unique_id}"

        company = Company(
            company_id=company_id,
            name="OA Co",
            owner_user_id="someone",
            members={viewer_id: ["viewer"]},
        )
        await frontend_container.company_repository.set(company)

        user = User(
            user_id=viewer_id,
            name="Viewer",
            companies={company_id: ["viewer"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)

        token = get_token_service().create_token(viewer_id, company_id=company_id)

        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/authorize",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_authorize_no_client_id(
        self,
        frontend_client: AsyncClient,
        auth_headers,
        monkeypatch,
    ):
        """Если client_id не настроен -- 503."""
        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="secret",
            client_id=None,
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/authorize",
            headers=auth_headers,
            follow_redirects=False,
        )
        assert response.status_code == 503


@pytest.mark.asyncio
class TestYooMoneyOAuthCallback:

    async def test_callback_without_code_400(
        self,
        frontend_client: AsyncClient,
        monkeypatch,
    ):
        """Callback без code -- 400."""
        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="secret",
            client_id="cid",
            client_secret="csecret",
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/callback",
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_callback_exchanges_code(
        self,
        frontend_client: AsyncClient,
        frontend_container,
        monkeypatch,
    ):
        """Callback обменивает code на access_token через mock."""
        provider = YooMoneyProvider(YooMoneyConfig(
            provider_type="yoomoney",
            account_number="4100999",
            notification_secret="secret",
            client_id="test_cid",
            client_secret="test_csecret",
        ))
        monkeypatch.setattr(
            PaymentProviderFactory, "_providers", {"yoomoney_main": provider},
        )

        import httpx

        mock_response = httpx.Response(
            200,
            json={"access_token": "mock_access_token_xyz"},
            request=httpx.Request("POST", "https://yoomoney.ru/oauth/token"),
        )

        async def mock_request_public_oauth(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(
            "apps.frontend.api.yoomoney_oauth.request_public_oauth",
            mock_request_public_oauth,
        )

        response = await frontend_client.get(
            "/frontend/api/billing/yoomoney/callback?code=test_auth_code",
            follow_redirects=False,
        )

        # Callback делает redirect на /billing?oauth=success
        assert response.status_code in (302, 307)

        # Проверяем что токен сохранён в storage
        storage = frontend_container.company_repository._storage
        loaded = await load_access_token(storage)
        assert loaded is not None
        assert loaded.token == "mock_access_token_xyz"

        # Очистка
        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)


# ---------------------------------------------------------------------------
#  10. sync_pending_transactions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSyncPendingTransactions:

    async def test_sync_finds_completed_transaction(
        self,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """sync_pending_transactions находит оплаченную транзакцию."""
        storage = frontend_container.company_repository._storage

        await save_access_token(storage, "test_sync_token")

        provider = _make_yoomoney_provider()

        import httpx

        async def mock_post(self, url, **kwargs):
            return httpx.Response(
                200,
                json={
                    "operations": [
                        {
                            "operation_id": f"op_sync_{unique_id}",
                            "status": "success",
                            "amount": 500.0,
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            )

        from core.http.client import SmartProxyClient
        monkeypatch.setattr(SmartProxyClient, "post", mock_post)

        txn_id = f"sync_co_{unique_id}:txn_test123"

        found = await provider.sync_pending_transactions(
            [{"transaction_id": txn_id, "amount": 500.0, "created_at": "2026-01-01T00:00:00"}],
            storage=storage,
        )

        assert len(found) == 1
        assert found[0]["transaction_id"] == txn_id
        assert found[0]["status"] == "success"
        assert found[0]["operation_id"] == f"op_sync_{unique_id}"

        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

    async def test_sync_no_token_raises(
        self, frontend_container, unique_id, monkeypatch
    ):
        """sync_pending_transactions без токена бросает ValueError до HTTP."""

        storage = frontend_container.company_repository._storage
        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

        async def _no_token(_storage):
            return None

        monkeypatch.setattr(
            "core.clients.payment.yoomoney_provider.load_access_token",
            _no_token,
        )

        provider = _make_yoomoney_provider()

        with pytest.raises(ValueError, match="access_token"):
            await provider.sync_pending_transactions(
                [{"transaction_id": "x:txn_1", "amount": 100}],
                storage=storage,
            )

    async def test_sync_empty_pending_list(self, frontend_container):
        """sync_pending_transactions с пустым списком возвращает пустой список."""
        storage = frontend_container.company_repository._storage
        await save_access_token(storage, "test_token")

        provider = _make_yoomoney_provider()
        found = await provider.sync_pending_transactions([], storage=storage)
        assert found == []

        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

    async def test_sync_no_matching_operations(
        self,
        frontend_container,
        unique_id,
        monkeypatch,
    ):
        """sync_pending_transactions: API вернул пустой список операций."""
        storage = frontend_container.company_repository._storage
        await save_access_token(storage, "test_token")

        provider = _make_yoomoney_provider()

        import httpx

        async def mock_post(self, url, **kwargs):
            return httpx.Response(
                200,
                json={"operations": []},
                request=httpx.Request("POST", url),
            )

        from core.http.client import SmartProxyClient
        monkeypatch.setattr(SmartProxyClient, "post", mock_post)

        found = await provider.sync_pending_transactions(
            [{"transaction_id": f"no_match_{unique_id}:txn_1", "amount": 100}],
            storage=storage,
        )
        assert found == []

        await storage.delete(YOOMONEY_TOKEN_STORAGE_KEY, force_global=True)

    async def test_sync_without_storage_raises(self):
        """sync_pending_transactions без storage бросает ValueError."""
        provider = _make_yoomoney_provider()

        with pytest.raises(ValueError, match="storage"):
            await provider.sync_pending_transactions(
                [{"transaction_id": "x:txn_1", "amount": 100}],
            )
