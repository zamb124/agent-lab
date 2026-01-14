"""
Тесты для PushRepository.

Используется реальный PostgreSQL - никаких моков.
Каждый тест изолирован через unique_id.
"""

import pytest
import pytest_asyncio

from apps.agents.src.db.push_repository import PushRepository, PushSubscription


@pytest_asyncio.fixture
async def push_repo(container):
    """Реальный PushRepository"""
    return container.push_repository


@pytest.mark.asyncio
async def test_save_subscription(push_repo: PushRepository, unique_id: str):
    """Сохранение новой подписки"""
    user_id = f"user_{unique_id}@example.com"
    endpoint = f"https://push.example.com/send/{unique_id}"
    
    subscription_id = await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="test_p256dh_key_" + unique_id,
        auth="test_auth_key_" + unique_id,
        user_agent="Test Browser 1.0"
    )
    
    assert subscription_id > 0
    
    # Проверяем что подписка сохранилась
    subscriptions = await push_repo.get_by_user(user_id)
    assert len(subscriptions) == 1
    assert subscriptions[0].endpoint == endpoint
    assert subscriptions[0].p256dh == "test_p256dh_key_" + unique_id
    assert subscriptions[0].auth == "test_auth_key_" + unique_id
    assert subscriptions[0].user_agent == "Test Browser 1.0"
    
    # Cleanup
    await push_repo.delete_by_endpoint(endpoint)


@pytest.mark.asyncio
async def test_save_updates_existing_subscription(push_repo: PushRepository, unique_id: str):
    """При повторном сохранении с тем же endpoint - обновление"""
    user_id = f"user_{unique_id}@example.com"
    endpoint = f"https://push.example.com/send/{unique_id}"
    
    # Первое сохранение
    id1 = await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="old_key",
        auth="old_auth"
    )
    
    # Второе сохранение с тем же endpoint
    id2 = await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="new_key",
        auth="new_auth"
    )
    
    # Должен быть тот же ID (обновление, не создание)
    assert id1 == id2
    
    # Проверяем что данные обновились
    subscriptions = await push_repo.get_by_user(user_id)
    assert len(subscriptions) == 1
    assert subscriptions[0].p256dh == "new_key"
    assert subscriptions[0].auth == "new_auth"
    
    # Cleanup
    await push_repo.delete_by_endpoint(endpoint)


@pytest.mark.asyncio
async def test_multiple_subscriptions_per_user(push_repo: PushRepository, unique_id: str):
    """Пользователь может иметь несколько устройств"""
    user_id = f"user_{unique_id}@example.com"
    endpoints = [
        f"https://push.example.com/device1/{unique_id}",
        f"https://push.example.com/device2/{unique_id}",
        f"https://push.example.com/device3/{unique_id}",
    ]
    
    # Создаем подписки для трех устройств
    for i, endpoint in enumerate(endpoints):
        await push_repo.save(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=f"p256dh_{i}",
            auth=f"auth_{i}"
        )
    
    # Проверяем что все три сохранились
    subscriptions = await push_repo.get_by_user(user_id)
    assert len(subscriptions) == 3
    
    saved_endpoints = {s.endpoint for s in subscriptions}
    assert saved_endpoints == set(endpoints)
    
    # Cleanup
    for endpoint in endpoints:
        await push_repo.delete_by_endpoint(endpoint)


@pytest.mark.asyncio
async def test_delete_by_endpoint(push_repo: PushRepository, unique_id: str):
    """Удаление подписки по endpoint"""
    user_id = f"user_{unique_id}@example.com"
    endpoint = f"https://push.example.com/send/{unique_id}"
    
    await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="test_key",
        auth="test_auth"
    )
    
    # Проверяем что подписка есть
    assert await push_repo.exists(user_id) is True
    
    # Удаляем
    deleted = await push_repo.delete_by_endpoint(endpoint)
    assert deleted is True
    
    # Проверяем что подписки больше нет
    assert await push_repo.exists(user_id) is False


