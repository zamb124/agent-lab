"""
Фикстуры для тестирования Push Notifications.

Используют существующую тестовую инфраструктуру:
- frontend_container для репозитория
- auth_token для авторизации
- frontend_service для E2E тестов

Запуск:
    make test-up
    pytest tests/core/push/ -v
    pytest tests/e2e/push/ -v
"""

import pytest
import pytest_asyncio


@pytest.fixture
def vapid_keys():
    """
    VAPID ключи для тестов.
    Используются реальные ключи из conf.local.json.
    """
    return {
        "public_key": "BP1OB4uP0WSgQqumAOefg1PdsN9S7qA1-UK26qjSPa11ylB1HgbcrVi6peEUkhkdfrADeTa_dwypXYiucfbu3JQ",
        "private_key": "lwzkecdrLZYcyUVhYUQuAnXYk92xup132qCCk5BtUEs",
        "email": "test@humanitec.ru"
    }


@pytest.fixture
def push_subscription_data():
    """Базовые данные push подписки для desktop."""
    return {
        "transport": "web_vapid",
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg"
        },
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "platform": "desktop"
    }


@pytest.fixture
def push_subscription_ios_data():
    """Данные push подписки для iOS."""
    return {
        "endpoint": "https://web.push.apple.com/test-endpoint-ios",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg"
        },
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "platform": "ios"
    }


@pytest.fixture
def push_subscription_android_data():
    """Данные push подписки для Android."""
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-android",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg"
        },
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7)",
        "platform": "android"
    }


@pytest.fixture
def push_repository(frontend_container):
    """
    Репозиторий для работы с push подписками.
    Использует container как все остальные репозитории.
    """
    return frontend_container.push_subscription_repository


@pytest.fixture
def web_push_service(vapid_keys):
    """
    WebPushService с тестовыми VAPID ключами.
    """
    from core.push.service import WebPushService
    
    return WebPushService(
        vapid_private_key=vapid_keys["private_key"],
        vapid_public_key=vapid_keys["public_key"],
        vapid_email=vapid_keys["email"]
    )


@pytest_asyncio.fixture
async def test_push_subscription(push_repository, push_subscription_data, unique_id):
    """
    Создает тестовую push подписку в реальной БД.
    Автоматически удаляется после теста.
    """
    user_id = f"test_user_{unique_id}"
    endpoint = f"{push_subscription_data['endpoint']}_{unique_id}"
    
    subscription = await push_repository.upsert_subscription(
        user_id=user_id,
        endpoint=endpoint,
        keys=push_subscription_data["keys"],
        platform=push_subscription_data["platform"],
        user_agent=push_subscription_data["user_agent"]
    )
    
    yield subscription
    
    # Cleanup
    try:
        await push_repository.delete_subscription(user_id, endpoint)
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_push_subscriptions_multi_device(push_repository, unique_id):
    """
    Создает подписки для 3 устройств одного пользователя.
    """
    user_id = f"test_user_multi_{unique_id}"
    
    devices = [
        ("desktop", f"https://fcm.googleapis.com/desktop-{unique_id}"),
        ("ios", f"https://web.push.apple.com/ios-{unique_id}"),
        ("android", f"https://fcm.googleapis.com/android-{unique_id}"),
    ]
    
    subscriptions = []
    endpoints = []
    
    for platform, endpoint in devices:
        endpoints.append(endpoint)
        sub = await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": f"key_{platform}", "auth": f"auth_{platform}"},
            platform=platform
        )
        subscriptions.append(sub)
    
    yield user_id, subscriptions
    
    # Cleanup
    for endpoint in endpoints:
        try:
            await push_repository.delete_subscription(user_id, endpoint)
        except Exception:
            pass


@pytest.fixture
def push_notification_payload():
    """Типичный payload для push уведомления."""
    return {
        "title": "Test Notification",
        "message": "This is a test push notification",
        "url": "/test/path",
        "tag": "test_tag",
        "priority": "normal",
        "data": {
            "entity_id": "test_entity_123",
            "action": "view"
        }
    }
