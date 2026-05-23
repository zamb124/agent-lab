"""
Сборка учётных данных APNs из push.* с заполнением из auth.providers.apple.

Сессионный JWT платформы к APNs не относится. Тот же файл ключа .p8, что и для
Sign in with Apple, подходит для push, только если в Apple Developer у этого
ключа включена возможность «Apple Push Notifications service (APNs)».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedApnsCredentials:
    team_id: str
    key_id: str
    private_key_pem: str
    bundle_id: str
    use_sandbox: bool


def resolve_apns_credentials(settings: Any) -> ResolvedApnsCredentials | None:
    push = settings.push
    bundle_id = push.apns_bundle_id
    if bundle_id is None or not str(bundle_id).strip():
        return None

    apple = None
    providers = getattr(settings.auth, "providers", None)
    if isinstance(providers, dict):
        apple = providers.get("apple")

    team_id = push.apns_team_id or _apple_field(apple, "apple_team_id")
    key_id = push.apns_key_id or _apple_field(apple, "apple_key_id")
    private_key = push.apns_private_key or _apple_field(apple, "apple_private_key")

    if not team_id or not key_id or not private_key:
        return None

    pem = str(private_key).strip()
    if not pem:
        return None

    return ResolvedApnsCredentials(
        team_id=str(team_id).strip(),
        key_id=str(key_id).strip(),
        private_key_pem=pem,
        bundle_id=str(bundle_id).strip(),
        use_sandbox=bool(push.apns_use_sandbox),
    )


def _apple_field(apple: Any, name: str) -> str | None:
    if apple is None:
        return None
    value = getattr(apple, name, None)
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
