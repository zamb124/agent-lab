"""
Доставка офлайн-push: разделение Web и APNs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db.models import PushSubscription


@pytest.mark.asyncio
async def test_deliver_offline_push_skips_apns_in_webpush_path(vapid_keys, unique_id):
    from core.push.delivery import deliver_offline_push
    from core.push.service import init_web_push_service

    init_web_push_service(
        vapid_private_key=vapid_keys["private_key"],
        vapid_public_key=vapid_keys["public_key"],
        vapid_email=vapid_keys["email"],
    )

    web_sub = MagicMock(spec=PushSubscription)
    web_sub.endpoint = f"https://fcm.googleapis.com/w-{unique_id}"
    web_sub.keys = {"p256dh": "k", "auth": "a"}
    web_sub.platform = "desktop"

    apns_sub = MagicMock(spec=PushSubscription)
    apns_sub.endpoint = "apns:" + "b" * 64
    apns_sub.keys = {"device_token": "b" * 64}
    apns_sub.platform = "ios_native"

    with patch("core.push.delivery.PushSubscriptionRepository") as RepoCls, patch(
        "core.push.delivery.get_apns_push_service", return_value=None
    ):
        repo = RepoCls.return_value
        repo.get_user_subscriptions = AsyncMock(return_value=[web_sub, apns_sub])
        repo.delete_by_endpoint = AsyncMock()

        with patch("core.push.delivery.get_settings") as gs:
            gs.return_value.database.shared_url = "postgresql://x/y"

            with patch("core.push.service.webpush") as mock_webpush:
                mock_webpush.return_value = MagicMock(status_code=201)
                removed = await deliver_offline_push(
                    f"u-{unique_id}",
                    title="t",
                    message="m",
                    action_url=None,
                    tag="system",
                    priority="normal",
                    data={},
                )

        assert removed == []
        mock_webpush.assert_called_once()
        call_info = mock_webpush.call_args.kwargs["subscription_info"]
        assert call_info["endpoint"] == web_sub.endpoint
