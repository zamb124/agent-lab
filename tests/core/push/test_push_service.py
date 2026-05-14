"""
Интеграционные тесты для Push Notifications.

Тестируют реальную работу с БД через container.
webpush мокается т.к. нет реального FCM сервера.

Запуск:
    make test-up
    pytest tests/core/push/ -v
"""

from unittest.mock import MagicMock, patch

import pytest


class TestPushRepository:
    """
    Тесты репозитория с реальной PostgreSQL.
    Используют frontend_container как все остальные тесты.
    """

    @pytest.mark.asyncio
    async def test_create_subscription(self, push_repository, unique_id):
        """Создание подписки в реальной БД."""
        user_id = f"user_{unique_id}"
        endpoint = f"https://fcm.googleapis.com/{unique_id}"

        subscription = await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": "test_key", "auth": "test_auth"},
            platform="desktop",
            user_agent="Test Browser"
        )

        assert subscription is not None
        assert subscription.user_id == user_id
        assert subscription.platform == "desktop"

        # Cleanup
        await push_repository.delete_subscription(user_id, endpoint)

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, push_repository, unique_id):
        """Upsert обновляет существующую подписку."""
        endpoint = f"https://fcm.googleapis.com/upsert-{unique_id}"
        user_id = f"user_{unique_id}"

        # Первое создание
        sub1 = await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": "key1", "auth": "auth1"},
            platform="ios"
        )

        # Обновление с новыми keys
        sub2 = await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": "key2", "auth": "auth2"},
            platform="android"
        )

        # ID должен остаться тем же
        assert sub1.id == sub2.id
        # Platform обновился
        assert sub2.platform == "android"

        # Cleanup
        await push_repository.delete_subscription(user_id, endpoint)

    @pytest.mark.asyncio
    async def test_get_user_subscriptions(self, push_repository, unique_id):
        """Получение всех подписок пользователя."""
        user_id = f"user_multi_{unique_id}"

        # Создаем 3 подписки
        endpoints = []
        for i in range(3):
            endpoint = f"https://fcm.googleapis.com/multi-{unique_id}-{i}"
            endpoints.append(endpoint)
            await push_repository.upsert_subscription(
                user_id=user_id,
                endpoint=endpoint,
                keys={"p256dh": f"key{i}", "auth": f"auth{i}"},
                platform=["desktop", "ios", "android"][i]
            )

        # Получаем все подписки
        subscriptions = await push_repository.get_user_subscriptions(user_id)

        assert len(subscriptions) == 3

        platforms = {s.platform for s in subscriptions}
        assert platforms == {"desktop", "ios", "android"}

        # Cleanup
        for endpoint in endpoints:
            await push_repository.delete_subscription(user_id, endpoint)

    @pytest.mark.asyncio
    async def test_delete_subscription(self, push_repository, unique_id):
        """Удаление подписки."""
        user_id = f"user_delete_{unique_id}"
        endpoint = f"https://fcm.googleapis.com/delete-{unique_id}"

        # Создаем
        await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": "key", "auth": "auth"},
            platform="desktop"
        )

        # Удаляем
        deleted = await push_repository.delete_subscription(user_id, endpoint)
        assert deleted is True

        # Проверяем что удалено
        subs = await push_repository.get_user_subscriptions(user_id)
        assert len(subs) == 0


