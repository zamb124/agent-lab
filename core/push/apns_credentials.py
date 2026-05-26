"""
Сборка учётных данных APNs из push.* с заполнением из auth.providers.apple.

Сессионный JWT платформы к APNs не относится. Тот же файл ключа .p8, что и для
Sign in with Apple, подходит для push, только если в Apple Developer у этого
ключа включена возможность «Apple Push Notifications service (APNs)».
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import BaseSettings


@dataclass(frozen=True)
class ResolvedApnsCredentials:
    team_id: str
    key_id: str
    private_key_pem: str
    bundle_id: str
    use_sandbox: bool


def resolve_apns_credentials(settings: BaseSettings) -> ResolvedApnsCredentials | None:
    push = settings.push
    bundle_id = _clean_optional_config_value(push.apns_bundle_id)
    if bundle_id is None:
        return None

    apple = settings.auth.providers.get("apple")

    team_id = _clean_optional_config_value(push.apns_team_id)
    key_id = _clean_optional_config_value(push.apns_key_id)
    private_key = _clean_optional_config_value(push.apns_private_key)
    if apple is not None:
        team_id = team_id or _clean_optional_config_value(apple.apple_team_id)
        key_id = key_id or _clean_optional_config_value(apple.apple_key_id)
        private_key = private_key or _clean_optional_config_value(apple.apple_private_key)

    if not team_id or not key_id or not private_key:
        return None

    return ResolvedApnsCredentials(
        team_id=team_id,
        key_id=key_id,
        private_key_pem=private_key,
        bundle_id=bundle_id,
        use_sandbox=push.apns_use_sandbox,
    )


def _clean_optional_config_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None