@pytest.mark.asyncio
async def test_delete_nonexistent_endpoint(push_repo: PushRepository, unique_id: str):
    """Удаление несуществующего endpoint возвращает False"""
    endpoint = f"https://push.example.com/nonexistent/{unique_id}"
    
    deleted = await push_repo.delete_by_endpoint(endpoint)
    assert deleted is False


@pytest.mark.asyncio
async def test_delete_by_user(push_repo: PushRepository, unique_id: str):
    """Удаление всех подписок пользователя"""
    user_id = f"user_{unique_id}@example.com"
    
    # Создаем несколько подписок
    for i in range(3):
        await push_repo.save(
            user_id=user_id,
            endpoint=f"https://push.example.com/{unique_id}/device{i}",
            p256dh=f"key_{i}",
            auth=f"auth_{i}"
        )
    
    # Проверяем что подписки есть
    subscriptions = await push_repo.get_by_user(user_id)
    assert len(subscriptions) == 3
    
    # Удаляем все
    count = await push_repo.delete_by_user(user_id)
    assert count == 3
    
    # Проверяем что ничего не осталось
    subscriptions = await push_repo.get_by_user(user_id)
    assert len(subscriptions) == 0


@pytest.mark.asyncio
async def test_get_by_endpoint(push_repo: PushRepository, unique_id: str):
    """Получение подписки по endpoint"""
    user_id = f"user_{unique_id}@example.com"
    endpoint = f"https://push.example.com/send/{unique_id}"
    
    await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="specific_key",
        auth="specific_auth",
        user_agent="Specific Agent"
    )
    
    # Получаем по endpoint
    subscription = await push_repo.get_by_endpoint(endpoint)
    
    assert subscription is not None
    assert isinstance(subscription, PushSubscription)
    assert subscription.user_id == user_id
    assert subscription.endpoint == endpoint
    assert subscription.p256dh == "specific_key"
    assert subscription.auth == "specific_auth"
    assert subscription.user_agent == "Specific Agent"
    
    # Cleanup
    await push_repo.delete_by_endpoint(endpoint)


@pytest.mark.asyncio
async def test_get_nonexistent_endpoint(push_repo: PushRepository, unique_id: str):
    """Получение несуществующего endpoint возвращает None"""
    endpoint = f"https://push.example.com/nonexistent/{unique_id}"
    
    subscription = await push_repo.get_by_endpoint(endpoint)
    assert subscription is None


@pytest.mark.asyncio
async def test_exists(push_repo: PushRepository, unique_id: str):
    """Проверка существования подписок пользователя"""
    user_id = f"user_{unique_id}@example.com"
    endpoint = f"https://push.example.com/send/{unique_id}"
    
    # Изначально подписок нет
    assert await push_repo.exists(user_id) is False
    
    # Создаем подписку
    await push_repo.save(
        user_id=user_id,
        endpoint=endpoint,
        p256dh="key",
        auth="auth"
    )
    
    # Теперь подписка есть
    assert await push_repo.exists(user_id) is True
    
    # Удаляем
    await push_repo.delete_by_endpoint(endpoint)
    
    # Снова нет
    assert await push_repo.exists(user_id) is False


@pytest.mark.asyncio
async def test_different_users_isolation(push_repo: PushRepository, unique_id: str):
    """Подписки разных пользователей изолированы"""
    user1 = f"user1_{unique_id}@example.com"
    user2 = f"user2_{unique_id}@example.com"
    
    endpoint1 = f"https://push.example.com/{unique_id}/user1"
    endpoint2 = f"https://push.example.com/{unique_id}/user2"
    
    await push_repo.save(user_id=user1, endpoint=endpoint1, p256dh="key1", auth="auth1")
    await push_repo.save(user_id=user2, endpoint=endpoint2, p256dh="key2", auth="auth2")
    
    # Подписки изолированы
    subs1 = await push_repo.get_by_user(user1)
    subs2 = await push_repo.get_by_user(user2)
    
    assert len(subs1) == 1
    assert len(subs2) == 1
    assert subs1[0].endpoint == endpoint1
    assert subs2[0].endpoint == endpoint2
    
    # Cleanup
    await push_repo.delete_by_endpoint(endpoint1)
    await push_repo.delete_by_endpoint(endpoint2)








