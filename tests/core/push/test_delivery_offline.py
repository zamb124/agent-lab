"""
Доставка офлайн-push: разделение Web и APNs.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.push.delivery import deliver_offline_push
from core.push.models import PushSubscription
from core.push.service import init_web_push_service


@pytest.mark.asyncio
async def test_deliver_offline_push_skips_apns_in_webpush_path(
    frontend_di, vapid_keys, unique_id
):
    _ = frontend_di
    _ = init_web_push_service(
        vapid_private_key=vapid_keys["private_key"],
        vapid_public_key=vapid_keys["public_key"],
        vapid_email=vapid_keys["email"],
    )

    user_id = f"u-{unique_id}"
    web_endpoint = f"https://fcm.googleapis.com/w-{unique_id}"
    apns_endpoint = f"apns:{unique_id}"
    web_sub = await PushSubscription.upsert_by_endpoint(
        user_id=user_id,
        endpoint=web_endpoint,
        keys={"p256dh": "k", "auth": "a"},
        platform="desktop",
    )
    _ = await PushSubscription.upsert_by_endpoint(
        user_id=user_id,
        endpoint=apns_endpoint,
        keys={"device_token": unique_id},
        platform="ios_native",
    )
    try:
        with patch("core.push.delivery.get_apns_push_service", return_value=None), patch(
            "core.push.delivery.get_settings"
        ) as gs, patch("core.push.service.webpush") as mock_webpush:
            gs.return_value.database.shared_url = "postgresql://x/y"
            mock_webpush.return_value = MagicMock(status_code=201)
            removed = await deliver_offline_push(
                user_id,
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
    finally:
        _ = await PushSubscription.delete_by_user_and_endpoint(user_id, web_endpoint)
        _ = await PushSubscription.delete_by_user_and_endpoint(user_id, apns_endpoint)