class TestWebPushService:
    """
    Тесты сервиса отправки push.
    webpush мокается, остальное реальное.
    """

    @pytest.mark.asyncio
    @patch('core.push.service.webpush')
    async def test_send_push_calls_webpush(self, mock_webpush, vapid_keys):
        """send_push вызывает pywebpush с правильными параметрами."""
        import json

        from core.push.models import PushSubscription
        from core.push.service import WebPushService

        mock_webpush.return_value = MagicMock(status_code=201)

        service = WebPushService(
            vapid_private_key=vapid_keys["private_key"],
            vapid_public_key=vapid_keys["public_key"],
            vapid_email=vapid_keys["email"]
        )

        # Создаем мок подписки
        subscription = MagicMock(spec=PushSubscription)
        subscription.endpoint = "https://fcm.googleapis.com/test"
        subscription.keys = {"p256dh": "test_p256dh", "auth": "test_auth"}
        subscription.platform = "desktop"

        result = await service.send_push(
            subscription=subscription,
            title="Test Title",
            message="Test Message",
            url="/test/path",
            tag="test_notification"
        )

        assert result is True
        mock_webpush.assert_called_once()

        # Проверяем payload
        call_kwargs = mock_webpush.call_args.kwargs
        payload = json.loads(call_kwargs["data"])

        assert payload["title"] == "Test Title"
        assert payload["message"] == "Test Message"
        assert payload["url"] == "/test/path"
        assert payload["tag"] == "test_notification"

    @pytest.mark.asyncio
    @patch('core.push.service.webpush')
    async def test_send_to_user_sends_to_all_devices(
        self,
        mock_webpush,
        test_push_subscriptions_multi_device,
        vapid_keys
    ):
        """send_to_user отправляет на все устройства из БД."""
        from core.push.service import WebPushService

        mock_webpush.return_value = MagicMock(status_code=201)

        user_id, subscriptions = test_push_subscriptions_multi_device

        service = WebPushService(
            vapid_private_key=vapid_keys["private_key"],
            vapid_public_key=vapid_keys["public_key"],
            vapid_email=vapid_keys["email"]
        )

        expired = await service.send_to_user(
            subscriptions=subscriptions,
            title="Multi-device",
            message="Sent to all"
        )

        # webpush должен быть вызван 3 раза
        assert mock_webpush.call_count == 3
        assert expired == []

    @pytest.mark.asyncio
    @patch('core.push.service.webpush')
    async def test_expired_subscription_returned(self, mock_webpush, vapid_keys):
        """410 Gone возвращает endpoint в списке expired."""
        from pywebpush import WebPushException

        from core.push.models import PushSubscription
        from core.push.service import WebPushService

        # Мокаем 410 Gone
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_webpush.side_effect = WebPushException("Gone", response=mock_response)

        service = WebPushService(
            vapid_private_key=vapid_keys["private_key"],
            vapid_public_key=vapid_keys["public_key"],
            vapid_email=vapid_keys["email"]
        )

        subscription = MagicMock(spec=PushSubscription)
        subscription.endpoint = "https://fcm.googleapis.com/expired"
        subscription.keys = {"p256dh": "key", "auth": "auth"}
        subscription.platform = "ios"

        expired = await service.send_to_user(
            subscriptions=[subscription],
            title="Test",
            message="Test"
        )

        assert "https://fcm.googleapis.com/expired" in expired


class TestNotifyUserIntegration:
    """
    Интеграционные тесты notify_user() с push.
    """

    @pytest.mark.asyncio
    @patch('core.push.service.webpush')
    async def test_notify_user_sends_push_when_offline(
        self,
        mock_webpush,
        push_repository,
        vapid_keys,
        unique_id
    ):
        """
        notify_user() отправляет push если пользователь не подключен к WebSocket.
        """
        from core.push.service import init_web_push_service
        from core.websocket.publisher import Notification, NotificationType, notify_user

        mock_webpush.return_value = MagicMock(status_code=201)

        # Инициализируем сервис
        init_web_push_service(
            vapid_private_key=vapid_keys["private_key"],
            vapid_public_key=vapid_keys["public_key"],
            vapid_email=vapid_keys["email"]
        )

        user_id = f"user_notify_{unique_id}"
        endpoint = f"https://fcm.googleapis.com/notify-{unique_id}"

        # Создаем подписку
        await push_repository.upsert_subscription(
            user_id=user_id,
            endpoint=endpoint,
            keys={"p256dh": "key", "auth": "auth"},
            platform="desktop"
        )

        # Отправляем уведомление (пользователь offline - нет WebSocket)
        notification = Notification(
            type=NotificationType.SYSTEM,
            title="Test Notification",
            message="This should trigger push",
            service="test"
        )

        await notify_user(user_id, notification)

        # webpush должен быть вызван
        assert mock_webpush.called, "webpush should be called for offline user"

        # Cleanup
        await push_repository.delete_subscription(user_id, endpoint)
