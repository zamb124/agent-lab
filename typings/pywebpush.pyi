from typing import TypeAlias

WebPushKeys: TypeAlias = dict[str, str | bytes]
WebPushSubscriptionInfo: TypeAlias = dict[str, str | bytes | WebPushKeys]


class WebPushResponse:
    status_code: int


class WebPushException(Exception):
    response: WebPushResponse | None


def webpush(
    *,
    subscription_info: WebPushSubscriptionInfo,
    data: str | bytes | None = None,
    vapid_private_key: str | None = None,
    vapid_claims: dict[str, str | int] | None = None,
    **kwargs: str | int | bool | bytes | None,
) -> str | WebPushResponse: ...
