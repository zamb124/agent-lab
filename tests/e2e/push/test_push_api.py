"""
E2E тесты для Push Notifications API.

РЕАЛЬНЫЕ тесты:
- Запускается frontend сервис на порту 9004
- HTTP запросы идут в реальные endpoints
- Данные реально сохраняются в PostgreSQL

Запуск:
    make test-up
    pytest tests/e2e/push/ -v -m e2e
"""

import pytest
import httpx


# Базовый URL frontend сервиса
FRONTEND_URL = "http://localhost:9004"


class TestPushAPIEndpoints:
    """
    E2E тесты Push API endpoints.
    Требуют запущенный frontend_service.
    """

    @pytest.mark.e2e
    def test_get_vapid_public_key(self, frontend_service):
        """
        GET /frontend/api/push/vapid-public-key
        
        Реальный запрос к сервису.
        """
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            response = client.get("/frontend/api/push/vapid-public-key")
            
            assert response.status_code == 200, f"Response: {response.text}"
            
            data = response.json()
            assert "publicKey" in data
            
            # VAPID public key должен быть base64url строкой ~87 символов
            public_key = data["publicKey"]
            assert isinstance(public_key, str)
            assert len(public_key) > 50, f"Key too short: {public_key}"

    @pytest.mark.e2e
    def test_subscribe_requires_auth(self, frontend_service, push_subscription_data):
        """
        POST /frontend/api/push/subscribe без авторизации
        
        Должен вернуть 401.
        """
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            response = client.post(
                "/frontend/api/push/subscribe",
                json=push_subscription_data
            )
            
            assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    @pytest.mark.e2e
    def test_subscribe_with_auth(self, frontend_service, push_subscription_data, auth_token_system, unique_id):
        """
        POST /frontend/api/push/subscribe с авторизацией
        
        Успешная подписка.
        """
        subscription_data = {
            **push_subscription_data,
            "endpoint": f"{push_subscription_data['endpoint']}_{unique_id}"
        }
        
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            response = client.post(
                "/frontend/api/push/subscribe",
                json=subscription_data,
                headers={"Authorization": f"Bearer {auth_token_system}"}
            )
            
            assert response.status_code == 200, f"Subscribe failed: {response.text}"
            data = response.json()
            assert data.get("success") is True
            assert "subscription_id" in data
            
            # Cleanup
            client.delete(
                "/frontend/api/push/unsubscribe",
                params={"endpoint": subscription_data["endpoint"]},
                headers={"Authorization": f"Bearer {auth_token_system}"}
            )

    @pytest.mark.e2e
    def test_subscribe_and_unsubscribe_cycle(
        self,
        frontend_service,
        push_subscription_data,
        auth_token_system,
        unique_id
    ):
        """
        Полный цикл подписки/отписки.
        """
        endpoint = f"{push_subscription_data['endpoint']}_cycle_{unique_id}"
        subscription_data = {
            **push_subscription_data,
            "endpoint": endpoint
        }
        
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {auth_token_system}"}
            
            # 1. Подписываемся
            response = client.post(
                "/frontend/api/push/subscribe",
                json=subscription_data,
                headers=headers
            )
            assert response.status_code == 200
            subscription_id = response.json().get("subscription_id")
            
            # 2. Повторная подписка - должен вернуть тот же ID (upsert)
            response2 = client.post(
                "/frontend/api/push/subscribe",
                json=subscription_data,
                headers=headers
            )
            assert response2.status_code == 200
            assert response2.json().get("subscription_id") == subscription_id
            
            # 3. Отписываемся
            response3 = client.delete(
                "/frontend/api/push/unsubscribe",
                params={"endpoint": endpoint},
                headers=headers
            )
            assert response3.status_code == 200
            assert response3.json().get("success") is True

    @pytest.mark.e2e
    def test_subscribe_multiple_devices(
        self,
        frontend_service,
        auth_token_system,
        unique_id
    ):
        """
        Подписка с нескольких устройств одного пользователя.
        """
        devices = [
            {"endpoint": f"https://fcm.googleapis.com/desktop-{unique_id}", "platform": "desktop"},
            {"endpoint": f"https://web.push.apple.com/ios-{unique_id}", "platform": "ios"},
            {"endpoint": f"https://fcm.googleapis.com/android-{unique_id}", "platform": "android"},
        ]
        
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {auth_token_system}"}
            subscription_ids = []
            
            for device in devices:
                response = client.post(
                    "/frontend/api/push/subscribe",
                    json={
                        "endpoint": device["endpoint"],
                        "keys": {"p256dh": "key", "auth": "auth"},
                        "platform": device["platform"]
                    },
                    headers=headers
                )
                assert response.status_code == 200, f"Failed for {device['platform']}: {response.text}"
                subscription_ids.append(response.json()["subscription_id"])
            
            # Все ID должны быть уникальными
            assert len(set(subscription_ids)) == 3
            
            # Cleanup
            for device in devices:
                client.delete(
                    "/frontend/api/push/unsubscribe",
                    params={"endpoint": device["endpoint"]},
                    headers=headers
                )


class TestPushAPIValidation:
    """Тесты валидации входных данных."""

    @pytest.mark.e2e
    def test_subscribe_missing_keys(self, frontend_service, auth_token_system):
        """Отсутствующие keys должны вернуть 422."""
        with httpx.Client(base_url=FRONTEND_URL, timeout=30.0) as client:
            response = client.post(
                "/frontend/api/push/subscribe",
                json={
                    "endpoint": "https://fcm.googleapis.com/valid"
                },
                headers={"Authorization": f"Bearer {auth_token_system}"}
            )
            
            assert response.status_code == 422
