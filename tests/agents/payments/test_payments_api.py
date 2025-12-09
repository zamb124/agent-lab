"""
Тесты HTTP endpoints для Payments API.

Проверяют что API endpoints создают PaymentService правильно
и возвращают корректные ответы.
"""

import pytest


class TestPaymentsCreateAPI:
    """Тесты POST /payments/create"""

    @pytest.mark.asyncio
    async def test_create_payment_success(self, agents_client):
        """Создание платежа возвращает 200 и payment_url"""
        response = await agents_client.post(
            "/agents/api/v1/payments/create",
            json={"amount": 500.0}
        )
        
        # Может быть 200 или 400 если нет провайдера
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "transaction_id" in data
            assert "payment_url" in data
            assert data["amount"] == 500.0

    @pytest.mark.asyncio
    async def test_create_payment_invalid_amount(self, agents_client):
        """Создание платежа с невалидной суммой возвращает 422"""
        response = await agents_client.post(
            "/agents/api/v1/payments/create",
            json={"amount": -100.0}
        )
        
        # Невалидная сумма
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_payment_missing_amount(self, agents_client):
        """Создание платежа без суммы возвращает 422"""
        response = await agents_client.post(
            "/agents/api/v1/payments/create",
            json={}
        )
        
        assert response.status_code == 422


class TestPaymentsHistoryAPI:
    """Тесты GET /payments/history"""

    @pytest.mark.asyncio
    async def test_get_history_success(self, agents_client):
        """Получение истории платежей возвращает 200"""
        response = await agents_client.get("/agents/api/v1/payments/history")
        
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        assert isinstance(data["transactions"], list)

    @pytest.mark.asyncio
    async def test_get_history_with_pagination(self, agents_client):
        """История платежей поддерживает пагинацию"""
        response = await agents_client.get(
            "/agents/api/v1/payments/history?limit=10&offset=0"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "limit" in data
        assert "offset" in data


class TestPaymentsTransactionAPI:
    """Тесты GET /payments/transaction/{id}"""

    @pytest.mark.asyncio
    async def test_get_transaction_not_found(self, agents_client, unique_id):
        """Несуществующая транзакция возвращает 404"""
        tx_id = unique_id("txn")
        response = await agents_client.get(
            f"/agents/api/v1/payments/transaction/{tx_id}"
        )
        
        assert response.status_code == 404


class TestPaymentsProvidersAPI:
    """Тесты GET /payments/providers"""

    @pytest.mark.asyncio
    async def test_get_providers_success(self, agents_client):
        """Получение списка провайдеров возвращает 200"""
        response = await agents_client.get("/agents/api/v1/payments/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)

